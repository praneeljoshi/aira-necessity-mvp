"""One check = one chart against one guideline the coordinator chose.

    A  code   spans            chart -> r-spans · guideline -> g-spans (at upload); one span per extracted line
    A2 model  sections         whole chart -> labelled sections; the judge reads only `evidence` lines   (cached)
    B  model  order            whole chart -> Order {patient, payer, procedure{cpt, as_written, target, surgeon, diagnosis, plan}, refs}
    C  model  guideline        whole guideline, narrowed by the order -> header, codes, pathways, chosen   (cached)
    E-G code  gates            no pathways · code tags · a pathway per code -> Selection
    H  model  criteria         whole guideline, the confirmed pathway(s) -> criteria + logic, then an add-only audit (cached)
    I  model  judge            the chart's evidence lines, answerable criteria -> verdicts
    J  code   verify           refs, dates, measurements, durations
    K  code   evaluate         expressions x verdicts, weakest decides
    L  code   write            ask, packet, checklist

Model calls per order: B, I always; C and H once per (guideline, cpt[], target).

The review flow pauses after E-G: `run(pause_at_pathways=True)` stops at the `confirm_pathways` gate with
selection.json written and status.json `paused`; `resume(chart_id, picks, by)` builds the Selection from the picks a
person confirmed, records pathways.json, runs H (cached by the confirmed pathways and the order's facts:
`h_cache_key`), I, J, K-L under the same run_id and saves the result. A-C are never re-run by resume.

K-L apply a person's strikes on the case (app/strikes.py: requirements removed for this case only) before deciding;
a case with no strikes.json is decided exactly as before. Lines a person added to the case's checklist
(app/additions.py) join the logic the same way, as one more AND term; no additions.json, no change.
jreasons.json is saved with the result so K-L can run again after a strike (strikes.redecide) without the model.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Callable, Optional

from pydantic import BaseModel, Field

from . import additions, admin, criteria, hints, judge, llm, log, narrow, refs, sections, store, strikes
from .evaluate import leaf_ids
from .models import CriteriaSet, Narrowed, Order, Pick, Procedure, Result, Selection, Span, Verdict
from .result import decide
from .select import pathway_name, select
from .status import Recorder, load_status
from .spans import render_chart, resolves, split_chart, split_guideline, table, unmapped_glyphs

logger = log.get("pipeline")


# ---------------------------------------------------------------- A (guideline, at upload)


def slug(s: str, n: int = 60) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:n].strip("-")


def add_guideline(text: str, filename: str, sha: str, gid: Optional[str] = None) -> str:
    """Code only: split and store. No model call until an order needs it."""
    existing = store.find_guideline_by_sha(sha)
    if existing:
        return existing
    gid = gid or slug(re.sub(r"\.pdf$", "", filename, flags=re.I)) or sha[:12]
    spans = split_guideline(text)
    store.save_guideline_spans(gid, sha, filename, spans)
    odd = unmapped_glyphs(text)
    logger.info("guideline %s: %d spans from %s%s", gid, len(spans), filename,
                f"; private-use characters left as extracted: {odd}" if odd else "")
    return gid


# ---------------------------------------------------------------- B


class _Proc(BaseModel):
    cpt: list[str] = Field(default_factory=list)
    as_written: Optional[str] = None
    target: Optional[str] = None
    surgeon: Optional[str] = None
    diagnosis: Optional[str] = None
    plan: Optional[str] = None


class BOut(BaseModel):
    patient_name: Optional[str] = None
    payer: Optional[str] = None
    procedure: _Proc = Field(default_factory=_Proc)
    refs: list[str] = Field(default_factory=list)


_CODE = re.compile(r"^\s*([0-9]{4}[0-9A-Z]|[A-Z][0-9]{4})")


def base_code(c: str) -> str:
    """The CPT/HCPCS code without its modifier: "36475-LT", "36475 RT", "36475-50" -> "36475". A code table lists
    base codes; the side is the order's target, not part of the code."""
    m = _CODE.match((c or "").upper())
    return m.group(1) if m else (c or "").strip().upper()


def detect_order(rspans: list[Span], chart_id: str, run_id: str) -> Order:
    out = llm.call(run_id, "detect_order", llm.prompt("detect_order", chart_spans=render_chart(rspans)), BOut,
                   model=llm.pick_models()[0])
    tbl = table(rspans)
    text = " ".join(s.text for s in rspans)
    cpt = []
    for c in out.procedure.cpt:
        c = base_code(c)
        if c and re.search(rf"(?<![0-9A-Z]){re.escape(c)}(?![0-9A-Z])", text.upper()):
            cpt.append(c)
        else:
            logger.warning("order: code %r is not written in the chart; dropped", c)
    plan = (out.procedure.plan or "").strip() or None
    if plan and not refs.written_in([s.text for s in rspans], plan):
        logger.warning("order: plan %r is not written in the chart; dropped", plan)
        plan = None
    o = Order(id=chart_id, chart_id=chart_id, patient_name=out.patient_name, payer=out.payer,
              procedure=Procedure(cpt=list(dict.fromkeys(cpt)), as_written=out.procedure.as_written,
                                  target=out.procedure.target, surgeon=out.procedure.surgeon,
                                  diagnosis=out.procedure.diagnosis, plan=plan),
              refs=[r for r in out.refs if resolves(r, tbl)])
    logger.info("order: payer=%r cpt=%s as_written=%r target=%r surgeon=%r plan=%r", o.payer, o.procedure.cpt,
                o.procedure.as_written, o.procedure.target, o.procedure.surgeon, o.procedure.plan)
    return o


def apply_override(o: Order, override: Optional[dict]) -> Order:
    """The coordinator's corrections: codes, target and/or the member's plan."""
    if not override:
        return o
    p = o.procedure.model_copy()
    if override.get("cpt") is not None:
        p.cpt = list(dict.fromkeys(base_code(c) for c in override["cpt"] if c and c.strip()))
    if override.get("target"):
        p.target = str(override["target"]).strip()
    if override.get("plan"):
        p.plan = str(override["plan"]).strip()
    return o.model_copy(update={"procedure": p})


