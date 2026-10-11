"""Step H as a declarative tree script (STEP_H=script). Drop-in for criteria.build. Spec: guideline-reduce
experiments/swarm/V12_SCRIPT_SPEC.md.

    in:  as STEP_H=tools (the whole guideline without ids, the allow-listed order, its code rows in full)
    session: tools find, read (as v1.2-tools), check(script), submit(script). The model writes the whole tree as a
         short Python-like script; the host PARSES it with `ast` against a whitelist (never runs it), checks all of
         it and returns every error with its line number. Fixing = editing the script and sending it again. Caps:
         MAX_ROUNDS check/submit calls, MAX_CALLS tool calls in all, then needs_review with the last errors. The
         first passing submit is not accepted: the host asks for the full-policy sweep (SWEEP_NEXT) and accepts the
         next passing submit; if a cap ends the session first, the first passing script stands
    audit: a second session gets the final script; its script is accepted only if it keeps every condition and
         indication and no indication's logic loses a leaf (add-only); otherwise the first script stands
    out: CriteriaSet; indications ORed into the confirmed pathway's expression; `script` = the final script;
         removed_conditions = conditions in an earlier passing script that the final one dropped

Checks are citation and well-formedness only: quotes printed, names defined before use, ids unique, conditions used,
thresholds well formed, every indication has a printed grant and logic.
"""
from __future__ import annotations

import ast
import difflib
import json
from typing import Any, Optional

from app.checklist import criteria
from app.core import llm, log
from app.checklist.criteria import _T, picked
from app.decide.evaluate import leaf_ids
from app.core.models import CriteriaSet, Criterion, Expression, Narrowed, Procedure, Selection, Span
from .reduce_code import guideline_text, not_covered, order_json, sweep_note
from .reduce_tools import SWEEP_NEXT, State, codes_json, confirmed, given_step, user_message
from . import reduce_tools

logger = log.get("reduce_script")

MAX_ROUNDS = 25          # check + submit
MAX_CALLS = 60
AUDIT_ROUNDS = 10
AUDIT_CALLS = 60
OPS = {">=", ">", "<=", "<", "=="}
C_ARGS = ("id", "quote", "question", "threshold", "answerable")
IND_ARGS = ("id", "grant", "logic")


# ---------------------------------------------------------------- the tools the model sees (spec section 2)

TOOLS = {
    "find": reduce_tools.TOOLS["find"],
    "read": reduce_tools.TOOLS["read"],
    "check": {
        "description": (
            "Parse and check the whole script. Returns {\"ok\": true, \"summary\": {conditions, blocks, indications "
            "with expanded logic}} or {\"ok\": false, \"errors\": [\"line 7: quote not found: '...' (nearest g0141: "
            "'...')\", \"line 15: name 'pt_6wk' is not defined\", \"unused condition 'x'\"]}. Use it as often as you "
            "like.\nThe script is the state: to change anything (a quote, a threshold, a grouping, an indication) edit "
            "the script and `check` or `submit` the whole thing again. To remove a condition, delete its line and its "
            "uses; say why in `notes`."),
        "parameters": {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]}},
    "submit": {
        "description": ("The same checks as `check`; on ok the script is the answer and the session ends; otherwise "
                        "the errors."),
        "parameters": {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]}},
}


def schemas() -> list[dict]:
    return [{"name": n, **t} for n, t in TOOLS.items()]


# ---------------------------------------------------------------- parse (whitelist, never executed)


class Tree:
    """What a script declares, evaluated: conditions, blocks, indications (expressions in the v1.1 shape)."""

    def __init__(self):
        self.conds: dict[str, dict] = {}         # id -> {quote, refs, question, threshold, answerable, line}
        self.blocks: dict[str, Any] = {}         # variable -> expression (blocks expanded)
        self.inds: dict[str, dict] = {}          # id -> {grant, expr, line}
        self.not_covered: Optional[str] = None
        self.notes: list[str] = []

    def summary(self) -> dict:
        from .reduce_tools import show
        return {"conditions": [{"id": i, "lines": c["refs"][0] if c["refs"] else None, "quote": c["quote"]}
                               for i, c in self.conds.items()],
                "blocks": {k: show(v) for k, v in self.blocks.items()},
                "indications": {k: show(v["expr"]) for k, v in self.inds.items() if v["expr"] is not None}}


