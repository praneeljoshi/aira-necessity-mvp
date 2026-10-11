"""Step H (model, the whole guideline, for the confirmed indication(s)) and its code checks.

    in:  every g-span; the confirmed pathway(s) with their lines; the request; the codes on them
    out: Criterion[] {id, refs, quote, threshold?, answerable, question} · Expression[] {pathway, expr} · notes
    two calls: read (every condition that limits approval, as criteria + a logic string per pathway), then an
          add-only audit (a patient who meets the logic but the text denies -> more criteria / tighter logic)
    code: quotes are found in the document (in the cited lines, else anywhere: the refs are then corrected) · logic
          parses and names known criteria · one retry on either -> still failing: status needs_review

No line accounting and no set-aside: the line ids are only an index for citing. Completeness is the model's job,
measured by the tree diff.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from app.checklist import hints
from app.core import llm, log
from app.decide.evaluate import from_logic, leaf_ids, parse
from app.core.models import Code, CriteriaSet, Criterion, Expression, Narrowed, Procedure, Selection, Span, Threshold
from app.understand.narrow import retry_prompt
from app.ingest.spans import in_range, locate, render_guideline, resolves, table, text_of

logger = log.get("criteria")

_OPS = {">=": "gte", "≥": "gte", "gte": "gte", "<=": "lte", "≤": "lte", "lte": "lte", ">": "gt", "gt": "gt",
        "<": "lt", "lt": "lt", "==": "eq", "=": "eq", "eq": "eq"}


class _T(BaseModel):
    op: str
    value: Any
    unit: Optional[str] = None


class _C(BaseModel):
    id: str
    quote: str
    refs: list[str] = Field(default_factory=list)
    threshold: Optional[_T] = None
    answerable: bool = True
    question: str
    admin: bool = False                  # not a condition about the patient (billing, paperwork, a heading): app/checklist/admin.py
    admin_why: Optional[str] = None


class _L(BaseModel):
    pathway: str
    logic: Any            # "a AND (b OR c) AND NOT d", or the JSON form


class HOut(BaseModel):
    notes: str = ""
    criteria: list[_C] = Field(default_factory=list)
    logic: list[_L] = Field(default_factory=list)


class AOut(BaseModel):
    """The audit: patients who would pass but the text denies, and the fix (new criteria, revised logic)."""
    loopholes: list[str] = Field(default_factory=list)
    criteria: list[_C] = Field(default_factory=list)
    logic: list[_L] = Field(default_factory=list)


def picked(sel: Selection) -> list[str]:
    return list(dict.fromkeys(p.pathway for p in sel.pathways))


# ---------------------------------------------------------------- quotes


def _flat(spans: list[Span]) -> tuple[str, list[tuple[int, str]]]:
    """The document as one string (lines stripped, joined by a space) and each line's start offset."""
    parts, starts, at = [], [], 0
    for s in spans:
        t = s.text.strip()
        starts.append((at, s.id))
        parts.append(t)
        at += len(t) + 1
    return " ".join(parts), starts


def find(quote: str, spans: list[Span], prefer: Optional[set[str]] = None) -> Optional[tuple[list[str], str]]:
    """Where the quote is printed: (the line ids it covers, as one range citation; the document's own text). Only
    whitespace and a hyphen broken over a line are forgiven. With several matches, one touching `prefer` wins."""
    words = (quote or "").split()
    if not words:
        return None
    flat, starts = _flat(spans)
    pats = [r"\s+".join(re.escape(w) for w in words),
            r"\s+".join("(?:-\\s)?".join(re.escape(ch) for ch in w) for w in words)]
    for pat in pats:
        hits = list(re.finditer(pat, flat))
        if not hits:
            continue

        def ids(m):
            a, b = m.start(), m.end() - 1
            return [i for k, (st, i) in enumerate(starts)
                    if st <= b and (starts[k + 1][0] if k + 1 < len(starts) else len(flat) + 1) > a]

        best = next((m for m in hits if prefer and set(ids(m)) & prefer), hits[0])
        got = ids(best)
        cite = got[0] if len(got) == 1 else f"{got[0]}-{got[-1]}"
        return [cite], best.group(0)
    return None