# ---------------------------------------------------------------- the cache key


_SIDE = re.compile(r"\b(left|right|bilateral|both|lt|rt|l|r)\b\.?", re.I)


def target_key(p: Procedure) -> str:
    """Side does not change which section applies; it is dropped from the key."""
    t = p.target or ("" if p.cpt else p.as_written or "")
    return slug(_SIDE.sub(" ", t), 50) or "any"


# The prompt files each step-H mode reads (C reads narrow_guideline). Their bytes, with the mode, make the prompt
# version in the cache keys, so a tree built from other prompts is never served.
C_PROMPTS = ["narrow_guideline"]
H_PROMPTS = {
    "loose": ["criteria_guideline", "criteria_audit", "reduce/plan"],
    "loose-loop": ["criteria_guideline_loop", "loop_round", "reduce/plan"],
    "loose-next": ["criteria_guideline_next", "criteria_audit_next", "reduce/plan"],
    "code": ["reduce/policies", "reduce/indication_given", "reduce/indication_find", "reduce/brief", "reduce/plan",
             "reduce/sweep", "reduce/task", "reduce/fix", "reduce/sweep_code", "reduce/audit"],
    "form": ["reduce/form", "reduce/brief", "reduce/policies", "reduce/indication_given", "reduce/indication_find",
             "reduce/plan", "reduce/sweep", "reduce/sweep_form", "criteria_audit"],
    "script": ["reduce/script", "reduce/plan", "reduce/sweep", "reduce/pitfalls", "reduce/script_audit"],
    "tools": ["reduce/tools", "reduce/plan", "reduce/sweep", "reduce/pitfalls", "reduce/tools_audit"],
}


def step_h() -> str:
    """Shipped step H: loose-next (owner, 2026-10-10). STEP_H=loose rolls back."""
    return os.environ.get("STEP_H", "loose-next")


def _prompt_bytes(name: str) -> bytes:
    p = llm.PROMPTS / f"{name}.md"
    return p.read_bytes() if p.exists() else b""


def prompt_version(with_c: bool = True, mode: Optional[str] = None, hint: Optional[str] = None) -> str:
    """8 hex over the mode's name and the bytes of every prompt file C (with_c) and its H read; `hint` (the payer
    structure hint's `<name>.<sha8>`, only when one was applied) joins them, so the version without one is unchanged."""
    mode = mode or step_h()
    h = hashlib.sha1(mode.encode())
    for name in (C_PROMPTS if with_c else []) + H_PROMPTS.get(mode, []):
        h.update(b"\0" + name.encode() + b"\0" + _prompt_bytes(name))
    if hint:
        h.update(b"\0hint\0" + hint.encode())
    return h.hexdigest()[:8]


# The step-H modes that inject the payer structure hint (criteria.build and its audit; app/hints.py).
HINT_MODES = ("loose", "loose-next")


def h_hint(gspans: Optional[list[Span]]) -> Optional[str]:
    """The payer structure hint H applies to this guideline (`<name>.<sha8>`), or None: flag off, unknown payer, two
    files matching, no guideline lines given, or a mode that does not inject it."""
    return hints.payer_id(gspans) if gspans and step_h() in HINT_MODES else None


def _pin(with_c: bool, hint: Optional[str] = None) -> str:
    """`-m<structure model>-v<prompt version>`: what built a cached tree, so another model's or prompt's never is."""
    return f"-m{re.sub(r'[^A-Za-z0-9._-]+', '_', llm.pick_models()[0])[:40]}-v{prompt_version(with_c, hint=hint)}"


def order_facts(p: Procedure) -> str:
    """Every order fact step H's prompt receives (criteria.request_line), as a key part: the sorted CPT codes, the
    target (side dropped), the ICD codes in the diagnosis and a hash of the plan; `<cpts|nocpt>-<target>[-icd][-p<8>]`.
    The order key (cache_key) and the H key (h_cache_key) both build on it, so the two can never drift."""
    icd = sorted(set(re.findall(r"\b[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\b", p.diagnosis or "")))
    return (f"{'+'.join(sorted(p.cpt)) or 'nocpt'}-{target_key(p)}" + (f"-{'+'.join(icd)}" if icd else "")
            + (f"-p{hashlib.sha1(p.plan.encode()).hexdigest()[:8]}" if p.plan else ""))


def legacy_cache_key(sha: str, p: Procedure) -> str:
    """The order key before models and prompts were in it: read only for older cases that recorded no key."""
    mode = step_h()
    return (f"{sha[:16]}-{order_facts(p)}"
            + ("" if mode == "loose" else f"-h{mode}") + ("-pf" if os.environ.get("PITFALLS") == "1" else ""))


def cache_key(sha: str, p: Procedure, gspans: Optional[list[Span]] = None) -> str:
    """C and H for an order: data/criteria/<sha16>-<cpts>-<target>[-icd][-plan][-hmode][-pf]-m<model>-v<prompts>.
    `gspans`: the guideline's lines, to fold in the payer structure hint when H applies one (else the key is as before)."""
    return legacy_cache_key(sha, p) + _pin(with_c=True, hint=h_hint(gspans))