class _Err(Exception):
    def __init__(self, node, msg):
        super().__init__(f"line {getattr(node, 'lineno', '?')}: {msg}")


def _flat(op: str, kids: list) -> dict:
    out = []
    for k in kids:
        if isinstance(k, dict) and op in k:
            out += k[op]
        else:
            out.append(k)
    return {op: out}


def parse(script: str, st: State) -> tuple[list[str], Tree]:
    """(errors, tree). Every statement is checked; errors are collected, not raised one at a time."""
    errors: list[str] = []
    t = Tree()
    try:
        mod = ast.parse(script or "")
    except SyntaxError as e:
        return [f"line {e.lineno}: syntax error: {e.msg}"], t
    env: dict[str, tuple[str, Any]] = {}             # name -> ("cond", id) | ("block", expr)
    later = {n.targets[0].id: n.lineno for n in mod.body
             if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)}

    def const(node, what):
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)) or (
                isinstance(node, ast.Constant) and node.value is None):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) \
                and isinstance(node.operand.value, (int, float)):
            return -node.operand.value
        raise _Err(node, f"{what} must be a plain value")

    def args_of(call, names):
        if len(call.args) > len(names):
            raise _Err(call, f"{call.func.id}() takes at most {len(names)} arguments")
        out = dict(zip(names, call.args))
        for kw in call.keywords:
            if kw.arg not in names:
                raise _Err(kw.value, f"{call.func.id}() has no argument '{kw.arg}'")
            if kw.arg in out:
                raise _Err(kw.value, f"{call.func.id}() got '{kw.arg}' twice")
            out[kw.arg] = kw.value
        return out

    def logic(node):
        if isinstance(node, ast.Name):
            if node.id not in env:
                if node.id in later and later[node.id] > node.lineno:
                    raise _Err(node, f"name '{node.id}' is used before it is defined (line {later[node.id]})")
                raise _Err(node, f"name '{node.id}' is not defined")
            kind, v = env[node.id]
            return v
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            op = "all" if isinstance(node.op, ast.BitAnd) else "any"
            return _flat(op, [logic(node.left), logic(node.right)])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Invert):
            return {"not": logic(node.operand)}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "at_least":
            if node.keywords or len(node.args) < 2:
                raise _Err(node, "at_least(k, a, b, ...) takes a number then the items")
            k = const(node.args[0], "at_least's k")
            items = [logic(a) for a in node.args[1:]]
            if not isinstance(k, int) or isinstance(k, bool) or not 1 <= k <= len(items):
                raise _Err(node, f"at_least: k must be a whole number from 1 to {len(items)}")
            return {"at_least": {"k": k, "of": items}}
        if isinstance(node, (ast.BoolOp, ast.Compare)) or (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)):
            raise _Err(node, "use & for AND, | for OR, ~ for NOT")
        raise _Err(node, f"not allowed here: {type(node).__name__}")

    def condition(call, var):
        a = args_of(call, C_ARGS)
        for need in ("id", "quote", "question"):
            if need not in a:
                raise _Err(call, f"C() needs {need}")
        cid, quote, q = (const(a[k], k) for k in ("id", "quote", "question"))
        if not isinstance(cid, str) or not cid.strip():
            raise _Err(call, "C(): id must be a string")
        if cid in t.conds:
            errors.append(f"line {call.lineno}: duplicate id '{cid}' (first on line {t.conds[cid]['line']})")
        thr = None
        if "threshold" in a and not (isinstance(a["threshold"], ast.Constant) and a["threshold"].value is None):
            node = a["threshold"]
            if not isinstance(node, ast.Tuple) or len(node.elts) not in (2, 3):
                errors.append(f"line {node.lineno}: threshold must be (op, value, unit) with op one of >=, >, <=, <, ==")
            else:
                vals = [const(x, "threshold") for x in node.elts]
                if vals[0] not in OPS:
                    errors.append(f"line {node.lineno}: threshold op {vals[0]!r} is not one of >=, >, <=, <, ==")
                else:
                    thr = {"op": vals[0], "value": vals[1], "unit": vals[2] if len(vals) == 3 else None}
        ans = True
        if "answerable" in a:
            ans = const(a["answerable"], "answerable")
            if not isinstance(ans, bool):
                errors.append(f"line {call.lineno}: answerable must be True or False")
                ans = True
        if not isinstance(q, str) or not q.strip():
            errors.append(f"line {call.lineno}: C('{cid}'): the question is empty")
        hit = st.locate(quote) if isinstance(quote, str) else None
        if hit is None:
            near = st.nearest(quote if isinstance(quote, str) else "")
            errors.append(f"line {call.lineno}: quote not found: {str(quote)[:120]!r}"
                          + (f" (nearest {near[0]['lines']}: {near[0]['text'][:160]!r})" if near else ""))
        t.conds.setdefault(cid, {"quote": hit[1] if hit else quote, "refs": hit[0] if hit else [], "question": q,
                                 "threshold": thr, "answerable": ans, "line": call.lineno, "ok": hit is not None})
        env[var] = ("cond", cid)

    for node in mod.body:
        try:
            if isinstance(node, ast.Assign):
                if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                    raise _Err(node, "assign to one plain name")
                var, val = node.targets[0].id, node.value
                if var in ("C", "at_least", "indication", "not_covered", "notes"):
                    raise _Err(node, f"'{var}' is a reserved name")
                if isinstance(val, ast.Call) and isinstance(val.func, ast.Name) and val.func.id == "C":
                    condition(val, var)
                else:
                    e = logic(val)
                    t.blocks[var] = e
                    env[var] = ("block", e)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                call, fn = node.value, node.value.func.id
                if fn == "indication":
                    a = args_of(call, IND_ARGS)
                    if "id" not in a:
                        raise _Err(call, "indication() needs an id")
                    iid = const(a["id"], "indication id")
                    if iid in t.inds:
                        errors.append(f"line {call.lineno}: indication '{iid}' declared twice")
                    grant = const(a["grant"], "grant") if "grant" in a else None
                    hit = st.locate(grant) if isinstance(grant, str) else None
                    if not grant:
                        errors.append(f"line {call.lineno}: indication '{iid}' needs grant=<the sentence that grants it>")
                    elif hit is None:
                        near = st.nearest(grant)
                        errors.append(f"line {call.lineno}: grant quote not found: {grant[:120]!r}"
                                      + (f" (nearest {near[0]['lines']}: {near[0]['text'][:160]!r})" if near else ""))
                    expr = None
                    if "logic" not in a:
                        errors.append(f"line {call.lineno}: indication '{iid}' needs logic=...")
                    else:
                        try:
                            expr = logic(a["logic"])
                        except _Err as x:
                            errors.append(str(x))
                    t.inds.setdefault(iid, {"grant": hit[1] if hit else grant, "expr": expr, "line": call.lineno})
                elif fn == "not_covered":
                    if len(call.args) != 1 or call.keywords:
                        raise _Err(call, "not_covered(<the guideline's words>)")
                    q = const(call.args[0], "not_covered")
                    hit = st.locate(q) if isinstance(q, str) else None
                    if hit is None:
                        errors.append(f"line {call.lineno}: not_covered quote not found: {str(q)[:120]!r}")
                    t.not_covered = hit[1] if hit else q
                elif fn == "notes":
                    if len(call.args) != 1 or call.keywords:
                        raise _Err(call, "notes(<text>)")
                    t.notes.append(str(const(call.args[0], "notes")))
                elif fn in ("C", "at_least"):
                    raise _Err(call, f"assign {fn}(...) to a name, then use the name")
                else:
                    raise _Err(call, f"not allowed here: call to '{fn}'")
            else:
                raise _Err(node, f"not allowed here: {type(node).__name__}")
        except _Err as x:
            errors.append(str(x))
    if not t.inds and not t.not_covered:
        errors.append("no indication(...) and no not_covered(...): declare at least one")
    if t.inds and all(v["expr"] is not None for v in t.inds.values()):     # else every leaf would look unused
        used = {i for v in t.inds.values() if v["expr"] is not None for i in leaf_ids(v["expr"])}
        for cid in t.conds:
            if cid not in used:
                errors.append(f"line {t.conds[cid]['line']}: unused condition '{cid}'")
    return errors, t


