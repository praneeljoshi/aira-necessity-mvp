"""A coordinator adds guideline lines to this case's checklist, from the highlight-to-ask card (app/review/ask.py). The
opposite of a strike (app/review/strikes.py) and, like it, per case only: the cached criteria and every other case are
untouched; the addition joins this case's logic and K-L run again (code only, no model call) over the stored
verdicts plus the addition's own, which the ask already judged and verified.

    data/results/<chart_id>/additions.json   {"additions": [{id, chart_id, spans, words, ask_key, criteria_key,
                                               criteria: [Criterion], expr, verdicts: {id: Verdict}, jreasons,
                                               by, at, feedback_id, undone: null | {by, at}}]}

The ask's parts become criteria under ids of their own (`add<id>_<part>`), so they never collide with the
checklist's. The ask's logic joins every judged section's expression as one more AND term: `all(expr, added)`, an
`all` at the top gains one more child. Adding is the safe direction (one more thing the chart must show, never one
less), so it takes effect at once, unlike line feedback; it withdraws a sign-off the way a strike does.

Append-only in spirit: taking an addition off sets `undone`, nothing is deleted. An addition applies while it is not
undone, and only to the checklist it was made on (same criteria key): a re-run that builds a different checklist
leaves it in the file, inert. Each addition is also filed as feedback (kind should_be_requirement, `addition` = its
id) so it shows across cases; taking it off removes that feedback item.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Optional

from app.core import store
from app.core.models import CriteriaSet, Criterion, Expression, Verdict


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _path(chart_id: str):
    return store.RESULTS / chart_id / "additions.json"


def load(chart_id: str) -> list[dict]:
    p = _path(chart_id)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text()).get("additions") or [])
    except ValueError:
        return []


def _save(chart_id: str, items: list[dict]) -> None:
    p = _path(chart_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"additions": items}, indent=2))


def active(chart_id: str) -> list[dict]:
    return [x for x in load(chart_id) if not x.get("undone")]


def _rename(e: Any, ids: dict[str, str]) -> Any:
    if isinstance(e, str):
        return ids.get(e, e)
    (op, arg), = e.items()
    if op == "not":
        return {"not": _rename(arg, ids)}
    if op == "at_least":
        return {"at_least": {"k": arg["k"], "of": [_rename(x, ids) for x in arg["of"]]}}
    return {op: [_rename(x, ids) for x in arg]}


def _and(e: Any, more: Any) -> Any:
    if isinstance(e, dict) and "all" in e:
        return {"all": list(e["all"]) + [more]}
    return {"all": [e, more]}


# ---------------------------------------------------------------- what a case's checklist looks like with its additions


def extend(chart_id: str, cs: Optional[CriteriaSet], verdicts: dict[str, Verdict], jreasons: dict[str, list[str]],
           pids: Optional[list[str]] = None) -> tuple[Optional[CriteriaSet], dict[str, Verdict], dict[str, list[str]], dict[str, dict]]:
    """(the CriteriaSet with this case's additions joined to the judged sections' expressions, the verdicts and J
    reasons with theirs, {criterion id: the addition it came from}). `pids` = the judged sections (all when None).
    No additions on this checklist: everything as given and {}."""
    if cs is None:
        return cs, verdicts, jreasons, {}
    mine = [x for x in active(chart_id) if x.get("criteria_key") == cs.key]
    if not mine:
        return cs, verdicts, jreasons, {}
    used = set(pids) if pids is not None else {e.pathway for e in cs.expressions}
    have = {c.id for c in cs.criteria}
    crit = list(cs.criteria) + [Criterion.model_validate(c) for x in mine for c in x["criteria"] if c["id"] not in have]
    exprs = []
    for e in cs.expressions:
        if e.pathway in used:
            ex = e.expr
            for x in mine:
                ex = _and(ex, x["expr"])
            e = Expression(pathway=e.pathway, expr=ex)
        exprs.append(e)
    v2 = dict(verdicts)
    j2 = dict(jreasons)
    added: dict[str, dict] = {}
    for x in mine:
        for cid, v in (x.get("verdicts") or {}).items():
            v2[cid] = Verdict.model_validate(v)
        for cid, rs in (x.get("jreasons") or {}).items():
            j2[cid] = list(rs)
        for c in x["criteria"]:
            added[c["id"]] = x
    return cs.model_copy(update={"criteria": crit, "expressions": exprs}), v2, j2, added


# ---------------------------------------------------------------- the operations


def find(chart_id: str, spans: list[str], cs_key: Optional[str] = None) -> Optional[dict]:
    """The active addition made on exactly these lines (and this checklist, when given)."""
    want = sorted(spans)
    return next((x for x in active(chart_id) if sorted(x.get("spans") or []) == want
                 and (cs_key is None or x.get("criteria_key") == cs_key)), None)


def add(chart_id: str, answer: dict, words: str, by: Optional[str], cs: CriteriaSet) -> dict:
    """`answer` is the stored ask (app/review/ask.py): its criteria, logic, verified verdicts and J reasons, under the
    part ids the model chose; they are filed here under ids of this addition's own."""
    from app.review import feedback

    aid = uuid.uuid4().hex[:8]
    ids = {c["id"]: f"add{aid}_{c['id']}" for c in answer["criteria"]}
    crit = [dict(c, id=ids[c["id"]]) for c in answer["criteria"]]
    verdicts = {ids[k]: dict(v, criterion=ids[k]) for k, v in (answer.get("verdicts") or {}).items() if k in ids}
    jreasons = {ids[k]: v for k, v in (answer.get("jreasons") or {}).items() if k in ids}
    item = {"id": aid, "chart_id": chart_id, "spans": list(answer["spans"]), "words": words, "ask_key": answer["key"],
            "criteria_key": cs.key, "criteria": crit, "expr": _rename(answer["logic"], ids), "verdicts": verdicts,
            "jreasons": jreasons, "by": by, "at": now(), "feedback_id": None, "undone": None}
    fb = feedback.add(chart_id, "should_be_requirement", "guideline", f"Added to this case's checklist: “{words[:200].rstrip()}{'…' if len(words) > 200 else ''}”",
                      list(answer["spans"]), list(ids.values()), by=by, extra={"addition": aid})
    item["feedback_id"] = fb["id"]
    _save(chart_id, load(chart_id) + [item])
    return item


def undo(chart_id: str, addition_id: str, by: Optional[str]) -> Optional[dict]:
    from app.review import feedback

    items = load(chart_id)
    x = next((i for i in items if i.get("id") == addition_id and not i.get("undone")), None)
    if x is None:
        return None
    x["undone"] = {"by": by, "at": now()}
    _save(chart_id, items)
    if x.get("feedback_id"):
        feedback.remove(chart_id, x["feedback_id"])
    return x


def summary(x: dict) -> dict:
    """What the sign-off panel and the page show of an addition."""
    return {k: x.get(k) for k in ("id", "spans", "words", "by", "at")}
