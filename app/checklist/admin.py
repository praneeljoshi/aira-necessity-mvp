"""Admin leaves: step H marks each criterion `admin` when its line is not a condition about the patient (billing,
coding or payment; paperwork; a heading, lead-in, date or definition nothing depends on). Per case, code prunes
those leaves from the logic before strikes (`split`), with strikes' own operator rules (strikes.prune), so they are
never asked of the chart, counted or signed for; the case page lists them at the bottom as `set_aside`.

Guards (code, not the model): a leaf is never pruned when that would
    empty the whole expression or any alternative of an `any` / `at_least` (a pathway never disappears)
    sit under a NOT (pipeline.negated_leaves): exclusions are always asked
    leave a judged section with no requirement
ADMIN_PRUNE=0 turns it off: the logic is exactly what step H wrote.

"Ask it anyway" restores one leaf for this case (`unprune`), with one judge call for its verdict:

    data/results/<chart_id>/unpruned.json    {"unpruned": [{id, criterion, words, criteria_key, by, at, feedback_id,
                                               verdict, jreasons, undone: null | {by, at}}]}

Append-only like strikes: setting it aside again sets `undone`. A restore applies only to the checklist it was made
on (same criteria key). Each restore is filed as feedback (kind should_be_requirement, `unprune` = its id).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Optional

from app.core import store
from app.decide.evaluate import leaf_ids
from app.core.models import CriteriaSet, Expression, Span, Verdict
from app.review.strikes import prune

WHYS = ("billing or coding", "paperwork", "heading or definition", "procedure wording")
DEFAULT_WHY = "not a condition about the patient"


def enabled() -> bool:
    return os.environ.get("ADMIN_PRUNE", "1").strip() not in ("0", "false", "off", "")


def why_of(c) -> str:
    w = (getattr(c, "admin_why", None) or "").strip().lower()
    return w if w in WHYS else DEFAULT_WHY


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- on disk


def _path(chart_id: str):
    return store.RESULTS / chart_id / "unpruned.json"


def load(chart_id: str) -> list[dict]:
    p = _path(chart_id)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text()).get("unpruned") or [])
    except ValueError:
        return []


def _save(chart_id: str, items: list[dict]) -> None:
    p = _path(chart_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"unpruned": items}, indent=2))


def active(chart_id: Optional[str], key: Optional[str] = None) -> list[dict]:
    if not chart_id:
        return []
    return [x for x in load(chart_id) if not x.get("undone") and (key is None or x.get("criteria_key") == key)]


# ---------------------------------------------------------------- the pruning


def _empties_alt(e: Any, gone: set[str]) -> bool:
    """True when every leaf of some alternative of an any / at_least is in `gone`."""
    if isinstance(e, str):
        return False
    (op, arg), = e.items()
    if op == "not":
        return _empties_alt(arg, gone)
    kids = arg["of"] if op == "at_least" else arg
    if op in ("any", "at_least") and any(set(leaf_ids(k)) <= gone for k in kids):
        return True
    return any(_empties_alt(k, gone) for k in kids)


def _ok(e: Any, gone: set[str]) -> bool:
    if set(leaf_ids(e)) <= gone:
        return False
    p = prune(e, gone)
    return p is not None and not _empties_alt(e, gone)


def split(chart_id: Optional[str], cs: Optional[CriteriaSet], pids: Optional[list[str]] = None
          ) -> tuple[Optional[CriteriaSet], dict[str, str]]:
    """(the CriteriaSet with this case's admin leaves pruned from the judged sections, {criterion id: why}). Off,
    no CriteriaSet or nothing to prune: the CriteriaSet itself and {}."""
    if cs is None or not enabled():
        return cs, {}
    from app.pipeline import negated_leaves              # pipeline imports this module's callers

    expr = {e.pathway: e.expr for e in cs.expressions}
    used = [p for p in (pids if pids is not None else list(expr)) if p in expr]
    if not used:
        return cs, {}
    leaves = {i for p in used for i in leaf_ids(expr[p])}
    negated = {i for p in used for i in negated_leaves(expr[p])}
    back = {x["criterion"] for x in active(chart_id, cs.key)}
    gone: set[str] = set()
    whys: dict[str, str] = {}
    for c in cs.criteria:
        if not c.admin or c.id not in leaves or c.id in negated or c.id in back:
            continue
        trial = gone | {c.id}
        if all(_ok(expr[p], trial) for p in used):
            gone, whys[c.id] = trial, why_of(c)
    if not gone:
        return cs, {}
    out = [Expression(pathway=e.pathway, expr=prune(e.expr, gone)) if e.pathway in used else e for e in cs.expressions]
    return cs.model_copy(update={"expressions": out}), whys


def applied(chart_id: Optional[str], cs: Optional[CriteriaSet], pids: Optional[list[str]] = None) -> Optional[CriteriaSet]:
    return split(chart_id, cs, pids)[0]


def verdicts(chart_id: Optional[str], cs: Optional[CriteriaSet], v: dict[str, Verdict],
             jr: Optional[dict[str, list[str]]] = None) -> tuple[dict[str, Verdict], dict[str, list[str]]]:
    """The verdicts (and J reasons) with each restored leaf's own, where the judge's run has none for it."""
    v2, j2 = dict(v), dict(jr or {})
    if cs is None:
        return v2, j2
    for x in active(chart_id, cs.key):
        cid = x["criterion"]
        if cid not in v2 and x.get("verdict"):
            v2[cid] = Verdict.model_validate(x["verdict"])
            if x.get("jreasons"):
                j2[cid] = list(x["jreasons"])
    return v2, j2


# ---------------------------------------------------------------- ask it anyway


def _judge_one(chart_id: str, cs: CriteriaSet, cid: str, gspans: list[Span], run_id: Optional[str]
               ) -> tuple[Optional[dict], list[str], Optional[str]]:
    """(the verdict, its J reasons, an error) for one restored leaf: the judge_chart call the run uses, over the
    chart's lines, then J. A leaf no chart can show is set as the run sets it. A failed call: no verdict (the page
    reads "not in the chart yet")."""
    from app import pipeline
    from app.core import llm
    from app.evidence import judge
    from app.core.models import Verdict as V

    c = cs.criterion_map()[cid]
    if not c.answerable:
        v = V(criterion=cid, status="MET", confidence=1.0, rationale="A case cannot show this; confirm it outside the case.")
        return json.loads(v.model_dump_json(by_alias=True)), [], None
    try:
        rspans = store.load_chart_spans(chart_id)
        order = store.load_order(chart_id)
        run_id = run_id or llm.new_run_id()
        ev, _ = pipeline.evidence_for(chart_id, rspans, run_id)     # the run's evidence lines (A2, cached per chart)
        got = judge.judge(ev, cs, [cid], gspans, order, run_id)
        jr = judge.verify(got, ev, cs, [cid], gspans, pipeline.chart_labels(chart_id, rspans))
    except Exception as e:                            # never lose the restore: it reads as not in the chart yet
        return None, [], f"{type(e).__name__}: {e}"[:200]
    v = got.get(cid)
    return (json.loads(v.model_dump_json(by_alias=True)) if v else None), list(jr.get(cid) or []), None


def unprune(chart_id: str, cid: str, by: Optional[str], cs: CriteriaSet, gspans: list[Span],
            run_id: Optional[str] = None) -> dict:
    from app.review import feedback
    from app.ingest.spans import expand, table, wording

    gt = table(gspans)
    c = cs.criterion_map()[cid]
    verdict, jr, err = _judge_one(chart_id, cs, cid, gspans, run_id)
    item = {"id": uuid.uuid4().hex[:12], "chart_id": chart_id, "criterion": cid, "words": wording(c, gt),
            "criteria_key": cs.key, "by": by, "at": now(), "feedback_id": None, "verdict": verdict, "jreasons": jr,
            "error": err, "undone": None}
    refs = expand(c.refs, gt)
    fb = feedback.add(chart_id, "should_be_requirement", "guideline", "Ask it anyway: " + item["words"],
                      refs or [cid], [cid], by=by, extra={"unprune": item["id"]})
    item["feedback_id"] = fb["id"]
    _save(chart_id, load(chart_id) + [item])
    return item


def reprune(chart_id: str, cid: str, by: Optional[str]) -> Optional[dict]:
    from app.review import feedback

    items = load(chart_id)
    hit = [x for x in items if x.get("criterion") == cid and not x.get("undone")]
    if not hit:
        return None
    for x in hit:
        x["undone"] = {"by": by, "at": now()}
        if x.get("feedback_id"):
            feedback.remove(chart_id, x["feedback_id"])
    _save(chart_id, items)
    return hit[-1]