# ---------------------------------------------------------------- the session


class Session:
    def __init__(self, spans: list[Span], audit_of: Optional[Tree] = None):
        self.st = State(spans)
        self.rounds = 0
        self.done = False
        self.script: Optional[str] = None           # the last script sent
        self.tree: Optional[Tree] = None            # the submitted tree
        self.passing: list[Tree] = []               # every tree that passed check or submit
        self.changes: list[str] = []                # unified diffs between consecutive scripts
        self.last: list[str] = []
        self.first = audit_of
        self.first_pass: Optional[tuple[Tree, str]] = None   # the first passing submit (tree, script): the sweep starts
        self.sweep_cut = False

    def handle(self, name: str, args: dict) -> dict:
        if name in ("find", "read"):
            return self.st.handle(name, args)
        if name not in ("check", "submit"):
            return {"ok": False, "problems": [f"no tool '{name}' here; use find, read, check, submit"]}
        self.rounds += 1
        script = (args or {}).get("script") or ""
        if self.script is not None and script != self.script:
            self.changes.append("".join(difflib.unified_diff(self.script.splitlines(True), script.splitlines(True),
                                                             "before", "after")))
        self.script = script
        errors, t = parse(script, self.st)
        if self.first is not None:
            errors += keeps(self.first, t)
        self.last = errors
        if errors:
            return {"ok": False, "errors": errors}
        self.passing.append(t)
        if name == "submit":
            if self.first is None and self.first_pass is None:     # main session: the first pass starts the sweep
                self.first_pass = (t, script)
                return {"ok": True, "accepted": False, "next": SWEEP_NEXT}
            self.tree, self.done = t, True
            return {"ok": True}
        return {"ok": True, "summary": t.summary()}


