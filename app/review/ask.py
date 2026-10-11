"""Highlight to ask (POST /api/review/{chart_id}/ask {span_ids}): the coordinator selects any lines of the guideline
on the case page and gets a ruling for that block and the chart's evidence for it.

    snap      the selection's g-span ids, ranges expanded, sorted in document order (the page snaps a DOM selection
              to whole lines before it asks; at most MAX_LINES)
    known     every selected line belongs to a requirement of this case's checklist (struck and added ones count),
              or was set aside by step H, or sits inside the confirmed section between two cited lines of one
              paragraph (a lead-in; `between_cited`): the answer is the stored verdicts, no model call.
              The logic is the case's own expression restricted to the requirements hit; an `any` / `at_least` that
              loses alternatives keeps each lost one as "another option in this checklist" with its compiled
              status, so "A and either B or C" reads as the case reads it, not as a narrower rule
    asked     anything else: one focused judge call (prompts/ask_guideline.md): the selected lines, the lines around
              them, where they sit, and the whole chart in; parts (each citing selected lines only), the logic over
              them and one verdict per part out. Code checks as step H and step J do: refs inside the selection,
              each quote located in its lines (else dropped), the logic parsed (else every part required),
              judge.to_verdicts + judge.verify (citations resolve, dates near the note, measurements in their
              lines, durations from verified dates). The model never types the evidence: every quote shown is the
              chart's own lines, resolved from the citation. Cached by (chart id, guideline sha, sorted span ids)
              in data/results/<chart_id>/asks.json; a repeat is `cached`, free
    ruling    code, from evaluate.compile_expr over the logic: Documented · Not in the chart · Contradicted; an
              exclusion at the top reads as tree.WORDS (does not apply / applies / can't tell); lines a chart
              cannot show (headings, billing, process text, definitions) say so and have no logic
    where     inside the confirmed section, or where else in the guideline the lines come from (the part that
              applies to every request, another section, or the nearest all-caps heading above them)

Every ask is recorded in data/results/<chart_id>/probes.json ({spans, at, by, source, mark}) so the person signing
off sees where the coordinator looked. Adding the answer to the case's checklist is app/review/additions.py.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.checklist import admin, criteria
from app.core import llm, log, store
from app.evidence import judge
from app.review import additions, strikes, tree
from app.decide.evaluate import compile_expr, leaf_ids, parse
from app.core.models import CriteriaSet, Criterion, Expression, Result, Selection, Span, Verdict
from app.understand.select import pathway_name
from app.ingest.spans import expand, locate, render_chart, render_guideline, table, text_of, wording

logger = log.get("ask")

MAX_LINES = 40          # a selection longer than this is a section, not a block; the page says to select less
CONTEXT = 6             # lines shown to the model above and below the selection, not citable
_lock = threading.Lock()

RULING = {"documented": "Documented", "missing": "Not in the case", "contradicted": "Contradicted",
          "not_chart": "This isn't something the case can show", "clear": tree.WORDS["clear"],
          "applies": tree.WORDS["applies"], "unclear": tree.WORDS["unclear"], "struck": tree.WORDS["struck"]}
WHY_NOT = {"heading": "It is a heading.", "billing": "It is billing and coding text.",
           "process": "It describes how the payer handles requests.",
           "description": "It is background, not something a case documents.",
           "confirm": "It is confirmed outside the case."}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- the model's answer, as validated


class _P(BaseModel):
    id: str
    refs: list[str]
    quote: Optional[str] = None
    threshold: Optional[criteria._T] = None
    question: str = ""


class AskOut(BaseModel):
    chart_can_show: bool = True
    kind: str = "requirement"
    parts: list[_P] = Field(default_factory=list)
    logic: Any = None
    verdicts: list[judge._V] = Field(default_factory=list)


# ---------------------------------------------------------------- the case, as K-L see it


class Case:
    """What a finished case's decision is made of, with this case's strikes and additions applied."""

    def __init__(self, chart_id: str):
        from app.review import review

        rec = store.load_result(chart_id)
        self.chart_id = chart_id
        self.r = Result.model_validate(rec["result"])
        self.sel = Selection.model_validate(rec["selection"])
        self.gid = (rec.get("meta") or {}).get("guideline_id") or self.r.guideline_id
        self.gspans, self.sha, _ = store.load_guideline_spans(self.gid)
        self.rspans = store.load_chart_spans(chart_id)
        self.gt, self.rt = table(self.gspans), table(self.rspans)
        self.pos = {s.id: i for i, s in enumerate(self.gspans)}
        self.order = store.load_order(chart_id)
        self.n, self.base = review._criteria_for_case(self.sha, self.order, review.confirmation(chart_id), chart_id)
        self.pids = list(self.r.pathway_used or [])
        verdicts = {k: Verdict.model_validate(v) for k, v in (rec.get("verdicts") or {}).items()}
        cs, self.pruned = admin.split(chart_id, self.base, self.pids)      # admin leaves set aside, before strikes
        verdicts, _ = admin.verdicts(chart_id, self.base, verdicts)
        cs, self.struck = strikes.split(chart_id, cs, self.gspans, self.pids)
        self.cs, self.verdicts, _, self.added = additions.extend(chart_id, cs, verdicts, rec.get("jreasons") or {}, self.pids)
        self.crit = {**(self.base.criterion_map() if self.base else {}), **(self.cs.criterion_map() if self.cs else {})}
        self.set_aside = set(expand([x for nu in self.base.not_used for x in nu.spans], self.gt)) if self.base else set()
        self.run_id = self.r.run_id or llm.new_run_id()

    def key(self, ids: list[str]) -> str:
        return f"{self.sha[:16]}:{'+'.join(sorted(ids))}"


def snap(span_ids: list[str], gspans: list[Span]) -> list[str]:
    tbl = table(gspans)
    pos = {s.id: i for i, s in enumerate(gspans)}
    ids = [i for i in dict.fromkeys(expand([str(x) for x in span_ids or []], tbl)) if i in tbl]
    if not ids:
        raise ValueError("select at least one line of the guideline")
    if len(ids) > MAX_LINES:
        raise ValueError(f"select at most {MAX_LINES} lines at a time")
    return sorted(ids, key=pos.get)


# ---------------------------------------------------------------- where the lines come from


_HEAD = re.compile(r"^[A-Z][A-Z0-9 ,/&()'’-]{3,}:$")


def heading_above(gspans: list[Span], i: int) -> Optional[str]:
    """The nearest all-caps heading at or above line i ("BILLING/CODING INFORMATION:"), as words ("Billing/coding
    information"). A reading aid, like tree.note_heading; None when there is none."""
    for j in range(i, -1, -1):
        t = gspans[j].text.strip()
        if _HEAD.match(t):
            return t.rstrip(":").strip().capitalize()
    return None


def where(c: Case, ids: list[str]) -> dict:
    pos = c.pos

    def within(rgs) -> bool:
        rgs = [r for r in rgs if r.first in pos and r.last in pos]
        return bool(rgs) and all(any(pos[r.first] <= pos[i] <= pos[r.last] for r in rgs) for i in ids)

    pw = {p.id: p for p in (c.n.pathways if c.n else [])}
    mine = [rg for p in c.pids if p in pw for rg in pw[p].spans]
    names = [pathway_name(c.n, p, c.gspans) for p in c.pids if p in pw] if c.n else []
    if within(mine):
        return {"inside": True, "say": None, "section": names[0] if names else None}
    head = heading_above(c.gspans, pos[ids[0]])
    part = f"“{head}”" if head else "another part of this guideline"
    if c.n and within(c.n.guideline.always_on):
        say = f"From {part}, outside the confirmed indication; it applies to every request under this guideline."
    else:
        other = next((p for p in (c.n.pathways if c.n else []) if p.id not in c.pids and within(p.spans)), None)
        say = (f"From “{pathway_name(c.n, other.id, c.gspans)}”, another indication of this guideline, not the one "
               f"confirmed for this case.") if other else f"From {part}, outside the confirmed indication."
    return {"inside": False, "say": say, "section": names[0] if names else None}


# ---------------------------------------------------------------- known: the stored verdicts, restricted to the lines


def restrict(e: Any, keep: set[str], other: dict[str, Any]) -> Optional[Any]:
    """The expression with only the leaves in `keep`; the structure above them stays. An alternative of an `any` /
    `at_least` that keeps nothing becomes a stand-in leaf ("~1", its subexpression filed in `other`), so the
    alternatives not selected still count as the case counts them. None when nothing is kept."""
    if isinstance(e, str):
        return e if e in keep else None
    (op, arg), = e.items()
    if op == "not":
        ch = restrict(arg, keep, other)
        return {"not": ch} if ch is not None else None
    if op == "all":
        kids = [k for k in (restrict(x, keep, other) for x in arg) if k is not None]
        return None if not kids else kids[0] if len(kids) == 1 else {"all": kids}
    xs = arg["of"] if op == "at_least" else arg
    got = [restrict(x, keep, other) for x in xs]
    if all(k is None for k in got):
        return None
    kids = []
    for x, k in zip(xs, got):
        if k is None:
            sid = f"~{len(other) + 1}"
            other[sid] = x
            k = sid
        kids.append(k)
    return {"at_least": {"k": arg["k"], "of": kids}} if op == "at_least" else {"any": kids}


def between_cited(gspans: list[Span], cited: set[str], section: list) -> set[str]:
    """The uncited lines of the confirmed section that sit between two cited lines of the same block: known without
    a model call (v1.2's H keeps no line accounting, so a lead-in such as "There is documentation of one or more of
    the following indications:" between "at least 3 millimeters" and "1. Ulceration" is cited by no requirement).

    A block is a paragraph as the guideline prints it and the case page draws it: a run of lines that starts at a
    line with a blank line before it (`Span.blank_before`) and runs to the line before the next such line (a page
    break does not end it). Inside one block, every line strictly after the block's first cited line and before
    its last cited line counts, when the cited lines and the gap line all lie inside the confirmed section's ranges
    (`section`: the case's pathway ranges). Never across blocks (a gap between the last cited line of one paragraph
    and the first of the next asks), never before the first or after the last cited line of a block, never outside
    the confirmed section."""
    pos = {s.id: i for i, s in enumerate(gspans)}
    inside: set[int] = set()
    for rg in section:
        if rg.first in pos and rg.last in pos:
            inside.update(range(pos[rg.first], pos[rg.last] + 1))
    blocks: dict[int, list[int]] = {}
    b = 0
    for i, s in enumerate(gspans):
        if s.blank_before and i:
            b += 1
        if i in inside and s.id in cited:
            blocks.setdefault(b, []).append(i)
    out: set[str] = set()
    for xs in blocks.values():
        out.update(gspans[i].id for i in range(min(xs) + 1, max(xs)) if i in inside and gspans[i].id not in cited)
    return out


def _known(c: Case, ids: list[str]) -> Optional[dict]:
    if not c.cs:
        return None
    want = set(ids)
    expr = {e.pathway: e.expr for e in c.cs.expressions}
    leaves = list(dict.fromkeys(i for p in c.pids if p in expr for i in leaf_ids(expr[p])))
    refs = {cid: set(expand(c.crit[cid].refs, c.gt)) for cid in leaves + list(c.struck) if cid in c.crit}
    hit = [cid for cid in dict.fromkeys(leaves + list(c.struck)) if refs.get(cid, set()) & want]
    if not hit:
        return None
    covered = set().union(*(refs[x] for x in hit))
    rest = want - covered
    if rest - c.set_aside:
        pw = {p.id: p for p in (c.n.pathways if c.n else [])}
        section = [rg for p in c.pids if p in pw for rg in pw[p].spans]
        cited = set().union(*refs.values()) if refs else set()
        if rest - c.set_aside - between_cited(c.gspans, cited, section):
            return None
    keep = {x for x in hit if x not in c.struck}
    other: dict[str, Any] = {}
    rex = []
    for p in c.pids:
        if p in expr:
            x = restrict(expr[p], keep, other)
            if x is not None and x not in rex:
                rex.append(x)
    logic = None if not rex else rex[0] if len(rex) == 1 else {"all": rex}
    verdicts = dict(c.verdicts)
    words: dict[str, str] = {}
    for sid, sub in other.items():
        node = compile_expr(sub, c.verdicts)
        verdicts[sid] = Verdict(criterion=sid, status=node.status, confidence=node.confidence)
        first = [wording(c.crit[i], c.gt) for i in leaf_ids(sub) if i in c.crit]
        words[sid] = (first[0].rstrip(".") + (" …" if len(first) > 1 else "")) if first else sid
    struck = [x for x in hit if x in c.struck]
    v = _view(c, logic, verdicts, c.crit, words)
    adds = {c.added[x]["id"]: c.added[x] for x in hit if x in c.added}
    same = additions.find(c.chart_id, ids, c.cs.key)
    v.update(source="added" if same else "known", requirements=hit,
             set_aside=sorted(rest, key=c.pos.get),
             struck=[{"criterion": x, "words": wording(c.crit[x], c.gt), **{k: c.struck[x].get(k) for k in ("id", "by", "at", "reason")}}
                     for x in struck],
             added=additions.summary(same) if same else (additions.summary(next(iter(adds.values()))) if len(adds) == 1 else None))
    if logic is None:                         # every requirement hit was removed for this case
        v["ruling"] = {"mark": "struck", "say": RULING["struck"], "status": None}
    return v


# ---------------------------------------------------------------- the ruling, the logic and the evidence, from code


def _shape(e: Any, node, info: dict, crit: dict[str, Criterion], verdicts: dict[str, Verdict], words: dict[str, str],
           c: Case) -> dict:
    if isinstance(e, str):
        cr, v = crit.get(e), verdicts.get(e)
        inf = info.get(e) or {"role": "requirement", "needed": True, "status": node.status}
        mark = tree.mark_of(inf, cr, v)
        out = {"criterion": e, "words": words.get(e) or (wording(cr, c.gt) if cr else e), "mark": mark,
               "say": tree.WORDS[mark], "other": e.startswith("~"), "evidence": []}
        if cr is not None and mark not in ("not_needed", "other_option", "confirm"):
            from app.review import review                 # review imports this module's callers; never at module top
            out["evidence"] = review.order_evidence(review.evidence(v, c.rspans, c.rt), mark,
                                                    judge.is_duration(cr.threshold, cr))
        return out
    (op, arg), = e.items()
    if op == "not":
        kids = [_shape(arg, node.children[0], info, crit, verdicts, words, c)]
    else:
        xs = arg["of"] if op == "at_least" else arg
        kids = [_shape(x, n, info, crit, verdicts, words, c) for x, n in zip(xs, node.children)]
    return {"op": op, "k": arg["k"] if op == "at_least" else None, "status": node.status, "kids": kids}


def _leaves_of(t: dict) -> list[dict]:
    return [t] if "criterion" in t else [x for k in t["kids"] for x in _leaves_of(k)]


def _view(c: Case, logic: Any, verdicts: dict[str, Verdict], crit: dict[str, Criterion], words: dict[str, str]) -> dict:
    """The card from a logic and its verdicts: the ruling, the logic as a nested checklist, one lead quote and the
    rest. No logic: nothing a chart can show."""
    if logic is None:
        return {"ruling": {"mark": "not_chart", "say": RULING["not_chart"], "status": None}, "logic": None,
                "parts": 0, "lead": None, "more": []}
    node = compile_expr(logic, verdicts)
    info: dict[str, dict] = {}
    tree.classify(logic, node, True, info)
    shape = _shape(logic, node, info, crit, verdicts, words, c)
    leaves = _leaves_of(shape)
    real = [crit[x["criterion"]] for x in leaves if x["criterion"] in crit]
    if real and all(not x.answerable for x in real):
        mark = "not_chart"
    elif isinstance(logic, dict) and "not" in logic:
        mark = {"MET": "clear", "NOT_MET": "applies", "INSUFFICIENT": "unclear"}[node.status]
    else:
        mark = {"MET": "documented", "INSUFFICIENT": "missing", "NOT_MET": "contradicted"}[node.status]
    # the lead quote: from a part whose own mark agrees with the ruling first, then the rest in printed order
    agree = {"documented": ("documented",), "missing": ("missing", "unclear"), "contradicted": ("contradicted", "applies"),
             "clear": ("clear", "part_clear"), "applies": ("applies", "part_shown"), "unclear": ("unclear", "missing")}.get(mark, ())
    evs, seen = [], set()
    for x in sorted(leaves, key=lambda x: x["mark"] not in agree):
        for e in x["evidence"]:
            if e["span"] not in seen:
                seen.add(e["span"])
                evs.append(dict(e, criterion=x["criterion"]))
    return {"ruling": {"mark": mark, "say": RULING[mark], "status": node.status}, "logic": shape, "parts": len(leaves),
            "lead": evs[0] if evs else None, "more": evs[1:]}


# ---------------------------------------------------------------- asked: one focused judge call


def _model(c: Case, ids: list[str]) -> dict:
    sel = set(ids)
    a, b = c.pos[ids[0]], c.pos[ids[-1]]
    around = [s for s in c.gspans[max(0, a - CONTEXT): b + CONTEXT + 1] if s.id not in sel]
    w = where(c, ids)
    where_text = w["say"] or (f"Inside the indication confirmed for this case: “{w['section']}”." if w["section"]
                              else "Inside the indication confirmed for this case.")
    prompt = llm.prompt("ask_guideline", order_line=judge.order_line(c.order) if c.order else "(not stated)",
                        where=where_text, selected_spans=render_guideline([c.gt[i] for i in ids]),
                        context_spans=render_guideline(around) or "(none)", chart_spans=render_chart(c.rspans))
    out = llm.call(c.run_id, "ask_guideline", prompt, AskOut, model=llm.pick_models()[1], reasoning_effort="low")
    problems: list[str] = []
    names: dict[str, str] = {}
    parts: list[Criterion] = []
    for p in out.parts:
        pid = re.sub(r"[^A-Za-z0-9_]", "_", p.id.strip())[:40] or f"part{len(parts) + 1}"
        if p.id in names or pid in names.values():
            continue
        refs = expand(p.refs, c.gt)
        if not refs or not all(r in sel for r in refs):
            problems.append("Part of the answer pointed outside the selected lines and was left out.")
            continue
        names[p.id] = pid
        parts.append(Criterion(id=pid, refs=p.refs, quote=locate(p.quote or "", text_of(p.refs, c.gt)),
                               threshold=criteria._threshold(p.threshold), answerable=True,
                               question=p.question or ""))
    ok = {x.id for x in parts}
    logic = None
    if parts and out.chart_can_show:
        pr: list[str] = []
        logic = parse(additions._rename(out.logic, names), ok, pr, "logic") if out.logic is not None else None
        if logic is None:
            logic = {"all": [x.id for x in parts]} if len(parts) > 1 else parts[0].id
            problems.append("How these lines join could not be read; every part is treated as required.")
        used = set(leaf_ids(logic))
        parts = [x for x in parts if x.id in used]
    else:
        parts = []
    verdicts: dict[str, Verdict] = {}
    jreasons: dict[str, list[str]] = {}
    if parts:
        cs = CriteriaSet(key="ask", criteria=parts, expressions=[Expression(pathway="ask", expr=logic)])
        vs = [v.model_copy(update={"criterion": names.get(v.criterion, v.criterion)}) for v in out.verdicts]
        verdicts = judge.to_verdicts(vs, cs.criterion_map())
        from app import pipeline                    # pipeline imports the modules ask builds on; never at module top
        jreasons = judge.verify(verdicts, c.rspans, cs, [x.id for x in parts], c.gspans,
                                pipeline.chart_labels(c.chart_id, c.rspans))
    kind = out.kind if out.kind in WHY_NOT or out.kind == "requirement" else "requirement"
    return {"key": c.key(ids), "spans": ids, "chart_can_show": bool(parts), "kind": kind,
            "criteria": [x.model_dump(exclude_none=True) for x in parts], "logic": logic,
            "verdicts": {k: v.model_dump(by_alias=True, exclude_none=True) for k, v in verdicts.items()},
            "jreasons": jreasons, "problems": problems, "run_id": c.run_id, "at": now()}


def _asked_view(c: Case, raw: dict) -> dict:
    crit = {x["id"]: Criterion.model_validate(x) for x in raw.get("criteria") or []}
    verdicts = {k: Verdict.model_validate(v) for k, v in (raw.get("verdicts") or {}).items()}
    v = _view(c, raw.get("logic") if crit else None, verdicts, crit, {})
    if v["ruling"]["mark"] == "not_chart":
        v["why_not"] = WHY_NOT.get(raw.get("kind") or "", "Nothing in these lines is something a case documents.")
    v["problems"] = list(raw.get("problems") or []) + [x for rs in (raw.get("jreasons") or {}).values() for x in rs]
    return v


# ---------------------------------------------------------------- on disk


def _load(chart_id: str, name: str, field: str):
    p = store.RESULTS / chart_id / name
    if not p.exists():
        return {} if field == "asks" else []
    try:
        return json.loads(p.read_text()).get(field) or ({} if field == "asks" else [])
    except ValueError:
        return {} if field == "asks" else []


def _save(chart_id: str, name: str, field: str, value) -> None:
    p = store.RESULTS / chart_id / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({field: value}, indent=2))