def h_cache_key(sha: str, n: Narrowed, pids: list[str], p: Optional[Procedure],
                gspans: Optional[list[Span]] = None) -> str:
    """H cached by the pathways a person confirmed AND the order: H's prompt carries the order (procedure, codes,
    target, diagnosis, plan) and its tree holds order-specific conditions (a technique, a CPT descriptor), so one
    order's tree is never served to another order on the same section. `h-<sha16>-<pids>-<ranges8>-o<order facts>
    -m<model>-v<prompts>`: the guideline, the pathway ids, a hash of their line ranges (the same id over different
    ranges is a different section), `order_facts(p)` (the same part cache_key uses), then the model and the H prompt
    version (which includes the mode, and the payer structure hint when H applies one: `gspans`, app/hints.py).
    `p=None` (precompute, no order) gives `-onone`, a key no order ever reads."""
    by = {x.id: x for x in n.pathways}
    pids = sorted(dict.fromkeys(pids))
    ranges = json.dumps([[[r.first, r.last] for r in by[x].spans] if x in by else None for x in pids])
    return ("h-" + sha[:16] + "-" + "+".join(pids) + "-" + hashlib.sha1(ranges.encode()).hexdigest()[:8]
            + "-o" + (order_facts(p) if p is not None else "none") + _pin(with_c=False, hint=h_hint(gspans)))


def case_order_key(sha: str, p: Procedure, chart_id: Optional[str] = None) -> str:
    """The order key a case was read with, for showing it: the key its check recorded (status tree / resume, the
    confirmation's narrowed_key) when that file exists; else today's key when cached; else the key older cases were
    written under. Runs never read through this; they use cache_key."""
    tried = []
    if chart_id:
        st = load_status(chart_id) or {}
        conf = store.load_confirmation(chart_id) or {}
        tk = (st.get("tree") or {}).get("criteria_key") or ""
        tried += [tk if not tk.startswith("h-") else "", (st.get("resume") or {}).get("key") or "",
                  conf.get("narrowed_key") or ""]
    gspans = None
    if chart_id and hints.enabled():          # today's key carries the payer structure hint when H applies one
        try:
            gspans = store.load_guideline_spans((load_status(chart_id) or {}).get("guideline_id") or "")[0]
        except Exception:
            gspans = None
    tried += [cache_key(sha, p, gspans), legacy_cache_key(sha, p)]
    for k in tried:
        if k and store.criteria_cached(k):
            return k
    return cache_key(sha, p, gspans)


# ---------------------------------------------------------------- C and H, cached


def narrowed_for(gid: str, gspans: list[Span], sha: str, order: Order, run_id: str) -> tuple[Narrowed, Optional[CriteriaSet], str]:
    key = cache_key(sha, order.procedure, gspans)
    n, cs = store.load_criteria(key)
    if n is None:
        n = narrow.narrow(gspans, order.procedure, gid, sha, key, run_id)
        n, cs = store.save_criteria(key, n, None)   # first writer wins: a run that narrowed meanwhile is kept
        store.save_guideline_header(n)
    else:
        logger.info("narrow %s: from the cache", key)
    return n, cs, key


def criteria_for(gspans: list[Span], n: Narrowed, sel: Selection, cs: Optional[CriteriaSet], key: str,
                 run_id: str, procedure: Optional[Procedure] = None,
                 progress: Optional[Callable[[str], None]] = None) -> CriteriaSet:
    want = set(criteria.picked(sel))
    if cs is not None and want <= {e.pathway for e in cs.expressions}:
        logger.info("criteria %s: from the cache", key)
        return cs
    cs = build_h(gspans, n, sel, key, run_id, procedure, progress)
    store.save_criteria(key, n, cs)        # first writer wins; this run keeps its own set (pinned for its case)
    return cs


H_WAIT_S = 240      # a run that finds the same checklist being built by another run waits this long to reuse it


def shared_h(key_h: str, build) -> tuple[CriteriaSet, bool]:
    """The checklist for an H cache key that is not cached yet: (cs, built). When another run is building the same
    key (its marker in data/criteria/.locks), wait up to H_WAIT_S for its result and reuse it; else build here.
    Either way the shared cache is written once (store.save_hcache, first writer wins) and this run keeps the set
    it judges with, which the read stage pins in the case's own folder."""
    claim = store.claim_build(key_h)
    try:
        if claim is None:
            got = store.wait_hcache(key_h, H_WAIT_S)
            if got is not None:
                logger.info("criteria %s: reused the set another run built", key_h)
                return got, False
        return build(), True
    finally:
        store.release_build(claim)


def build_h(gspans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
            procedure: Optional[Procedure] = None, progress: Optional[Callable[[str], None]] = None) -> CriteriaSet:
    """Step H in the mode STEP_H names (loose by default); see CLAUDE.md. `progress` gets the status page's short
    lines (loose reports its first pass and its audit; the other modes the start only)."""
    mode = step_h()
    if mode not in ("loose", "loose-next") and progress:
        progress("Building the checklist from the whole guideline")
    if mode == "loose-loop":
        from . import reduce_loop
        return reduce_loop.build(gspans, n, sel, key, run_id, procedure)
    if mode == "loose-next":
        from . import reduce_next
        return reduce_next.build(gspans, n, sel, key, run_id, procedure, progress=progress)
    if mode == "script":
        from . import reduce_script
        return reduce_script.build(gspans, n, sel, key, run_id, procedure)
    if mode == "tools":
        from . import reduce_tools
        return reduce_tools.build(gspans, n, sel, key, run_id, procedure)
    if mode in ("code", "form"):
        from . import reduce_code
        return reduce_code.build(gspans, n, sel, key, run_id, procedure)
    return criteria.build(gspans, n, sel, key, run_id, procedure, progress=progress)


def negated_leaves(e) -> set[str]:
    """Leaf ids that sit under an odd number of `not`s."""
    out: set[str] = set()

    def walk(x, neg):
        if isinstance(x, str):
            if neg:
                out.add(x)
            return
        (op, arg), = x.items()
        if op == "not":
            walk(arg, not neg)
        elif op == "at_least":
            for y in arg["of"]:
                walk(y, neg)
        else:
            for y in arg:
                walk(y, neg)
    walk(e, False)
    return out


# ---------------------------------------------------------------- A2: the record only


def chart_labels(chart_id: str, rspans: list[Span]) -> dict[str, str]:
    """A2's label per chart line when sections.json was made from these same lines; {} otherwise."""
    out = store.load_sections(chart_id, _lines_sha(rspans))
    return sections.labels(out, rspans) if out is not None else {}