def keeps(first: Tree, t: Tree) -> list[str]:
    """The audit may only tighten: every condition and indication stays, no indication loses a leaf, none is added."""
    out = [f"the check may only add: condition '{c}' was removed" for c in first.conds if c not in t.conds]
    for iid, v in first.inds.items():
        if iid not in t.inds:
            out.append(f"the check may only add: indication '{iid}' was removed")
        elif t.inds[iid]["expr"] is not None:
            lost = sorted(set(leaf_ids(v["expr"])) - set(leaf_ids(t.inds[iid]["expr"])))
            if lost:
                out.append(f"the check may only add: indication '{iid}' no longer uses {', '.join(lost)}")
    out += [f"the check may only tighten: a new indication '{i}' would widen approval" for i in t.inds if i not in first.inds]
    return out


def instructions(payer: str, given: Optional[str] = None) -> str:
    """`given`: the confirmed indication's text (None: the model finds it)."""
    import os
    out = llm.prompt("reduce/script", payer=payer or "the payer")
    if given:
        out = given_step(out, given)
    out += "\n\n" + llm.prompt("reduce/plan") + "\n\n" + llm.prompt("reduce/sweep")
    if os.environ.get("PITFALLS", "0") == "1":
        out += "\n\n" + llm.prompt("reduce/pitfalls")
    return out


def run(spans, run_id, step, text, payer, model, rounds, calls, audit_of=None, given=None) -> tuple[Session, dict]:
    s = Session(spans, audit_of)
    usage = llm.call_tools(run_id, step, instructions(payer, given), text, schemas(), s.handle,
                           lambda: s.done or s.rounds >= rounds, model=model, max_calls=calls)
    if not s.done and s.first_pass is not None:     # a cap ended the sweep: the first passing script stands
        logger.warning("script: the sweep did not finish (%s); the first passing script stands",
                       "call cap" if usage["capped"] else f"{s.rounds} rounds")
        (s.tree, s.script), s.done, s.sweep_cut = s.first_pass, True, True
    if audit_of is not None and usage.get("capped"):
        logger.warning("script audit hit its %d-call cap", calls)
    llm._log(run_id, f"{step}-script", {"script": s.script, "changes": s.changes, "rounds": s.rounds,
                                        "passed": bool(s.done), "errors": s.last})
    return s, usage


def to_criteria(t: Tree) -> list[Criterion]:
    return [Criterion(id=i, refs=c["refs"], quote=c["quote"], answerable=c["answerable"], question=c["question"],
                      threshold=criteria._threshold(_T(**c["threshold"])) if c["threshold"] else None)
            for i, c in t.conds.items()]