def _threshold(t: Optional[_T]) -> Optional[Threshold]:
    if not t or t.op.strip() not in _OPS:
        return None
    return Threshold(op=_OPS[t.op.strip()], value=t.value, unit=t.unit)


def _expr(x: Any, ids: set[str], problems: list[str], where: str) -> Optional[Any]:
    e = from_logic(x, problems, where) if isinstance(x, str) and not x.strip() in ids else x
    return None if e is None else parse(e, ids, problems, where)


def check(h: HOut, spans: list[Span], want: list[str]) -> tuple[list[str], list[Criterion], list[Expression]]:
    """(problems, criteria with their quotes found, expressions). A quote not in its cited lines is looked for in the
    whole document and the refs corrected; only a quote printed nowhere is a problem."""
    tbl = table(spans)
    problems: list[str] = []
    crit: list[Criterion] = []
    seen: set[str] = set()
    for c in h.criteria:
        if c.id in seen:
            problems.append(f"criterion id '{c.id}' used twice")
            continue
        seen.add(c.id)
        refs = [r for r in c.refs if resolves(r, tbl)]
        quote = locate(c.quote, text_of(refs, tbl)) if refs else None
        if quote is None:
            near = {i for r in refs for i in [r.split("-")[0]]}
            hit = find(c.quote, spans, near)
            if hit:
                refs, quote = hit
            else:
                problems.append(f"criterion '{c.id}': quote is not printed in the document: \"{c.quote[:90]}\"")
        if c.threshold and c.threshold.op.strip() not in _OPS:
            problems.append(f"criterion '{c.id}': threshold op '{c.threshold.op}' is not one of >=, >, <=, <, ==")
        crit.append(Criterion(id=c.id, refs=refs, quote=quote, threshold=_threshold(c.threshold),
                              answerable=c.answerable, question=c.question, admin=bool(c.admin),
                              admin_why=(c.admin_why or None) if c.admin else None))
    ids = {c.id for c in crit}
    exprs: list[Expression] = []
    got = [x.pathway for x in h.logic]
    for p in want:
        if p not in got:
            problems.append(f"no logic for pathway '{p}'")
    for x in h.logic:
        if x.pathway not in want:
            continue
        e = _expr(x.logic, ids, problems, f"logic for {x.pathway}")
        if e is None and ids:            # unreadable logic never loses the tree: every criterion required, for review
            problems.append(f"logic for {x.pathway} could not be read: every criterion is required until a person fixes it")
            e = {"all": sorted(ids)}
        if e is not None:
            exprs.append(Expression(pathway=x.pathway, expr=e))
    return problems, crit, exprs


def keep_missing(before: list[Expression], after: list[Expression], problems: list[str]) -> list[Expression]:
    """A pathway the audit's logic left without an expression keeps its first-pass one (the audit may only add)."""
    have = {e.pathway for e in after}
    kept = [e for e in before if e.pathway not in have]
    if kept:
        problems.append(f"the audit gave no readable logic for {', '.join(e.pathway for e in kept)}; the first logic stands")
    return after + kept


# ---------------------------------------------------------------- the calls


def _codes_json(codes: list[Code]) -> str:
    return json.dumps([{"code": c.code, "tag": c.tag, "description": c.description[:200]} for c in codes], indent=0)


def request_line(p: Optional[Procedure], extra: Optional[dict] = None) -> str:
    """The order in one line; `extra` (the reduce runner's allow-listed fields: cpt_line, age, sex) appended."""
    if p is None and not extra:
        return "(not given)"
    bits = [p.as_written, ("codes " + ", ".join(p.cpt)) if p.cpt else None, ("treating " + p.target) if p.target else None,
            ("diagnosis " + p.diagnosis) if p.diagnosis else None, ("plan: " + p.plan) if p.plan else None] if p else []
    bits += [f"{k.replace('_', ' ')} {v}" for k, v in (extra or {}).items() if v not in (None, "")]
    return "; ".join(str(b) for b in bits if b) or "(not given)"