def _lines_sha(rspans: list[Span]) -> str:
    return hashlib.sha256("\n".join(f"{s.id} {s.text}" for s in rspans).encode()).hexdigest()


def doing(st: Recorder, s) -> Callable[[str], None]:
    """A `progress` callback for a stage: sets its `doing` line and saves the status at once (the heartbeat saves it
    again every few seconds)."""
    def say(line: str) -> None:
        s.doing = line
        st.save()
    return say


def evidence_for(chart_id: str, rspans: list[Span], run_id: str,
                 progress: Optional[Callable[[str], None]] = None) -> tuple[list[Span], dict]:
    """The chart's evidence lines (step A2), cached per chart: the judge never reads the clinic's summaries or the
    planned-procedure block. Also the label counts, for the status and the case document."""
    sha = _lines_sha(rspans)
    model = llm.pick_models()[0]
    hint = hints.clinic_id(rspans)                            # the clinic structure hint A2 is given (app/hints.py)
    out = store.load_sections(chart_id, sha, model=model, hint=hint)   # another model's or hint's labels are a miss
    cached = out is not None
    if out is None:
        if progress:                      # one model call reads the whole chart
            pages = len({s.page for s in rspans}) or 1
            progress(f"Reading {pages} page{'s' if pages != 1 else ''} of the case")
        out = sections.split(rspans, run_id)
        store.save_sections(chart_id, sha, out, model=model, hint=hint)
    lab = sections.labels(out, rspans)
    counts = {k: sum(1 for v in lab.values() if v == k) for k in ("evidence", "summary", "order", "admin")}
    counts["unlabelled"] = len(rspans) - sum(counts.values())
    counts["cached"] = cached
    return sections.evidence(out, rspans), counts


# ---------------------------------------------------------------- precompute at upload (PRECOMPUTE_H=1, default off)


def precompute(gid: str, run_id: Optional[str] = None) -> dict:
    """Build the checklist for every covered indication of a guideline ahead of any chart, so the first chart's wait
    drops from the H build (1-2 min) to the judge (~30 s). Off unless PRECOMPUTE_H=1 (the owner decides the spend).
    Step C runs once with no order (cached by cache_key(sha, Procedure())); H runs per pathway under the order-less
    H key (h_cache_key(..., None), `-onone`). Resume reads only the order's own H key (H's prompt and tree carry the
    order), so these trees are never served to a case: today precompute only warms the order-less C and H entries,
    which no order with a code, target, ICD code or plan reads. Hence off by default. Returns {pathways, built,
    cached}."""
    gspans, sha, _ = store.load_guideline_spans(gid)
    run_id = run_id or llm.new_run_id()
    proc = Procedure()
    key = cache_key(sha, proc, gspans)
    n, _ = store.load_criteria(key)
    if n is None:
        n = narrow.narrow(gspans, proc, gid, sha, key, run_id)
        n, _ = store.save_criteria(key, n, None)
    built, cached = [], []
    for p in n.pathways:
        key_h = h_cache_key(sha, n, [p.id], None, gspans)       # order-less: never read by resume
        if store.load_hcache(key_h) is not None:
            cached.append(p.id)
            continue
        sel = Selection(applies=True, pathways=[Pick(code=p.codes[0] if p.codes else "", pathway=p.id, how="code" if p.codes else "name")],
                        ranges=p.spans)
        store.save_hcache(key_h, build_h(gspans, n, sel, key_h, run_id, proc))
        built.append(p.id)
    logger.info("precompute %s: %d pathway(s), built %s, cached %s", gid, len(n.pathways), built, cached)
    return {"pathways": [p.id for p in n.pathways], "built": built, "cached": cached}


def precompute_wanted() -> bool:
    return os.environ.get("PRECOMPUTE_H", "0") == "1"


# ---------------------------------------------------------------- run


def run(chart_text: str, chart_id: str, gid: str, override: Optional[dict] = None, filename: str = "chart.pdf",
        source: str = "api", order: Optional[Order] = None, rspans: Optional[list[Span]] = None,
        status: Optional[Recorder] = None, pause_at_pathways: bool = False) -> Optional[Result]:
    """`status` records each stage (app/status.py) as it runs; a fresh persisting recorder when none is given, so
    every check, browser or CLI, leaves a status.json beside its result.

    `pause_at_pathways`: stop after the section stage whenever there is a section to pick (every code passed the
    code gate, whether or not the guideline reader chose one) and wait for a person to confirm it: selection.json is
    written, the status is `paused` at the `confirm_pathways` gate, and None is returned; `resume` continues. A code
    stopped at the code gate does not pause: it runs to its NOT_COVERED / CANT_CHECK result as always. Before that,
    an order with 2+ codes pauses on the order stage at the `pick_code` gate (one code, one pathway; app/onecode.py):
    C has not run; onecode.pick continues from C with the one code a person picked."""
    st = status or Recorder(chart_id, gid, filename, override, source)
    run_id = llm.new_run_id()
    st.set_run(run_id)
    with st.stage("chart") as s:
        rspans = rspans or split_chart(chart_text)
        store.save_chart(chart_id, filename, rspans, source=source)
        s.summary = _chart_summary(rspans, filename)
    logger.info("check chart %s against %s: %d spans, run %s", chart_id, gid, len(rspans), run_id)
    with st.stage("order", step="detect_order") as s:
        s.cached = order is not None
        order = order or detect_order(rspans, chart_id, run_id)
        order = apply_override(order, override)
        store.save_order(order)
        s.summary = _order_summary(order)
        st.doc["order"] = {"patient_name": order.patient_name, "procedure_text": order.procedure.as_written,
                           "cpt": order.procedure.cpt, "payer": order.payer}
        # one code, one pathway (app/onecode.py): the review flow asks which code before C when the order has 2+
        picking = pause_at_pathways and len(dict.fromkeys(order.procedure.cpt)) >= 2
        if picking:
            from . import onecode
            onecode.gate(s, chart_id, gid, order, rspans)
    if picking:
        st.pause("order", {"stage": "guideline", "needs": "code", "endpoint": f"/api/review/{chart_id}/code"})
        logger.info("chart %s paused at the code gate (run %s): %s", chart_id, run_id, ", ".join(order.procedure.cpt))
        return None
    return from_guideline(st, chart_id, gid, override, order, rspans, run_id, pause_at_pathways)