def build(spans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
          procedure: Optional[Procedure] = None, extra: Optional[dict] = None,
          indication: Optional[str] = None) -> CriteriaSet:
    want = picked(sel)
    on = {c for p in n.pathways if p.id in want for c in p.codes} | {x.code for x in sel.code_gate}
    codes = [c for c in n.codes if c.code in on] or n.codes
    payer = n.guideline.payer.name if n.guideline and n.guideline.payer else ""
    ind = "\n\n".join(x for x in (confirmed(n, pid, spans, indication) for pid in want) if x) or None
    msg = user_message(order_json(procedure, extra), codes_json(codes), guideline_text(spans), ind)
    model = llm.pick_models()[0]
    s, u1 = run(spans, run_id, "criteria_script", msg, payer, model, MAX_ROUNDS, MAX_CALLS, given=ind)
    problems: list[str] = []
    if not s.done:
        why = ("the tool-call cap was reached" if u1["capped"] else f"{s.rounds} check/submit rounds"
               if s.rounds >= MAX_ROUNDS else "the model stopped without a passing submit")
        problems.append(f"not finished: {why}")
        problems += s.last
    swept = ("Sweep: cut off by a cap; the first passing script stands" if s.sweep_cut else
             sweep_note(set(s.first_pass[0].conds), set(s.tree.conds), []) if s.first_pass and s.done else "")
    tree, script, loopholes, u2 = s.tree, s.script, [], None
    if s.done and tree.inds:
        try:
            text = llm.prompt("reduce/script_audit", script=script) + "\n\n" + msg
            a, u2 = run(spans, run_id, "criteria_script_audit", text, payer, model, AUDIT_ROUNDS, AUDIT_CALLS,
                        audit_of=tree, given=ind)
            if a.done:
                added = [ln for ln in a.tree.notes if ln not in tree.notes]
                loopholes = [x.strip("-• ").strip() for ln in added for x in ln.splitlines()
                             if x.strip() and x.strip("-• .").lower() not in ("none found", "none", "nothing found")][:20]
                tree, script = a.tree, a.script
        except Exception as x:          # the check only adds; the first script stands without it
            logger.warning("script audit failed: %s", x)
            problems.append(f"audit failed: {type(x).__name__}")
    if tree is None:                    # nothing passed: the last passing script, if any, is shown for review
        tree = s.passing[-1] if s.passing else None
    removed, nc_note = [], None
    if tree is not None:
        seen: dict[str, dict] = {}
        for p in s.passing:
            for i, c in p.conds.items():
                seen.setdefault(i, c)
        removed = [{"id": i, "quote": c["quote"], "why": " ".join(tree.notes)} for i, c in seen.items()
                   if i not in tree.conds]
        nc, nc_note = not_covered(tree.not_covered, bool(tree.inds))
        if nc:
            problems.append(nc)
    exprs = []
    if tree is not None:
        ex = [v["expr"] for v in tree.inds.values() if v["expr"] is not None]
        if ex:
            exprs = [Expression(pathway=pid, expr=ex[0] if len(ex) == 1 else {"any": ex}) for pid in want]
    used = {i for e in exprs for i in leaf_ids(e.expr)}
    notes = list(tree.notes) if tree else []
    if tree is not None and nc_note:
        notes.append(nc_note)
    if swept:
        notes.append(swept)
    if u2 and u2.get("capped"):
        notes.append(f"The check hit its {AUDIT_CALLS}-call cap.")
    if tree and tree.inds:
        notes.append("Indication used: " + " | ".join(v["grant"] for v in tree.inds.values() if v["grant"]))
    cs = CriteriaSet(key=key, criteria=[c for c in to_criteria(tree) if c.id in used] if tree else [],
                     expressions=exprs, notes="\n\n".join(x for x in notes if x), loopholes=loopholes,
                     status="needs_review" if problems else "ok", problems=problems, run_id=run_id,
                     removed_conditions=removed, script=script)
    spend = {"main": u1, **({"audit": u2} if u2 else {})}
    llm._log(run_id, "criteria_script-cost", spend)
    logger.info("criteria (script) %s: %d criteria, %d indication(s), %d loophole(s), %s, %d rounds, $%.2f", key,
                len(cs.criteria), len(tree.inds) if tree else 0, len(loopholes), cs.status, s.rounds,
                sum(v["dollars"] for v in spend.values()))
    return cs