def _cite(spans: list[Span], ranges) -> str:
    return ", ".join(r.first if r.first == r.last else f"{r.first}-{r.last}" for r in ranges)


def _pathways(n: Narrowed, want: list[str], spans: list[Span], given: Optional[str] = None) -> str:
    """Each confirmed pathway by its first line; `given` (the reduce runner's heading arm): that heading text whole."""
    tbl = table(spans)
    out = []
    for p in n.pathways:
        if p.id in want:
            first = next((s.text.strip() for r in p.spans for s in in_range(spans, r) if s.text.strip()), p.id)
            first = " ".join(given.split()) if given else first[:140]
            out.append(f"- `{p.id}`: “{first}” (lines {_cite(spans, p.spans)})"
                       + (f"; about {', '.join(p.targets)}" if p.targets else ""))
    return "\n".join(out) or "(none)"


def _merge(h: HOut, a: AOut) -> HOut:
    """Audit additions: new criteria appended (an existing id keeps its first wording); revised logic replaces."""
    have = {c.id for c in h.criteria}
    crit = h.criteria + [c for c in a.criteria if c.id not in have]
    logic = {x.pathway: x for x in h.logic}
    for x in a.logic:
        logic[x.pathway] = x
    return HOut(notes=h.notes, criteria=crit, logic=list(logic.values()))


def _dropped(before: list[Expression], after: list[Expression]) -> list[str]:
    old = {i for e in before for i in leaf_ids(e.expr)}
    new = {i for e in after for i in leaf_ids(e.expr)}
    return sorted(old - new)


def inputs(spans: list[Span], n: Narrowed, sel: Selection, procedure: Optional[Procedure] = None,
           extra: Optional[dict] = None, indication: Optional[str] = None) -> tuple[list[str], dict]:
    """(the confirmed pathways, the prompt variables step H's loose prompts share)."""
    want = picked(sel)
    on = {c for p in n.pathways if p.id in want for c in p.codes} | {x.code for x in sel.code_gate}
    codes = [c for c in n.codes if c.code in on] or n.codes
    return want, {"plan_rule": llm.prompt("reduce/plan") + "\n", "request": request_line(procedure, extra),
                  "pathways": _pathways(n, want, spans, indication), "codes_json": _codes_json(codes),
                  "guideline_spans": render_guideline(spans)}


def first_pass(base: str, spans: list[Span], want: list[str], run_id: str, model: str, step: str = "criteria_guideline",
               tally: Optional[dict] = None):
    """One reading with one retry on check problems: (h, problems, criteria, expressions)."""
    h = llm.call(run_id, step, base, HOut, model=model, reasoning_effort="high", tally=tally)
    problems, crit, exprs = check(h, spans, want)
    if problems:
        logger.warning("criteria: %d problem(s), retrying once: %s", len(problems), " | ".join(problems)[:300])
        h2 = llm.call(run_id, step, retry_prompt(base, h, problems), HOut, model=model,
                      reasoning_effort="high", tally=tally)
        p2, c2, e2 = check(h2, spans, want)
        if len(p2) <= len(problems):
            h, problems, crit, exprs = h2, p2, c2, e2
    return h, problems, crit, exprs