def from_guideline(st: Recorder, chart_id: str, gid: str, override: Optional[dict], order: Order, rspans: list[Span],
                   run_id: str, pause_at_pathways: bool = False) -> Optional[Result]:
    """C onward (run's tail; onecode.pick continues here once a person picked the code)."""
    with st.stage("guideline", step="narrow_guideline") as s:
        gspans, sha, gname = store.load_guideline_spans(gid)
        cached = store.load_criteria(cache_key(sha, order.procedure, gspans))[0] is not None
        n, cs, key = narrowed_for(gid, gspans, sha, order, run_id)
        _hints_meta(st, gspans, rspans)
        s.cached = cached
        s.summary = _guideline_summary(n, gname)
        if n.problems:
            s.gate("guideline_problems", "Part of the guideline could not be read cleanly for this order. Open "
                   "“How this was decided” before relying on the result.", options=n.problems,
                   action={"recheck": {"field": "guideline_id"}})
    with st.stage("section") as s:
        sel = select(n, order, gspans)
        s.summary = _section_summary(n, sel, gspans)
        pausing = pause_at_pathways and sel.applies and all(g.outcome == "judge" for g in sel.code_gate)
        _section_gates(s, n, sel, order, gspans, which_section=not pausing)
        if pausing:
            names = list(dict.fromkeys(pathway_name(n, p.pathway, gspans) for p in sel.pathways))
            needs = "Confirm which indication of the guideline this order is checked under."
            if not sel.pathways:
                needs += " The guideline reader chose none; pick one."
            s.gate("confirm_pathways", needs, options=names,
                   action={"confirm": {"endpoint": f"/api/review/{chart_id}/pathways"}})
    if pausing:
        store.save_selection(chart_id, sel)
        st.pause("section", {"stage": "checklist", "needs": "pathways", "key": key,
                             "endpoint": f"/api/review/{chart_id}/pathways"})
        logger.info("chart %s paused at the section gate (run %s): %s", chart_id, run_id,
                    "; ".join(f"{p.code}->{p.pathway}" for p in sel.pathways) or "nothing chosen")
        return None
    verdicts: dict[str, Verdict] = {}
    jreasons: dict[str, list[str]] = {}
    judged = sel.applies and all(g.outcome == "judge" for g in sel.code_gate) and sel.pathways
    if judged:
        with st.stage("checklist", step="criteria_guideline") as s:
            had = cs is not None and set(criteria.picked(sel)) <= {e.pathway for e in cs.expressions}
            cs = criteria_for(gspans, n, sel, cs, key, run_id, order.procedure, doing(st, s))
            ids, asked = _checklist(s, n, sel, cs, gspans, cached=had, chart_id=chart_id)
            _tree_meta(st, cs, key)
        return _judge_and_decide(st, chart_id, gid, override, order, n, sel, cs, ids, asked, gspans, rspans, run_id)
    for sid in ("checklist", "record", "read", "verify"):
        st.skip(sid, "Not run: " + (sel.reason or "no section was chosen").rstrip(".") + ".")
    store.drop_case_criteria(chart_id)        # nothing judged: no checklist belongs to this case now
    return _decide(st, chart_id, gid, override, order, n, sel, None, verdicts, jreasons, gspans, rspans, run_id)


# ---------------------------------------------------------------- H .. K-L, shared by run and resume


def _checklist(s, n: Narrowed, sel: Selection, cs: CriteriaSet, gspans: list[Span], cached: bool,
               chart_id: Optional[str] = None) -> tuple[list[str], list[str]]:
    """Inside the checklist stage, once the CriteriaSet is at hand: (every requirement id the picked pathways use,
    the ones a chart can answer); the stage's summary, cached flag and problems gate. Admin leaves this case prunes
    (app/admin.py) are in neither: never sent to the judge."""
    pruned = admin.applied(chart_id, cs, criteria.picked(sel))
    expr = {e.pathway: e.expr for e in pruned.expressions}
    ids = list(dict.fromkeys(i for p in criteria.picked(sel) if p in expr for i in leaf_ids(expr[p])))
    crit = cs.criterion_map()
    asked = [i for i in ids if i in crit and crit[i].answerable]
    s.cached = cached
    s.summary = f"{len(ids)} requirement(s) under “{pathway_name(n, criteria.picked(sel)[0], gspans)[:80]}”" \
        if criteria.picked(sel) else "No requirements to build"
    if cs.status == "needs_review":
        s.gate("checklist_problems", "The requirements for this indication could not be fully built from the "
               "guideline; read the indication under “How this was decided” before relying on the checklist.",
               options=cs.problems)
    return ids, asked


def _hints_meta(st: Recorder, gspans: list[Span], rspans: list[Span]) -> None:
    """Which structure hints this check's prompts carry (app/hints.py; names, None when none applied): `hints`
    {payer, clinic} on the status document. The payer hint reaches H only in HINT_MODES."""
    st.doc["hints"] = {"payer": hints.payer_hint(gspans)[0] if step_h() in HINT_MODES else None,
                       "clinic": hints.clinic_hint(rspans)[0]}


def _tree_meta(st: Recorder, cs: CriteriaSet, key: str) -> None:
    """What this case's checklist was built with, on the status document, so a sign-off or an accept can record the
    exact tree it was made on: the criteria cache key, the step-H mode, the model, the audit's findings and notes."""
    st.doc["tree"] = {"criteria_key": key, "step_h": step_h(), "model": llm.pick_models()[0],
                      "run_id": cs.run_id, "criteria": len(cs.criteria), "loopholes": list(cs.loopholes),
                      "notes": cs.notes, "status": cs.status}
    st.save()


