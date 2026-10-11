"""A coordinator strikes a requirement that is not necessary for this case (the checklist over-includes on purpose:
exclusions anywhere in the document, documentation and billing lines become requirements). Per case only: the
cached criteria and every other case are untouched; the strike changes the logic this case is decided with, and
K-L run again (code only, no model call) over the stored verdicts.

    data/results/<chart_id>/strikes.json     {"strikes": [{id, criterion, words, refs, criteria_key, code, reason, by,
                                               at, feedback_id, was, undone: null | {by, at}}]}
                                             (`was` = the requirement's mark when struck: striking a gap shows;
                                             `code` = the reason chip, one of REASONS, absent on older records;
                                             `reason` = the person's note, or the chip's label when none was written)

Append-only in spirit: an un-strike sets `undone` on the record, nothing is deleted, so the file is the case's
audit trail. A strike applies while it is not undone, and only to the checklist it was made on (same criteria key,
same criterion id, same words): a re-run that builds a different checklist leaves it in the file, inert.

Removing a leaf from the logic (`prune`), by the operator it sits under:
    all        the leaf is dropped; the rest must still be documented
    any        that alternative is dropped; the others still count
    at_least   k of n becomes k of n-1, k clamped to what is left (2 of 2 with one struck = the remaining one)
    not        the exclusion is dropped: not(leaf) goes; inside not(any(...)) the struck item goes and the other
               items still exclude; inside a compound exclusion (an `all` under a `not`, "X without Y") the whole
               exclusion goes, because its remaining parts alone would be a wider exclusion the guideline never
               wrote (the parts dropped with it are listed as removed along with the struck one)
    an operator left with nothing is dropped from its parent the same way; one child left replaces the operator.
A strike that would leave a judged section with no requirement at all is refused (`check`): an empty section would
read as everything documented, which is a Ready no one could stand behind.

Each strike is also filed as feedback (kind not_a_requirement, the reason as its text, `strike` = the strike id,
`code` = the chip) so it is visible across cases in GET /api/feedback; an un-strike removes that feedback item. The
codes are the labelled data for improving the guideline trees: why the checklist over-included this line.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from app.core import store
from app.decide.evaluate import leaf_ids
from app.core.models import CriteriaSet, Expression, Span
from app.ingest.spans import expand, table, wording


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# why a requirement is not needed for this case: one tap on the page (keys 1-6, in this order); "other" needs a note
REASONS = [
    ("not_for_case", "Not for this procedure or patient"),
    ("billing", "Billing or coding only"),
    ("paperwork", "Paperwork the payer collects"),
    ("other_section", "Belongs to another section"),
    ("wrong_quote", "The quote is wrong"),
    ("other", "Other"),
]
LABELS = dict(REASONS)

# ---------------------------------------------------------------- the logic with leaves removed


def prune(e: Any, struck: set[str], negated: bool = False) -> Optional[Any]:
    """The expression with every struck leaf removed (the rules in the module header). None when nothing is left.
    `negated` is true inside an odd number of `not`s, where an `all` is a compound exclusion."""
    if isinstance(e, str):
        return None if e in struck else e
    (op, arg), = e.items()
    if op == "not":
        child = prune(arg, struck, not negated)
        return {"not": child} if child is not None else None
    if op == "at_least":
        kids = [k for k in (prune(x, struck, negated) for x in arg["of"]) if k is not None]
        if not kids:
            return None
        if len(kids) == 1:
            return kids[0]
        return {"at_least": {"k": max(1, min(arg["k"], len(kids))), "of": kids}}
    if op == "all" and negated and struck & set(leaf_ids(e)):
        return None                       # a part of "X without Y" struck: the whole exclusion goes
    kids = [k for k in (prune(x, struck, negated) for x in arg) if k is not None]
    if not kids:
        return None
    return kids[0] if len(kids) == 1 else {op: kids}


# ---------------------------------------------------------------- on disk


def _path(chart_id: str):
    return store.RESULTS / chart_id / "strikes.json"


def load(chart_id: str) -> list[dict]:
    p = _path(chart_id)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text()).get("strikes") or [])
    except ValueError:
        return []


def _save(chart_id: str, items: list[dict]) -> None:
    p = _path(chart_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"strikes": items}, indent=2))


def active(chart_id: str) -> list[dict]:
    return [x for x in load(chart_id) if not x.get("undone")]


# ---------------------------------------------------------------- what a case's checklist looks like with its strikes


def _matches(x: dict, cs: CriteriaSet, gt: dict[str, Span]) -> bool:
    c = cs.criterion_map().get(x.get("criterion"))
    return c is not None and x.get("criteria_key") == cs.key and wording(c, gt) == x.get("words")


def split(chart_id: str, cs: Optional[CriteriaSet], gspans: list[Span],
          pids: Optional[list[str]] = None) -> tuple[Optional[CriteriaSet], dict[str, dict]]:
    """(the CriteriaSet with this case's strikes applied to its expressions, {criterion id: the strike that removed
    it}). Leaves dropped along with a struck one (the other parts of a compound exclusion) map to that strike with
    `removed_with` set to the struck criterion (None on the struck one itself). `pids` limits the strikes to leaves
    of those pathways (the judged ones). No strikes: the CriteriaSet itself and {}."""
    if cs is None:
        return cs, {}
    gt = table(gspans)
    expr = {e.pathway: e.expr for e in cs.expressions}
    used = [p for p in (pids if pids is not None else list(expr)) if p in expr]
    leaves = {i for p in used for i in leaf_ids(expr[p])}
    mine = [x for x in active(chart_id) if x.get("criterion") in leaves and _matches(x, cs, gt)]
    if not mine:
        return cs, {}
    ids = {x["criterion"] for x in mine}
    out_exprs = []
    removed: dict[str, dict] = {x["criterion"]: dict(x, removed_with=None) for x in mine}
    for e in cs.expressions:
        if e.pathway not in used:
            out_exprs.append(e)
            continue
        p = prune(e.expr, ids)
        if p is not None:
            out_exprs.append(Expression(pathway=e.pathway, expr=p))
        before = set(leaf_ids(e.expr))
        for x in mine:                    # what each strike takes with it, alone
            alone = prune(e.expr, {x["criterion"]})
            gone = before - set(leaf_ids(alone) if alone is not None else [])
            for cid in gone - ids:
                removed.setdefault(cid, dict(x, removed_with=x["criterion"]))
    return cs.model_copy(update={"expressions": out_exprs}), removed


def applied(chart_id: str, cs: Optional[CriteriaSet], gspans: list[Span], pids: Optional[list[str]] = None) -> Optional[CriteriaSet]:
    return split(chart_id, cs, gspans, pids)[0]


# ---------------------------------------------------------------- the operations


def check(chart_id: str, criterion: str, cs: Optional[CriteriaSet], gspans: list[Span], pids: list[str]) -> Optional[str]:
    """Why this strike cannot be made, in plain words; None when it can."""
    if cs is None:
        return "this case has no requirements to remove"
    expr = {e.pathway: e.expr for e in cs.expressions}
    if not any(criterion in leaf_ids(expr[p]) for p in pids if p in expr):
        return "not a requirement of this case"
    if any(x.get("criterion") == criterion for x in active(chart_id)):
        return "this requirement is already removed for this case"
    struck = {x["criterion"] for x in active(chart_id)} | {criterion}
    for p in pids:
        if p in expr and criterion in leaf_ids(expr[p]) and prune(expr[p], struck) is None:
            return "this is the last requirement left in the section; it cannot be removed"
    return None


def add(chart_id: str, criterion: str, reason: str, by: Optional[str], cs: CriteriaSet, gspans: list[Span],
        was: Optional[str] = None, code: Optional[str] = None) -> dict:
    """`was`: the requirement's mark when it was struck ("missing", "contradicted", …); a strike of a gap is never
    invisible: the page and the packet say a requirement that was not documented was removed, and by whom."""
    from app.review import feedback

    gt = table(gspans)
    c = cs.criterion_map()[criterion]
    refs = expand(c.refs, gt)
    item = {"id": uuid.uuid4().hex[:12], "chart_id": chart_id, "criterion": criterion, "words": wording(c, gt),
            "refs": refs, "criteria_key": cs.key, "code": code, "reason": reason, "by": by, "at": now(), "feedback_id": None,
            "undone": None, "was": was}
    fb = feedback.add(chart_id, "not_a_requirement", "guideline", reason, refs or [criterion], [criterion], by=by,
                      extra={"strike": item["id"], "code": code})
    item["feedback_id"] = fb["id"]
    _save(chart_id, load(chart_id) + [item])
    return item


def undo(chart_id: str, strike_id: str, by: Optional[str]) -> Optional[dict]:
    from app.review import feedback

    items = load(chart_id)
    x = next((i for i in items if i.get("id") == strike_id and not i.get("undone")), None)
    if x is None:
        return None
    x["undone"] = {"by": by, "at": now()}
    _save(chart_id, items)
    if x.get("feedback_id"):
        feedback.remove(chart_id, x["feedback_id"])
    return x


# ---------------------------------------------------------------- K-L again, over the stored verdicts


def redecide(chart_id: str, by: Optional[str] = None, why: str = "strike"):
    """Steps K-L again for a finished case, with its strikes applied (pipeline._decide applies them): the stored
    selection, verdicts and the J reasons; no model call. The decide stage is re-recorded and the status says when
    and why (`redecided`). Returns the new Result."""
    import copy

    from app import pipeline
    from app.core import status
    from app.evidence import judge
    from app.review import review
    from app.core.models import Selection, Verdict

    rec = store.load_result(chart_id)
    sel = Selection.model_validate(rec["selection"])
    verdicts = {k: Verdict.model_validate(v) for k, v in (rec.get("verdicts") or {}).items()}
    meta = rec.get("meta") or {}
    gid = meta.get("guideline_id") or rec["result"].get("guideline_id")
    order = store.load_order(chart_id)
    gspans, sha, _ = store.load_guideline_spans(gid)
    rspans = store.load_chart_spans(chart_id)
    n, cs = review._criteria_for_case(sha, order, review.confirmation(chart_id), chart_id)
    if order is None or n is None:
        raise ValueError("the order or the guideline reading for this case is gone; run the check again")
    jreasons = rec.get("jreasons")
    if jreasons is None and cs is not None:          # a result saved before jreasons.json: J again, on copies
        expr = {e.pathway: e.expr for e in cs.expressions}
        crit = cs.criterion_map()
        ids = [i for p in dict.fromkeys(x.pathway for x in sel.pathways) if p in expr for i in leaf_ids(expr[p])]
        asked = [i for i in dict.fromkeys(ids) if i in crit and crit[i].answerable]
        from app import pipeline as _p
        jreasons = judge.verify(copy.deepcopy(verdicts), rspans, cs, asked, gspans, _p.chart_labels(chart_id, rspans))
    doc = status.load_status(chart_id)
    st = status.Recorder.from_doc(doc) if doc else status.Recorder(chart_id, gid, persist=False)
    st.stage_rec("decide")["gate"] = None
    st.doc["redecided"] = {"at": now(), "by": by, "why": why}
    return pipeline._decide(st, chart_id, gid, meta.get("override"), order, n, sel, cs, verdicts, jreasons or {},
                            gspans, rspans, rec["result"].get("run_id"))
