"""Step H as a coding agent (STEP_H=code) or its no-sandbox form (STEP_H=form). Drop-in for criteria.build.

    in:  every g-span; the confirmed indication (its lines); the order (+ age/sex when known); the order's code rows
    code (STEP_H=code): a sandbox with guideline.txt, order.json, codes.json, helpers.py, BRIEF.md; the model writes
         tree.py with helpers (C checks each quote as written, block for shared groups, write checks ids / leaves /
         usage / the expression), runs it, fixes, re-runs; then one audit turn in the same sandbox (add-only)
    form (STEP_H=form): the same tree as one JSON answer; the host runs the same helpers checks and sends problems back
    host: never trusts the sandbox: tree.json is downloaded and re-checked with the same helpers (quotes found in the
          guideline, ids, leaves, usage, expression), then through criteria.check (refs located, logic parsed);
          problems go back for up to ROUNDS rounds, then status needs_review. The audit may only add: a condition its
          tree drops is put back at the top. Answerable=false conditions stay in the tree (the pipeline makes them
          review reasons, never MET or NOT_MET).

Policies (spec 3.2) are flags, default on: REDUCE_POLICY_A / _C / _D / _E = 1|0.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from app.checklist import criteria
from app.core import llm, log
from app.checklist.criteria import AOut, HOut, _and_back, _dropped, _merge, picked
from app.decide.evaluate import leaf_ids
from app.core.models import Code, CriteriaSet, Narrowed, Procedure, Selection, Span
from .sandbox import helpers
from app.ingest.spans import in_range

logger = log.get("reduce_code")

ROUNDS = 3
SANDBOX = Path(__file__).resolve().parent / "sandbox"


# ---------------------------------------------------------------- inputs


def guideline_text(spans: list[Span]) -> str:
    """The guideline as plain text: each line as extracted (indent kept), a blank line where there was one, a
    `--- page N ---` marker where a page starts. No ids: the host finds where each quote is printed."""
    out, page = [], None
    for s in spans:
        if s.page != page:
            out.append(f"--- page {s.page} ---")
            page = s.page
        if s.blank_before:
            out.append("")
        out.append(s.text)
    return "\n".join(out) + "\n"


def indication_text(n: Narrowed, pid: str, spans: list[Span], given: Optional[str] = None) -> str:
    """The confirmed indication as the model sees it: the given text alone (the runner's heading arm), else the
    lines of the confirmed pathway (the product: C picked them), else FIND (the model finds it)."""
    if given:
        return given
    p = next((x for x in n.pathways if x.id == pid), None)
    if p is None or not p.spans:
        return FIND
    lines = [s.text for r in p.spans for s in in_range(spans, r)]
    return f"`{pid}`" + (f" (about {', '.join(p.targets)})" if p.targets else "") + ":\n\n" + "\n".join(lines)


def order_json(p: Optional[Procedure], extra: Optional[dict] = None) -> str:
    d = {}
    if p is not None:
        d = {"procedure": p.as_written, "cpt": p.cpt, "treating": p.target, "diagnosis": p.diagnosis, "plan": p.plan}
    d.update({k: v for k, v in (extra or {}).items() if v not in (None, "")})
    return json.dumps({k: v for k, v in d.items() if v not in (None, "", [])}, indent=1)


def codes_json(codes: list[Code]) -> str:
    return json.dumps([{"code": c.code, "tag": c.tag, "row": c.description} for c in codes], indent=1)


def policies() -> str:
    """The policy bullets that are on (REDUCE_POLICY_X=0 drops bullet X and its continuation lines)."""
    text = llm.prompt("reduce/policies")
    out, skip = [], False
    for ln in text.splitlines():
        m = re.match(r"- \[([A-Z])\]", ln)
        if m:
            skip = os.environ.get(f"REDUCE_POLICY_{m.group(1)}", "1") == "0"
        elif not ln.startswith("  "):
            skip = False
        if not skip:
            out.append(ln)
    body = "\n".join(out)
    return "\n" + body + "\n" if re.search(r"- \[[A-Z]\]", body) else ""


def heading_of(ind: Optional[str]) -> str:
    """The given pathway as the instructions name it: the heading arm's text whole (a joined "lead-in ... item" too),
    else the first printed line of the pathway's lines."""
    if ind and " ... " in ind:
        return f"“{' '.join(ind.split())[:400]}”"
    lines = [x.strip() for x in (ind or "").splitlines() if x.strip() and not x.startswith("`")]
    return f"“{' '.join(lines[0].split())[:200]}”" if lines else "the indication given in the task"


def given_rule(ind: Optional[str]) -> str:
    """The given-pathway rule, every arm: reduce only this pathway, against the whole policy."""
    return llm.prompt("reduce/indication_given", heading=heading_of(ind))


def brief(find: bool = False, ind: Optional[str] = None) -> str:
    rule = llm.prompt("reduce/indication_find") if find else given_rule(ind)
    return llm.prompt("reduce/brief", policies=policies(), indication_rule=rule, plan_rule=llm.prompt("reduce/plan"),
                      sweep=llm.prompt("reduce/sweep"))


def sweep_note(before: set[str], after: set[str], lost: list[str]) -> str:
    """What the full-policy sweep changed, for notes (to measure what persistence buys)."""
    added, gone = sorted(after - before), sorted(before - after)
    out = "Sweep added: " + (", ".join(added) if added else "nothing")
    out += f"; removed: {', '.join(gone)}" if gone else ""
    return out + (f"; it dropped {', '.join(lost)}, put back (add-only)" if lost else "")


def _sweep_accept(old, new):
    """Add-only acceptance of the sweep's tree: (crit, exprs, lost). A leaf it drops is ANDed back at the top."""
    (crit, exprs), (c2, e2) = old, new
    lost = _dropped(exprs, e2)
    if lost:
        logger.warning("sweep dropped %s; put back", ", ".join(lost))
        e2 = [_and_back(e, exprs, lost) for e in e2]
        have = {c.id for c in c2}
        c2 = c2 + [c for c in crit if c.id in lost and c.id not in have]
    return c2, e2, lost


FIND = "Not given. Find the coverage indication(s) this order falls under yourself (BRIEF.md)."


# ---------------------------------------------------------------- tree -> CriteriaSet


def to_hout(tree: dict, pid: str) -> HOut:
    """A sandbox tree as step H's answer: conditions -> criteria, blocks expanded into one expression."""
    blocks = {b["name"]: b["expr"] for b in tree.get("blocks") or []}
    crit = [{"id": c["id"], "quote": c.get("quote") or "", "refs": [], "threshold": c.get("threshold"),
             "answerable": c.get("answerable", True), "question": c.get("question") or ""}
            for c in tree.get("conditions") or []]
    try:
        expr = helpers.expand(tree.get("expression"), blocks)
    except Exception:
        expr = tree.get("expression")
    return HOut.model_validate({"notes": tree.get("notes") or "", "criteria": crit,
                                "logic": [{"pathway": pid, "logic": expr}] if expr is not None else []})


def not_covered(quote: Optional[str], declared: bool) -> tuple[Optional[str], Optional[str]]:
    """(problem, note), the host rule in every arm: the not-covered flag only when no indication is declared. With an
    indication declared, a quoted not-covered sentence (usually "... who do not meet the criteria") goes to notes."""
    if not quote:
        return None, None
    if declared:
        return None, f"Not-covered sentence quoted, not raised (an indication is declared): “{quote[:300]}”"
    return f"the reducer reads this order as not covered: “{quote[:200]}”", None


def declared(tree: Optional[dict]) -> bool:
    return bool(tree) and (bool(tree.get("indication")) or tree.get("expression") is not None)


def verify(tree: Optional[dict], text: str, spans: list[Span], pid: str):
    """(problems, criteria, expressions): the helpers checks, then criteria.check (refs located, logic parsed)."""
    if tree is None:
        return ["no tree.json was written"], [], []
    problems = helpers.problems(tree, text)
    nc, _ = not_covered(tree.get("not_covered"), declared(tree))
    if nc:
        problems.append(nc)
    try:
        h = to_hout(tree, pid)
    except ValueError as e:          # a malformed threshold etc.: the problems go back to the model, never a crash
        if not problems:
            problems.append(f"the tree does not fit the schema: {str(e).splitlines()[0][:200]}")
        return problems, [], []
    p2, crit, exprs = criteria.check(h, spans, [pid])
    problems += [p for p in p2 if p not in problems and "QUOTE NOT FOUND" not in p]
    return problems, crit, exprs


def _load(body: Optional[bytes]) -> Optional[dict]:
    if not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


# ---------------------------------------------------------------- the two modes


def _code(spans, text, pid, order, codes, run_id, model, ind):
    find = ind == FIND
    # exactly these five files; nothing from the answer keys, the key's pathway names or any task map
    b = brief(find, ind)
    files = {"guideline.txt": text.encode(), "order.json": order.encode(), "codes.json": codes.encode(),
             "helpers.py": (SANDBOX / "helpers.py").read_bytes(), "BRIEF.md": b.encode()}
    s = llm.CodeSession(run_id, "criteria_code", files, model=model)
    try:
        s.turn(llm.prompt("reduce/task", order_json=order, indication=ind, brief=b))
        tree = _load(s.fetch("tree.json"))
        problems, crit, exprs = verify(tree, text, spans, pid)
        rounds = 1
        while problems and rounds < ROUNDS and not _only_not_covered(problems):
            s.turn(llm.prompt("reduce/fix", problems="\n".join(f"- {p}" for p in problems)))
            tree = _load(s.fetch("tree.json")) or tree
            problems, crit, exprs = verify(tree, text, spans, pid)
            rounds += 1
        swept = ""
        if tree is not None and not problems:      # the full-policy sweep: one more round, add-only
            s.turn(llm.prompt("reduce/sweep_code", sweep=llm.prompt("reduce/sweep")))
            try:
                t2 = _load(s.fetch("tree.json")) or tree
                p2, c2, e2 = verify(t2, text, spans, pid)
                if p2:
                    s.turn(llm.prompt("reduce/fix", problems="\n".join(f"- {p}" for p in p2)))
                    t2 = _load(s.fetch("tree.json")) or t2
                    p2, c2, e2 = verify(t2, text, spans, pid)
            except Exception as x:       # the sweep only adds; the first tree stands without it
                logger.warning("code sweep failed: %s", x)
                p2, swept = ["invalid"], "Sweep: output invalid, first tree stands"
            if p2 and not swept:
                swept = "Sweep: its tree failed the checks; the first tree stands"
            elif not p2:
                before = {c.id for c in crit}
                c2, e2, lost = _sweep_accept((crit, exprs), (c2, e2))
                swept = sweep_note(before, {c.id for c in c2}, lost)
                tree, crit, exprs = t2, c2, e2
        first = (tree, problems, crit, exprs)
        loopholes: list[str] = []
        if tree is not None:
            said = s.turn(llm.prompt("reduce/audit"))
            loopholes = [ln.strip("-• ").strip() for ln in said.splitlines()
                         if ln.strip() and ln.strip().upper() not in ("DONE", "NONE FOUND", "DONE.")][:20]
            t2 = _load(s.fetch("tree.json"))
            if t2 is not None and t2 != tree:
                p2, c2, e2 = verify(t2, text, spans, pid)
                if len(p2) <= len(problems):
                    lost = _dropped(exprs, e2)
                    if lost:
                        p2.append(f"the audit's tree left out {', '.join(lost)}; put back as required")
                        e2 = [_and_back(e, exprs, lost) for e in e2]
                        have = {c.id for c in c2}
                        c2 += [c for c in crit if c.id in lost and c.id not in have]
                    tree, problems, crit, exprs = t2, p2, c2, e2
        return first, (tree, problems, crit, exprs), loopholes, s.usage, s.cost(), swept
    finally:
        s.close()


def _only_not_covered(problems: list[str]) -> bool:
    return all("not covered" in p for p in problems)


def _form(spans, text, pid, order, codes, run_id, model, ind):
    from pydantic import BaseModel, Field

    class TOut(BaseModel):
        indication: Optional[str] = None
        not_covered: Optional[str] = None
        conditions: list[dict] = Field(default_factory=list)
        blocks: list[dict] = Field(default_factory=list)
        expression: object = None
        notes: str = ""

    b = brief(ind == FIND, ind)
    b = b[:b.index("## How to work")] if "## How to work" in b else b
    base = llm.prompt("reduce/form", brief=b, order_json=order, indication=ind, guideline=text)
    tally: dict = {}
    t = llm.call(run_id, "criteria_form", base, TOut, model=model, reasoning_effort="high", tally=tally)
    tree = t.model_dump()
    problems, crit, exprs = verify(tree, text, spans, pid)
    rounds = 1
    while problems and rounds < ROUNDS and not _only_not_covered(problems):
        t = llm.call(run_id, "criteria_form", criteria.retry_prompt(base, t, problems), TOut, model=model,
                     reasoning_effort="high", tally=tally)
        tree = t.model_dump()
        problems, crit, exprs = verify(tree, text, spans, pid)
        rounds += 1
    swept = ""
    if not problems:                               # the full-policy sweep: one more round, add-only
        sb = llm.prompt("reduce/sweep_form", base=base, tree=json.dumps(tree, indent=1), sweep=llm.prompt("reduce/sweep"))
        try:
            t2 = llm.call(run_id, "criteria_form_sweep", sb, TOut, model=model, reasoning_effort="high", tally=tally)
            p2, c2, e2 = verify(t2.model_dump(), text, spans, pid)
            if p2:
                t2 = llm.call(run_id, "criteria_form_sweep", criteria.retry_prompt(sb, t2, p2), TOut, model=model,
                              reasoning_effort="high", tally=tally)
                p2, c2, e2 = verify(t2.model_dump(), text, spans, pid)
        except Exception as x:           # the sweep only adds; the first tree stands without it
            logger.warning("form sweep failed: %s", x)
            p2 = ["invalid"]
            swept = "Sweep: output invalid, first tree stands"
        if p2 and not swept:
            swept = "Sweep: its tree failed the checks; the first tree stands"
        elif not p2:
            before = {c.id for c in crit}
            c2, e2, lost = _sweep_accept((crit, exprs), (c2, e2))
            swept = sweep_note(before, {c.id for c in c2}, lost)
            t, tree, crit, exprs = t2, t2.model_dump(), c2, e2
    first = (tree, problems, crit, exprs)
    # the add-only audit: the same prompt step H uses
    shown = {"criteria": [{"id": c.id, "quote": c.quote, "question": c.question} for c in crit],
             "logic": [{"pathway": e.pathway, "logic": e.expr} for e in exprs]}
    loopholes: list[str] = []
    try:
        a = llm.call(run_id, "criteria_audit", llm.prompt("criteria_audit", request=order, pathways=ind,
                                                          tree=json.dumps(shown, indent=1), guideline_spans=text),
                     AOut, model=model, reasoning_effort="high", tally=tally)
        loopholes = a.loopholes
        if a.criteria or a.logic:
            h = HOut(notes=tree.get("notes") or "", criteria=[criteria._C(id=c.id, quote=c.quote or "", refs=c.refs,
                     threshold=None, answerable=c.answerable, question=c.question) for c in crit],
                     logic=[{"pathway": e.pathway, "logic": e.expr} for e in exprs])
            p3, c3, e3 = criteria.check(_merge(h, a), spans, [pid])
            e3 = criteria.keep_missing(exprs, e3, p3)
            lost = _dropped(exprs, e3)
            if lost:
                p3.append(f"the audit's logic left out {', '.join(lost)}; put back as required")
                e3 = [_and_back(e, exprs, lost) for e in e3]
            keep = {c.id: c for c in crit}                 # first-pass criteria keep their typed thresholds
            c3 = [keep.get(c.id, c) for c in c3]
            problems, crit, exprs = problems + p3, c3, e3
    except Exception as x:
        logger.warning("form audit failed: %s", x)
        problems = problems + [f"audit failed: {type(x).__name__}"]
    return first, (tree, problems, crit, exprs), loopholes, tally, llm.dollars(tally), swept




# ---------------------------------------------------------------- build (the drop-in)


def build(spans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
          procedure: Optional[Procedure] = None, extra: Optional[dict] = None, mode: Optional[str] = None,
          indication: Optional[str] = None) -> CriteriaSet:
    mode = mode or os.environ.get("STEP_H", "code")
    want = picked(sel)
    on = {c for p in n.pathways if p.id in want for c in p.codes} | {x.code for x in sel.code_gate}
    codes = [c for c in n.codes if c.code in on] or n.codes
    text = guideline_text(spans)
    order = order_json(procedure, extra)
    model = llm.pick_models()[0]
    all_crit, all_exprs, notes, loops, problems = [], [], [], [], []
    spend = {}
    for pid in want:
        ind = indication_text(n, pid, spans, indication)     # per call: rows run in threads
        run = _code if mode == "code" else _form
        first, (tree, probs, crit, exprs), loopholes, usage, cost, swept = run(spans, text, pid, order,
                                                                              codes_json(codes), run_id, model, ind)
        have = {c.id for c in all_crit}
        for c in crit:                     # one id shared by two indications: the first wording stands
            if c.id not in have:
                all_crit.append(c)
                have.add(c.id)
        all_exprs += exprs
        notes.append((tree or {}).get("notes") or "")
        notes.append(not_covered((tree or {}).get("not_covered"), declared(tree))[1] or "")
        notes.append(swept)
        ind = (tree or {}).get("indication")
        if ind:
            notes.append("Indication used: " + " | ".join([ind] if isinstance(ind, str) else ind))
        loops += loopholes
        problems += probs
        if usage:
            spend[pid] = {**usage, "dollars": cost}
    used = {i for e in all_exprs for i in leaf_ids(e.expr)}
    cs = CriteriaSet(key=key, criteria=[c for c in all_crit if c.id in used], expressions=all_exprs,
                     notes="\n\n".join(x for x in notes if x), loopholes=loops,
                     status="needs_review" if problems else "ok", problems=problems, run_id=run_id)
    logger.info("criteria (%s) %s: %d criteria, %d expressions, %d loophole(s), %s%s", mode, key, len(cs.criteria),
                len(cs.expressions), len(loops), cs.status,
                f", ${sum(v['dollars'] for v in spend.values()):.2f}" if spend else "")
    if spend:
        llm._log(run_id, "criteria_code-cost", spend)
    return cs