def _judge_and_decide(st: Recorder, chart_id: str, gid: str, override: Optional[dict], order: Order, n: Narrowed,
                      sel: Selection, cs: CriteriaSet, ids: list[str], asked: list[str], gspans: list[Span],
                      rspans: list[Span], run_id: str) -> Result:
    """Stages read (I), verify (J) and decide (K-L) over a built checklist; saves the result and closes the status."""
    crit = cs.criterion_map()
    verdicts: dict[str, Verdict] = {}
    with st.stage("record", step="chart_sections") as s:
        ev, counts = evidence_for(chart_id, rspans, run_id, doing(st, s))
        doing(st, s)(f"{counts['evidence']} lines of record, {counts['summary']} of summaries, {counts['order']} of the request")
        s.cached = counts["cached"]
        s.summary = (f"{counts['evidence']} of {len(rspans)} lines are the record; "
                     f"{counts['summary']} are the clinic's summaries, {counts['order']} the request")
        st.doc["sections"] = counts
    with st.stage("read", step="judge_chart") as s:
        doing(st, s)(f"Checking {len(asked)} requirement{'s' if len(asked) != 1 else ''} against {len(ev)} lines of the record")
        if asked:
            verdicts = judge.judge(ev, cs, asked, gspans, order, run_id, hint=hints.clinic_hint(rspans)[1])
            pruned = admin.split(chart_id, cs, criteria.picked(sel))[1]
            verdicts = {k: v for k, v in verdicts.items() if k not in pruned}   # never one for a leaf not asked
        store.save_case_criteria(chart_id, cs)   # the exact checklist this case is judged with: readers prefer it
        s.summary = f"{sum(1 for i in asked if i in verdicts)} of {len(asked)} requirement(s) answered" if asked \
            else "Nothing a case can show; every requirement is confirmed outside the case"
    with st.stage("verify") as s:
        doing(st, s)("Checking quotes and dates")
        jreasons = judge.verify(verdicts, ev, cs, asked, gspans, chart_labels(chart_id, rspans))
        expr = {e.pathway: e.expr for e in cs.expressions}
        negated = {i for p in criteria.picked(sel) if p in expr for i in negated_leaves(expr[p])}
        for i in ids:   # a chart cannot show it: never decided here, always a person's check (policy B)
            if i in crit and not crit[i].answerable:
                # set so the tree does not stop on it: satisfied where it is required, absent where it is excluded
                verdicts[i] = Verdict(criterion=i, status="NOT_MET" if i in negated else "MET", confidence=1.0,
                                      rationale="A case cannot show this; confirm it outside the case.")
        s.summary = _verify_summary(verdicts, jreasons)
    return _decide(st, chart_id, gid, override, order, n, sel, cs, verdicts, jreasons, gspans, rspans, run_id)


def _decide(st: Recorder, chart_id: str, gid: str, override: Optional[dict], order: Order, n: Narrowed, sel: Selection,
            cs: Optional[CriteriaSet], verdicts: dict[str, Verdict], jreasons: dict[str, list[str]], gspans: list[Span],
            rspans: list[Span], run_id: str) -> Result:
    with st.stage("decide") as s:
        # a person's strikes on this case (app/strikes.py) take their requirements out of the logic; none: cs itself
        pids = [p.pathway for p in sel.pathways]
        # admin leaves (billing, paperwork, headings: app/admin.py) are pruned first, then the strikes; a leaf a
        # person restored ("Ask it anyway") stays, with the verdict its own judge call gave
        used = admin.applied(chart_id, cs, pids)
        v_dec, j_dec = admin.verdicts(chart_id, cs, verdicts, jreasons)
        used = strikes.applied(chart_id, used, gspans, pids)
        # lines a person added to this case's checklist (app/additions.py) join as one more AND term, with the
        # verdicts their ask judged; the stored verdicts stay the judge's own
        used, v_all, j_all, _ = additions.extend(chart_id, used, v_dec, j_dec, pids)
        r = decide(order, n, sel, used, v_all, j_all, gspans, rspans, run_id)
        store.save_result(chart_id, sel, verdicts, r, gid, override, jreasons)
        s.summary = r.reason or {"ready": "Ready to submit."}.get(r.queue, "")
        if r.queue != "ready":
            s.gate("review", r.reason, options=r.review_reasons)
    st.close()
    logger.info("result %s (%s) for chart %s via %s, confidence %.2f, %d miss(es)%s", r.determination, r.queue, chart_id,
                r.pathway_used or "-", r.confidence, len(r.misses),
                f"; review: {' | '.join(r.review_reasons)}" if r.review_reasons else "")
    return r


# ---------------------------------------------------------------- resume after the section gate


def _as_pick(x) -> tuple[str, str]:
    if isinstance(x, Pick):
        return x.code, x.pathway
    return str((x or {}).get("code") or "").strip(), str((x or {}).get("pathway") or "").strip()