def build(spans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
          procedure: Optional[Procedure] = None, extra: Optional[dict] = None, indication: Optional[str] = None,
          tally: Optional[dict] = None, progress: Optional[Callable[[str], None]] = None,
          prompt: str = "criteria_guideline", audit_prompt: str = "criteria_audit") -> CriteriaSet:
    """`progress`: called with a short line for the status page as the step moves (Stage.doing). `prompt` /
    `audit_prompt`: the prompt files (a variant such as STEP_H=loose-next passes its own)."""
    say = progress or (lambda _: None)
    want, v = inputs(spans, n, sel, procedure, extra, indication)
    payer, hint = hints.payer_hint(spans)          # STRUCTURE_HINTS=1 and a known payer only; else "" (prompt as shipped)
    if payer:
        logger.info("criteria %s: payer structure hint %s", key, payer)
    base = hints.for_guideline(llm.prompt(prompt, **v), hint)
    model = llm.pick_models()[0]
    say("Building the checklist from the whole guideline")
    h, problems, crit, exprs = first_pass(base, spans, want, run_id, model, tally=tally)
    say(f"{len(crit)} conditions so far")
    return audit(h, problems, crit, exprs, spans, want, v, key, run_id, model, tally, progress, prompt=audit_prompt,
                 hint=hint)


def audit(h: HOut, problems: list[str], crit: list[Criterion], exprs: list[Expression], spans: list[Span],
          want: list[str], v: dict, key: str, run_id: str, model: str, tally: Optional[dict] = None,
          progress: Optional[Callable[[str], None]] = None, prompt: str = "criteria_audit",
          hint: str = "") -> CriteriaSet:
    """The add-only audit, then the CriteriaSet. `hint`: the payer structure hint build injected (app/checklist/hints.py)."""
    if progress:
        progress(f"Checking for gaps ({len(crit)} conditions)")
    shown = {"criteria": [{"id": c.id, "quote": c.quote or text_of(c.refs, table(spans)), "question": c.question}
                          for c in crit],
             "logic": [{"pathway": x.pathway, "logic": x.logic} for x in h.logic if x.pathway in want]}
    audit = llm.prompt(prompt, request=v["request"], pathways=v["pathways"],
                       tree=json.dumps(shown, indent=1), guideline_spans=v["guideline_spans"])
    audit = hints.for_guideline(audit, hint)
    loopholes: list[str] = []
    try:
        a = llm.call(run_id, "criteria_audit", audit, AOut, model=model, reasoning_effort="high", tally=tally)
        loopholes = a.loopholes
        if a.criteria or a.logic:
            p3, c3, e3 = check(_merge(h, a), spans, want)
            e3 = keep_missing(exprs, e3, p3)
            lost = _dropped(exprs, e3)
            if lost:      # the audit may only tighten: a criterion its logic left out goes back in at the top
                p3.append(f"the audit's logic left out {', '.join(lost)}; put back as required")
                e3 = [_and_back(e, exprs, lost) for e in e3]
            h, problems, crit, exprs = _merge(h, a), p3, c3, e3
    except Exception as x:   # the audit only adds; the first reading stands without it
        logger.warning("criteria audit failed: %s", x)
        problems.append(f"audit failed: {type(x).__name__}")
    used = {i for e in exprs for i in leaf_ids(e.expr)}
    cs = CriteriaSet(key=key, criteria=[c for c in crit if c.id in used], expressions=exprs, notes=h.notes,
                     loopholes=loopholes, status="needs_review" if problems else "ok", problems=problems)
    cs.run_id = run_id
    logger.info("criteria %s: %d criteria, %d expressions, %d loophole(s) found by the audit, %s", key,
                len(cs.criteria), len(cs.expressions), len(loopholes), cs.status)
    return cs


def _and_back(e: Expression, before: list[Expression], lost: list[str]) -> Expression:
    """A criterion the audit's logic lost goes back in, ANDed at the top: the audit may only tighten."""
    mine = [i for i in lost if any(i in leaf_ids(b.expr) for b in before if b.pathway == e.pathway)]
    if not mine:
        return e
    kids = e.expr["all"] if isinstance(e.expr, dict) and "all" in e.expr else [e.expr]
    return Expression(pathway=e.pathway, expr={"all": kids + mine})