def cached(chart_id: str, key: str) -> Optional[dict]:
    return _load(chart_id, "asks.json", "asks").get(key)


def probes(chart_id: str) -> list[dict]:
    return _load(chart_id, "probes.json", "probes")


def _probe(chart_id: str, ids: list[str], by: Optional[str], source: str, mark: str) -> None:
    with _lock:
        items = probes(chart_id)
        items.append({"id": uuid.uuid4().hex[:8], "spans": ids, "at": now(), "by": by, "source": source, "mark": mark})
        _save(chart_id, "probes.json", "probes", items)


# ---------------------------------------------------------------- the operations


def _finish(c: Case, ids: list[str], v: dict) -> dict:
    v.update(key=c.key(ids), spans=ids, where=where(c, ids),
             lines=[{"id": i, "text": c.gt[i].text, "page": c.gt[i].page} for i in ids])
    v.setdefault("problems", [])
    v.setdefault("added", None)
    v["can_add"] = v.get("source") in ("asked", "cached") and v["ruling"]["mark"] != "not_chart" and not v["added"]
    return v


def ask(chart_id: str, span_ids: list[str], by: Optional[str] = None) -> dict:
    """The card for these lines: known (no model call), cached, or asked (one call). Recorded as a probe."""
    c = Case(chart_id)
    ids = snap(span_ids, c.gspans)
    v = _known(c, ids)
    if v is None:
        key = c.key(ids)
        raw = cached(chart_id, key)
        source = "cached"
        if raw is None:
            t0 = time.time()
            raw = _model(c, ids)
            source = "asked"
            with _lock:
                asks = _load(chart_id, "asks.json", "asks")
                asks[key] = raw
                _save(chart_id, "asks.json", "asks", asks)
            logger.info("ask %s on chart %s: %s in %.1fs", key, chart_id, "parts " + str(len(raw["criteria"])), time.time() - t0)
        v = _asked_view(c, raw)
        same = additions.find(chart_id, ids, c.cs.key if c.cs else None)
        v.update(source=source, added=additions.summary(same) if same else None)
    v = _finish(c, ids, v)
    _probe(chart_id, ids, by, v["source"], v["ruling"]["mark"])
    return v


def answer_to_add(chart_id: str, span_ids: list[str]) -> tuple[dict, str, CriteriaSet]:
    """(the stored ask, the lines' words, the checklist it joins) for POST .../additions. LookupError: not asked
    yet; PermissionError: already on the checklist or nothing a chart can show."""
    c = Case(chart_id)
    ids = snap(span_ids, c.gspans)
    if c.cs is None:
        raise PermissionError("this case has no checklist to add to")
    if additions.find(chart_id, ids, c.cs.key):
        raise PermissionError("these lines are already on this case's checklist")
    if _known(c, ids) is not None:
        raise PermissionError("these lines are already on this case's checklist")
    raw = cached(chart_id, c.key(ids))
    if raw is None:
        raise LookupError("ask about these lines first")
    if not raw.get("criteria") or raw.get("logic") is None:
        raise PermissionError("a case cannot show these lines, so they cannot be checked")
    return raw, text_of(ids, c.gt), c.cs