def resume(chart_id: str, picks: Optional[list[dict]] = None, by: Optional[str] = None,
           status: Optional[Recorder] = None) -> Result:
    """Continue a check a person answered at the section gate. `picks` = [{"code", "pathway"}] (each pathway one of
    the guideline's, each code one of the order's codes that passed the code gate); the status must be `paused`.
    A `failed` check whose pathways.json exists (a resume that raised) is re-run from its stored picks when none
    are given: that is how retry works after confirmation. A, B and C are not re-run: the chart, the order, the
    narrowed guideline and the model's selection are read from disk."""
    doc = status.doc if status is not None else load_status(chart_id)
    if doc is None:
        raise ValueError("not paused")
    conf = store.load_confirmation(chart_id)
    if doc.get("state") == "paused":
        pass
    elif doc.get("state") == "failed" and (conf or picks):
        pass
    else:
        raise ValueError("not paused")
    if not picks:
        picks = (conf or {}).get("confirmed") or []
        by = by if by is not None else (conf or {}).get("by")
    if not picks:
        raise ValueError("pick at least one section")
    gid = doc["guideline_id"]
    key = (doc.get("resume") or {}).get("key") or (conf or {}).get("narrowed_key")
    if not key:
        raise ValueError("not paused")
    run_id = doc.get("run_id") or llm.new_run_id()

    # what A-C left on disk
    rspans = store.load_chart_spans(chart_id)
    order = store.load_order(chart_id)
    gspans, sha, gname = store.load_guideline_spans(gid)
    n, cs0 = store.load_criteria(key)
    if order is None or n is None:
        raise ValueError("the order or the guideline reading for this check is gone; run the check again")
    rec = store.load_result(chart_id) if (store.RESULTS / chart_id / "result.json").exists() else {}
    sel_path = store.RESULTS / chart_id / "selection.json"
    sel0 = Selection.model_validate_json(sel_path.read_text()) if sel_path.exists() else \
        Selection.model_validate(rec["selection"]) if rec.get("selection") else None
    if sel0 is None:
        raise ValueError("no selection was saved for this check; run it again")

    # the picks
    pairs = list(dict.fromkeys(_as_pick(p) for p in picks))
    pw = {p.id: p for p in n.pathways}
    codes = [g.code for g in sel0.code_gate]
    bad_p = sorted({p for _, p in pairs if p not in pw})
    bad_c = sorted({c for c, _ in pairs if c not in codes})
    if bad_p or bad_c:
        raise ValueError("; ".join(x for x in [f"unknown section(s): {', '.join(bad_p)}" if bad_p else "",
                                                f"code(s) not in this order: {', '.join(bad_c)}" if bad_c else ""] if x))
    confirmed = [{"code": c, "pathway": p} for c, p in pairs]
    suggested = [{"code": p.code, "pathway": p.pathway} for p in sel0.pathways]
    pathways = [Pick(code=c, pathway=p, how="code" if c in pw[p].codes else "name") for c, p in pairs]
    pids = list(dict.fromkeys(p for _, p in pairs))
    pos = {s.id: i for i, s in enumerate(gspans)}
    ranges = [r for pid in pids for r in pw[pid].spans] + list(n.guideline.always_on)
    ranges = sorted({(r.first, r.last): r for r in ranges}.values(), key=lambda r: pos.get(r.first, 0))
    reasons = [x for x in sel0.reasons if not x.startswith("Which indication covers CPT")]
    if {(c, p) for c, p in pairs} != {(p.code, p.pathway) for p in sel0.pathways}:
        names = "; ".join(dict.fromkeys(pathway_name(n, p, gspans) for p in pids))
        was = list(dict.fromkeys(pathway_name(n, p.pathway, gspans) for p in sel0.pathways))
        reasons.append(f"The indication was chosen by {(by or '').strip() or 'a person'}: “{names}” "
                       + (f"(the guideline reader suggested “{'; '.join(was)}”)." if was else "(the guideline reader suggested nothing)."))
    sel = Selection(applies=True, reason=sel0.reason, code_gate=sel0.code_gate, pathways=pathways, ranges=ranges,
                    reasons=reasons, candidates={})
    key_h = h_cache_key(sha, n, pids, order.procedure, gspans)     # the order is in H's prompt, so in its key
    store.save_confirmation(chart_id, {"chart_id": chart_id, "run_id": run_id, "guideline_id": gid, "guideline_sha": sha,
                                       "narrowed_key": key, "suggested": suggested, "confirmed": confirmed, "by": by,
                                       "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "h_key": key_h})

    # the recorder picks up where it paused, same run_id
    st = status if status is not None else Recorder.from_doc(doc)
    if st.doc.get("run_id") != run_id:
        st.doc["run_id"] = run_id
    st.answer("section", by, confirmed, suggested)
    _hints_meta(st, gspans, rspans)
    logger.info("resume chart %s (run %s): %s confirmed by %s", chart_id, run_id,
                "; ".join(f"{c}->{p}" for c, p in pairs), by or "a person")

    # H, cached by the confirmed pathways and this order's facts (never another order's tree)
    with st.stage("checklist", step="criteria_guideline") as s:
        covers = lambda c: c is not None and set(pids) <= {e.pathway for e in c.expressions}
        cs = store.load_hcache(key_h)
        built = False
        if not covers(cs):
            if covers(cs0):
                cs = cs0                      # the model's own cache for the same pick
                logger.info("criteria %s: from the order's cache %s", key_h, key)
            else:
                cs, built = shared_h(key_h, lambda: build_h(gspans, n, sel, key_h, run_id, order.procedure, doing(st, s)))
            if store.save_hcache(key_h, cs) is not cs and built:
                logger.info("criteria %s: another run wrote the cache first; this case keeps its own set", key_h)
        else:
            logger.info("criteria %s: from the cache", key_h)
        if not covers(cs0) and {p for _, p in pairs} == {p.pathway for p in sel0.pathways}:
            store.save_criteria(key, n, cs)   # the same pick as the model's: fill its cache so the tree view reads it
        ids, asked = _checklist(s, n, sel, cs, gspans, cached=not built, chart_id=chart_id)
        _tree_meta(st, cs, key_h)
    return _judge_and_decide(st, chart_id, gid, doc.get("override"), order, n, sel, cs, ids, asked, gspans, rspans, run_id)


def no_section(chart_id: str, by: Optional[str] = None) -> Result:
    """At the section gate a person judged that no indication of this guideline fits the order ("None of these"): the
    check ends without a checklist (H, I, J skipped), the result is "can't check against this guideline" with the
    person's name, and nofit.json records who and when, so the page reads "This guideline doesn't apply" and offers
    the other guidelines on file (POST /api/review/{id}/recheck). No model call."""
    doc = load_status(chart_id)
    if not doc or doc.get("state") != "paused":
        raise ValueError("not paused")
    gid, key = doc["guideline_id"], (doc.get("resume") or {}).get("key") or ""
    order = store.load_order(chart_id)
    sel_path = store.RESULTS / chart_id / "selection.json"
    if order is None or not sel_path.exists():
        raise ValueError("the order or the selection for this check is gone; run the check again")
    sel0 = Selection.model_validate_json(sel_path.read_text())
    who = (by or "").strip() or None
    suggested = [{"code": p.code, "pathway": p.pathway} for p in sel0.pathways]
    st = Recorder.from_doc(doc)
    st.answer("section", who, [], suggested)
    store.drop_case_criteria(chart_id)
    for sid in ("checklist", "record", "read", "verify"):
        st.skip(sid, "Not run: no indication of this guideline fits the order.")
    sel = Selection(applies=False, reason="No section of this guideline fits this order", code_gate=sel0.code_gate)
    with st.stage("decide") as s:
        r = Result(order_id=order.id or chart_id, guideline_id=gid, determination="CANT_CHECK", queue="cant_check",
                   reason=f"{who or 'A person'} judged that no indication of this guideline fits this order; check it "
                          f"against another guideline.", run_id=doc.get("run_id"))
        store.save_result(chart_id, sel, {}, r, gid, doc.get("override"), {})
        s.summary = r.reason
    st.close()
    n, _ = store.load_criteria(key)
    gspans = store.load_guideline_spans(gid)[0]
    names = list(dict.fromkeys(pathway_name(n, p["pathway"], gspans) for p in suggested)) if n else []
    (store.RESULTS / chart_id / "nofit.json").write_text(json.dumps(
        {"by": who, "at": time.strftime("%Y-%m-%dT%H:%M:%S"), "guideline_id": gid, "suggested": suggested,
         "suggested_names": names}, indent=2))
    logger.info("chart %s: no section of %s fits (by %s)", chart_id, gid, who or "a person")
    return r


# ---------------------------------------------------------------- stage summaries (plain words, for the status screen)


def _chart_summary(rspans: list[Span], filename: str) -> str:
    pages = len({s.page for s in rspans}) or 1
    return f"{len(rspans)} lines over {pages} page{'s' if pages != 1 else ''} from {filename}"


def _order_summary(o: Order) -> str:
    p = o.procedure
    proc = (p.as_written or "procedure not named") + (f" ({', '.join(p.cpt)})" if p.cpt else " (no code written)")
    return " · ".join(x for x in [o.patient_name or "patient not named", proc, o.payer or "payer not named"])


def _guideline_summary(n: Narrowed, gname: str) -> str:
    payer = n.guideline.payer.name or gname or n.guideline.id
    return f"{payer}: {len(n.pathways)} section(s) that grant coverage, {len(n.codes)} code(s) in the table"


def _section_summary(n: Narrowed, sel: Selection, gspans: list[Span]) -> str:
    if not sel.applies:
        return sel.reason
    tag = {"covered": "covered", "non_covered": "not covered", "investigational": "investigational",
           "not_addressed": "decided elsewhere", None: "not in the code table"}
    codes = "; ".join(f"Code {g.code} is {tag.get(g.tag, g.tag)}" + (" (matched from the procedure name)" if g.mapped else "")
                      for g in sel.code_gate)
    if sel.pathways:
        names = list(dict.fromkeys(pathway_name(n, p.pathway, gspans) for p in sel.pathways))
        return f"{codes}; section: {'; '.join(names)}"
    return f"{codes}; no section chosen" if sel.candidates else codes


def _section_gates(s, n: Narrowed, sel: Selection, order: Order, gspans: list[Span], which_section: bool = True) -> None:
    """`which_section=False` when the check pauses for a person to confirm the section: the pause gate replaces it."""
    mapped = [g for g in sel.code_gate if g.mapped]
    if mapped:
        written = ", ".join(order.procedure.cpt) or "no code"
        s.gate("confirm_code", f"The case gives {written}; the procedure was matched to {mapped[0].code} from its "
               f"name (“{(n.mapped_cpt.description if n.mapped_cpt else '')[:120]}”). Confirm the code.",
               options=[g.code for g in mapped], action={"recheck": {"field": "cpt"}})
    if which_section and sel.applies and not sel.pathways and sel.candidates and all(g.outcome == "judge" for g in sel.code_gate):
        names = list(dict.fromkeys(pathway_name(n, p, gspans) for ids in sel.candidates.values() for p in ids))
        what = order.procedure.target or order.procedure.as_written or "the procedure"
        s.gate("which_section", f"The order does not say which indication of the guideline it falls under ({what}). "
               "Which of these is the procedure for?", options=names, action={"recheck": {"field": "target"}})


def _verify_summary(verdicts: dict[str, Verdict], jreasons: dict[str, list[str]]) -> str:
    dates = sum(1 for v in verdicts.values() for d in v.dates if d.iso)
    flagged = sum(len(x) for x in jreasons.values())
    quotes = sum(len(v.for_) + len(v.against) for v in verdicts.values())
    out = f"{quotes} quote(s) found in the case, {dates} date(s) verified"
    return out + (f"; {flagged} thing(s) to check by hand" if flagged else "")


def recheck(chart_id: str, override: Optional[dict] = None) -> Result:
    """Re-run with the stored order plus the coordinator's corrections (cpt, target, guideline_id)."""
    meta = store.load_result(chart_id).get("meta", {})
    merged = dict(meta.get("override") or {})
    merged.update({k: v for k, v in (override or {}).items() if v not in (None, "", [])})
    gid = merged.get("guideline_id") or meta.get("guideline_id")
    meta_c = store.chart_meta(chart_id)
    return run("", chart_id, gid, override=merged, filename=meta_c.get("filename") or "chart.pdf",
               source=meta_c.get("source", "api"), order=store.load_order(chart_id),
               rspans=store.load_chart_spans(chart_id))
