"""Compare a generated requirement tree with the answer key's, exactly. One model call per pair (leaf alignment).

    .venv/bin/python experiments/eval/tree_diff.py --results data/reduce_loose/<model>/results-heading-loose-next.jsonl
                                                   [--results F ...] [--store <v1.1 score store> ...]
                                                   [--only slug,...] [--view full|coordinator] [--out DIR]
                                                   [--export-prompts DIR | --import-answers DIR] [--align-only]

Pairs come from experiments/eval/pairs.py (the reduce runner's results rows, or v1.1 score stores) against the answer
keys in tests/fixtures. --view coordinator scores the tree the coordinator sees: the case's admin leaves pruned by the
app's own guards (app.checklist.admin.split), alignment derived from the full view's by dropping the pruned leaves.

The model only aligns leaves (`align_trees.md`, beside this file): for every generated leaf, which key leaf it asks
about (same / narrower / broader / negation / part_of / combines / any_of / none). The alignment is cached as a
reviewable JSON file under <out>/<arm>/align/ and never re-asked unless either tree changes (its stamp). With no
cached alignment the model is called (paid), unless --export-prompts writes the prompts for a person or another agent
to answer, and --import-answers validates and caches the answers. Everything after that is code:

  variables  one per key leaf; one per generated leaf with no counterpart. A generated leaf is its variable, NOT of it
             (negation; several = none of), ALL of several (combines) or ANY of several (any_of). Unanswerable leaves
             follow the app (never judged; only a review reason, counted separately): a key one is MET, a generated
             one MET where required and NOT_MET under a NOT (map_trees).
  logic      the app's three-valued semantics (evaluate.py): ALL: any NOT_MET -> NOT_MET, else any INSUFFICIENT ->
             INSUFFICIENT, else MET; ANY dual; NOT swaps MET/NOT_MET and keeps INSUFFICIENT; at_least k.
  exact      (authoritative) a SAT encoding of that logic, every leaf a pair (met, not_met), never both, neither =
             INSUFFICIENT; Tseitin per node, at_least by a sequential counter. "Generated MET and key not MET" is SAT
             or it is not: UNSAT proves no chart of any mix of MET / NOT_MET / INSUFFICIENT is a false approval.
             Witnesses are minimised greedily towards the baseline and enumerated with blocking clauses on the set of
             key leaves that fail (the requirement the generated tree misses), first with every generated-only
             alternative held off ("direct"), then without ("via generated-only routes": the generated tree approves
             through a route the key's pathway lacks; for human review, never discarded). Per key leaf: can it fail
             in a false approval at all, alone, alone and direct. Missed good charts the same way, capped.
  baseline   every variable set to the value that satisfies the tree it belongs to (key leaves by the key's polarity,
             generated-only leaves by the generated tree's): the "qualifying chart".
  heuristic  (kept as *_heuristic for comparison) every single and pair flip from the baseline, plus random flips,
             bit-parallel, exhaustive over two values up to 16 variables. It misses false approvals that need 3+ flips.
  silence    the baseline with every leaf under a NOT left INSUFFICIENT (charts are silent on exclusions): can each
             tree still be ready?
  thresholds aligned leaves whose typed thresholds differ.

The witnesses are chart specs: a leaf-by-leaf list of what a synthetic chart should document.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from itertools import combinations
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.eval import pairs as P  # noqa: E402

PROMPT = Path(__file__).resolve().parent / "align_trees.md"
OUT = ROOT / "experiments" / "eval" / "data"          # gitignored (experiments/**/data/)
MET, NOT_MET, INSUFFICIENT = "MET", "NOT_MET", "INSUFFICIENT"


# ---------------------------------------------------------------- trees
# A tree is ("leaf", id) | ("const", status) | ("all", [t]) | ("any", [t]) | ("not", t) | ("atl", k, [t]).

def from_key(n) -> tuple:
    if n.type == "leaf":
        return ("leaf", n.criterion)
    if n.type == "not":
        return ("not", from_key(n.child))
    return (n.type, [from_key(c) for c in n.children])


def from_expr(e) -> tuple:
    """v1.1 expression: "id" | {"all": [...]} | {"any": [...]} | {"not": e} | {"at_least": {"k": k, "of": [...]}}."""
    if isinstance(e, str):
        return ("leaf", e)
    op = next(k for k in e if k in ("all", "any", "not", "at_least"))
    a = e[op]
    if op == "not":
        return ("not", from_expr(a))
    if op == "at_least":
        return ("atl", a["k"], [from_expr(x) for x in a["of"]])
    return (op, [from_expr(x) for x in a])


def kids(t: tuple) -> list:
    return t[2] if t[0] == "atl" else t[1] if t[0] in ("all", "any") else [t[1]] if t[0] == "not" else []


def leaves(t: tuple) -> list[str]:
    if t[0] == "leaf":
        return [t[1]]
    return [x for c in kids(t) for x in leaves(c)]


def polarity(t: tuple, neg: bool = False, out: dict | None = None) -> dict[str, bool]:
    """Leaf id -> True when it sits under an odd number of NOTs."""
    out = {} if out is None else out
    if t[0] == "leaf":
        out.setdefault(t[1], neg)
    for c in kids(t):
        polarity(c, neg ^ (t[0] == "not"), out)
    return out


def subst(t: tuple, f) -> tuple:
    """Replace each leaf by f(id) (a tree)."""
    if t[0] == "leaf":
        return f(t[1])
    if t[0] == "const":
        return t
    if t[0] == "not":
        return ("not", subst(t[1], f))
    if t[0] == "atl":
        return ("atl", t[1], [subst(c, f) for c in t[2]])
    return (t[0], [subst(c, f) for c in t[1]])


def show(t: tuple, text: dict[str, str], ind: int = 0) -> str:
    p = "  " * ind
    if t[0] == "leaf":
        return f"{p}- [{t[1]}] {text.get(t[1], '')}"
    if t[0] == "const":
        return f"{p}- ({t[1]})"
    head = {"all": "ALL", "any": "ANY", "not": "NOT"}.get(t[0]) or f"AT_LEAST {t[1]} OF"
    return f"{p}{head}\n" + "\n".join(show(c, text, ind + 1) for c in kids(t))


# ---------------------------------------------------------------- bit-parallel three-valued evaluation

def ev(t: tuple, env: dict[str, tuple[int, int]], full: int) -> tuple[int, int]:
    """(met, not_met) masks over all rows; INSUFFICIENT is neither."""
    k = t[0]
    if k == "leaf":
        return env[t[1]]
    if k == "const":
        return (full, 0) if t[1] == MET else (0, full) if t[1] == NOT_MET else (0, 0)
    if k == "not":
        m, n = ev(t[1], env, full)
        return n, m
    rs = [ev(c, env, full) for c in kids(t)]
    if k == "all":
        m, n = full, 0
        for a, b in rs:
            m &= a
            n |= b
        return m, n
    if k == "any":
        m, n = 0, full
        for a, b in rs:
            m |= a
            n &= b
        return m, n
    # at_least k: MET when >= k children MET; NOT_MET when fewer than k can still be MET (not NOT_MET).
    need = t[1]

    def at_least(masks: list[int]) -> int:
        dp = [full] + [0] * need          # dp[j]: rows with at least j of the masks seen so far
        for x in masks:
            for j in range(need, 0, -1):
                dp[j] |= dp[j - 1] & x
        return dp[need]

    met = at_least([a for a, _ in rs])
    possible = at_least([full & ~b for _, b in rs])
    return met, full & ~possible


def status_at(mn: tuple[int, int], row: int) -> str:
    m, n = mn
    return MET if m >> row & 1 else NOT_MET if n >> row & 1 else INSUFFICIENT


# ---------------------------------------------------------------- exact check: SAT over the three-valued semantics
# Every variable v is a pair of booleans (met_v, notmet_v), never both; neither is INSUFFICIENT (the chart is silent).
# Each node gets the same pair by Tseitin equivalences that mirror ev() exactly, so "the generated tree is MET and the
# key's is not" is a SAT question with no search neighbourhood: UNSAT proves no chart (any mix of MET / NOT_MET /
# INSUFFICIENT per leaf) is approved by the generated tree and refused by the key.

VALUES = (MET, NOT_MET, INSUFFICIENT)


class Enc:
    def __init__(self):
        self.n = 1                      # var 1 is TRUE
        self.cl: list[list[int]] = [[1]]
        self.var: dict[str, tuple[int, int]] = {}

    def new(self) -> int:
        self.n += 1
        return self.n

    def leaf(self, v: str) -> tuple[int, int]:
        if v not in self.var:
            m, n = self.new(), self.new()
            self.cl.append([-m, -n])
            self.var[v] = (m, n)
        return self.var[v]

    def AND(self, xs: list[int]) -> int:
        if not xs:
            return 1
        if len(xs) == 1:
            return xs[0]
        y = self.new()
        self.cl += [[-y, x] for x in xs] + [[y] + [-x for x in xs]]
        return y

    def OR(self, xs: list[int]) -> int:
        if not xs:
            return -1
        if len(xs) == 1:
            return xs[0]
        y = self.new()
        self.cl += [[y, -x] for x in xs] + [[-y] + list(xs)]
        return y

    def atleast(self, k: int, xs: list[int]) -> int:
        """y <-> at least k of xs (sequential counter, full equivalences)."""
        if k <= 0:
            return 1
        if k > len(xs):
            return -1
        prev = [1] + [-1] * k                       # prev[j]: at least j of the inputs seen so far
        for x in xs:
            cur = [1]
            for j in range(1, k + 1):
                cur.append(self.OR([prev[j], self.AND([prev[j - 1], x])]) if prev[j - 1] != -1 else prev[j])
            prev = cur
        return prev[k]

    def node(self, t: tuple) -> tuple[int, int]:
        k = t[0]
        if k == "leaf":
            return self.leaf(t[1])
        if k == "const":
            return (1, -1) if t[1] == MET else (-1, 1) if t[1] == NOT_MET else (-1, -1)
        if k == "not":
            m, n = self.node(t[1])
            return n, m
        rs = [self.node(c) for c in kids(t)]
        ms, ns = [a for a, _ in rs], [b for _, b in rs]
        if k == "all":
            return self.AND(ms), self.OR(ns)
        if k == "any":
            return self.OR(ms), self.AND(ns)
        # at_least k: MET when >= k children MET; NOT_MET when fewer than k are not NOT_MET, i.e. >= n-k+1 NOT_MET
        return self.atleast(t[1], ms), self.atleast(len(ns) - t[1] + 1, ns)

    def is_(self, v: str, val: str) -> list[int]:
        m, n = self.var[v]
        return [m, -n] if val == MET else [-m, n] if val == NOT_MET else [-m, -n]


def eval_assign(t: tuple, a: dict[str, str]) -> str:
    """Status of a tree on one assignment (leaf -> MET / NOT_MET / INSUFFICIENT), via ev()."""
    env = {v: ((1, 0) if x == MET else (0, 1) if x == NOT_MET else (0, 0)) for v, x in a.items()}
    return status_at(ev(t, env, 1), 0)


def mandatory(t: tuple, neg: bool = False, conj: bool = True, out: dict | None = None) -> dict[str, bool]:
    """Leaf -> True when every ancestor is effectively ALL (ANY under an odd number of NOTs counts as ALL)."""
    out = {} if out is None else out
    if t[0] == "leaf":
        out[t[1]] = out.get(t[1], True) and conj
        return out
    here = {"all": not neg, "any": neg, "atl": len(kids(t)) == (t[1] if t[0] == "atl" else 0)}.get(t[0], True)
    for c in kids(t):
        mandatory(c, neg ^ (t[0] == "not"), conj and here, out)
    return out


def baseline_of(T: tuple, Gx: tuple) -> dict[str, str]:
    """The qualifying chart: key variables by the key's polarity, generated-only ones by the generated tree's."""
    t_pol, g_pol = polarity(T), polarity(Gx)
    vs = sorted(set(leaves(T)) | set(leaves(Gx)))
    return {v: NOT_MET if (t_pol[v] if v in t_pol else g_pol.get(v, False)) else MET for v in vs}


def gen_routes(T: tuple, Gx: tuple) -> list[str]:
    """Generated-only alternatives: G-only variables that are optional in the generated tree and required in their
    positive sense (a route or an exception the key may lack). Turning one off means the chart does not show it.
    Generated-only leaves under a NOT are exclusion parts: their baseline (absent) is already 'off'."""
    g_pol, m = polarity(Gx), mandatory(Gx)
    key = set(leaves(T))
    return sorted(v for v in set(leaves(Gx)) - key if not g_pol.get(v) and not m.get(v, True))


def exact_diff(T: tuple, Gx: tuple, cap: int = 20, cap_missed: int = 20) -> dict:
    """Exact false approvals (G MET, T not MET) and missed good charts (T MET, G not MET) over all three-valued charts.

    Witnesses are minimised greedily towards the qualifying chart; `fails` names the key leaves off their qualifying
    value (the requirement the generated tree does not enforce). FA witnesses are enumerated first with every
    generated-only alternative held off ("direct"), then without ("via generated-only routes", with the routes used)."""
    from pysat.solvers import Solver

    e = Enc()
    tm, tn = e.node(T)
    gm, gn = e.node(Gx)
    base = baseline_of(T, Gx)
    for v in base:
        e.leaf(v)
    key_vars = sorted(v for v in base if v in set(leaves(T)))
    gen_vars = sorted(v for v in base if v not in set(key_vars))
    routes = gen_routes(T, Gx)
    at_base = {}
    for v in base:                                  # b_v <-> v at its qualifying value
        at_base[v] = e.AND(e.is_(v, base[v]))
    routes_off = [-e.var[r][0] for r in routes]     # an alternative is off when not MET
    fa_act, mg_act = e.new(), e.new()
    e.cl += [[-fa_act, gm], [-fa_act, -tm], [-mg_act, tm], [-mg_act, -gm]]
    s = Solver(name="g4", bootstrap_with=e.cl)

    def model_assign() -> dict[str, str]:
        mdl = set(x for x in s.get_model() if x > 0)
        return {v: MET if e.var[v][0] in mdl else NOT_MET if e.var[v][1] in mdl else INSUFFICIENT for v in base}

    def minimise(assume: list[int], prefs: list[tuple[str, str]]) -> dict[str, str]:
        assume = list(assume)
        assert s.solve(assumptions=assume)
        cur = model_assign()
        for v, val in prefs:
            if cur[v] == val:
                assume += e.is_(v, val)
                continue
            if s.solve(assumptions=assume + e.is_(v, val)):
                assume += e.is_(v, val)
                cur = model_assign()
        return cur

    def opp(v: str) -> str:
        return NOT_MET if base[v] == MET else MET

    def witness(a: dict[str, str], kind: str, routes_used=()) -> dict:
        """flip/values: leaves off the qualifying chart; generated-only routes are listed apart (held off, or used)."""
        flip = [v for v in sorted(a) if a[v] != base[v] and (kind == "missed_good" or v not in routes)]
        w = {"flip": flip, "values": {v: a[v] for v in flip}, "fails": [v for v in flip if v in key_vars],
             "key": eval_assign(T, a), "gen": eval_assign(Gx, a), "kind": kind}
        if kind != "missed_good":
            w["routes_off"] = {r: a[r] for r in routes if a[r] != MET}
            w["routes_used"] = list(routes_used)
        return w

    def fa_enum(direct: bool, blocks: list[int], n: int) -> list[dict]:
        out = []
        while len(out) < n:
            assume = [fa_act] + blocks + (routes_off if direct else [])
            if not s.solve(assumptions=assume):
                break
            # key leaves back to their qualifying value first (the smallest missing requirement), failing ones to the
            # opposite value rather than silent; then routes off; then the rest of the generated-only leaves
            prefs = [(v, base[v]) for v in key_vars]
            a0 = minimise(assume, prefs)
            failing = [v for v in key_vars if a0[v] != base[v]]
            # then the other generated-only leaves back to their qualifying value (which only helps the generated tree),
            # and only then the routes off, so the routes left on are the ones this false approval needs
            prefs = [(v, base[v]) for v in key_vars] + [(v, opp(v)) for v in failing]
            prefs += [(v, base[v]) for v in gen_vars if v not in routes]
            if not direct:
                prefs += [(r, NOT_MET) for r in routes]
            a = minimise(assume + [-at_base[v] for v in failing], prefs)
            used = [r for r in routes if a[r] == MET] if not direct else []
            out.append(witness(a, "via_gen_only_routes" if used else "direct", used))
            # block every chart whose failing key leaves include this set (minimal sets only)
            act = e.new()
            s.add_clause([-act] + [at_base[v] for v in failing])
            blocks.append(act)
            if not failing:
                break
        return out

    blocks: list[int] = []
    direct = fa_enum(True, blocks, cap)
    via = fa_enum(False, blocks, cap)
    fa_any = s.solve(assumptions=[fa_act])

    # per-key-leaf attribution
    attrib = {}
    for k in key_vars:
        others = [at_base[v] for v in key_vars if v != k]
        if not s.solve(assumptions=[fa_act, -at_base[k]]):
            continue
        a = minimise([fa_act, -at_base[k]], [(v, base[v]) for v in key_vars + gen_vars])
        assert eval_assign(Gx, a) == MET and eval_assign(T, a) != MET and a[k] != base[k]
        attrib[k] = {"with_others": True,
                     "alone": s.solve(assumptions=[fa_act, -at_base[k]] + others),
                     "alone_direct": s.solve(assumptions=[fa_act, -at_base[k]] + others + routes_off),
                     "example": {v: a[v] for v in sorted(a) if a[v] != base[v]}}

    # missed good charts: all variables off their qualifying value, grouped
    missed, mblocks = [], []
    while len(missed) < cap_missed:
        assume = [mg_act] + mblocks
        if not s.solve(assumptions=assume):
            break
        a0 = minimise(assume, [(v, base[v]) for v in gen_vars + key_vars])
        off = [v for v in sorted(base) if a0[v] != base[v]]
        a = minimise(assume + [-at_base[v] for v in off], [(v, base[v]) for v in sorted(base)] + [(v, opp(v)) for v in off])
        missed.append(witness(a, "missed_good"))
        act = e.new()
        s.add_clause([-act] + [at_base[v] for v in off])
        mblocks.append(act)
        if not off:
            break
    mg_any = s.solve(assumptions=[mg_act])
    s.delete()
    for w in direct + via + missed:                 # every witness is re-checked by ev(), independent of the encoding
        ok = (w["gen"] == MET and w["key"] != MET) if w["kind"] != "missed_good" else (w["key"] == MET and w["gen"] != MET)
        assert ok, w
    return {"false_approval": fa_any, "false_approvals": direct, "false_approvals_via_gen_only_routes": via,
            "fa_capped": len(direct) >= cap or len(via) >= cap, "fa_by_key_leaf": attrib,
            "missed_good_exists": mg_any, "missed_good": missed, "missed_capped": len(missed) >= cap_missed,
            "routes": routes, "baseline": base, "variables": len(base)}


def brute_force(T: tuple, Gx: tuple, fix: dict[str, tuple[str, ...]] | None = None) -> dict:
    """Ground truth by enumeration, bit-parallel over every three-valued chart (3^n rows; keep n <= 13). `fix` limits a
    variable to some values (e.g. a route to NOT_MET / INSUFFICIENT). Returns counts and the masks' first rows."""
    vs = sorted(set(leaves(T)) | set(leaves(Gx)))
    doms = [list((fix or {}).get(v, VALUES)) for v in vs]
    sizes, total = [], 1
    for d in doms:
        sizes.append(total)
        total *= len(d)
    full = (1 << total) - 1
    env = {}
    for v, d, blk in zip(vs, doms, sizes):
        period = blk * len(d)
        reps = total // period
        rep = ((1 << (period * reps)) - 1) // ((1 << period) - 1)    # 1 at the start of every period
        masks = {}
        for idx, val in enumerate(d):
            masks[val] = (((1 << blk) - 1) << (idx * blk)) * rep
        env[v] = (masks.get(MET, 0), masks.get(NOT_MET, 0))
    tm, tn = ev(T, env, full)
    gm, gn = ev(Gx, env, full)
    fa, mg = gm & ~tm, tm & ~gm

    def row(r: int) -> dict[str, str]:
        out = {}
        for v, d, blk in zip(vs, doms, sizes):
            out[v] = d[(r // blk) % len(d)]
        return out
    first = lambda m: row((m & -m).bit_length() - 1) if m else None
    return {"rows": total, "false_approvals": fa.bit_count(), "missed_good": mg.bit_count(),
            "fa_example": first(fa), "mg_example": first(mg), "fa_mask": fa, "row": row}


def false_approvals_exact(T: tuple, Gx: tuple, cap: int = 20) -> dict:
    """SAT for met(G) and not met(T) on the leaf-mapped trees (see map_trees). Returns exact_diff's dict."""
    return exact_diff(T, Gx, cap=cap)


# ---------------------------------------------------------------- alignment (the one model call)

class Link(BaseModel):
    gen: str
    relation: Literal["same", "narrower", "broader", "negation", "part_of", "combines", "any_of", "none"]
    truth: list[str] = []
    why: str = ""


class Alignment(BaseModel):
    links: list[Link]


def check_alignment(a: Alignment, t_ids: set[str], g_ids: set[str]) -> list[str]:
    problems, seen = [], set()
    for l in a.links:
        if l.gen not in g_ids:
            problems.append(f"unknown G leaf {l.gen}")
        if l.gen in seen:
            problems.append(f"G leaf {l.gen} linked twice")
        seen.add(l.gen)
        bad = [x for x in l.truth if x not in t_ids]
        if bad:
            problems.append(f"{l.gen}: unknown T leaves {bad}")
        n = len(l.truth)
        if l.relation == "none" and n:
            problems.append(f"{l.gen}: 'none' with T leaves")
        if l.relation in ("combines", "any_of") and n < 2:
            problems.append(f"{l.gen}: '{l.relation}' needs 2+ T leaves")
        if l.relation == "negation" and n < 1:
            problems.append(f"{l.gen}: 'negation' needs one or more T leaves")
        if l.relation not in ("none", "combines", "any_of", "negation") and n != 1:
            problems.append(f"{l.gen}: '{l.relation}' needs exactly one T leaf")
    problems += [f"G leaf {g} not linked" for g in sorted(g_ids - seen)]
    return problems


def fill(template: str, **vars: str) -> str:
    """{{name}} substitution, as app.core.llm.prompt does for prompts/."""
    for k, v in vars.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def align_prompt(t_tree, t_text, g_tree, g_text) -> tuple[str, list[str], list[str]]:
    T = lambda i: "T." + i
    G = lambda i: "G." + i
    t_ids, g_ids = sorted(set(leaves(t_tree))), sorted(set(leaves(g_tree)))
    user = fill(
        PROMPT.read_text(),
        t_tree=show(subst(t_tree, lambda i: ("leaf", T(i))), {T(k): v for k, v in t_text.items()}),
        g_tree=show(subst(g_tree, lambda i: ("leaf", G(i))), {G(k): v for k, v in g_text.items()}),
        t_leaves="\n".join(f"{T(i)}: {t_text[i]}" for i in t_ids),
        g_leaves="\n".join(f"{G(i)}: {g_text[i]}" for i in g_ids))
    return user, t_ids, g_ids


def strip_ids(a: Alignment) -> Alignment:
    for l in a.links:
        l.gen = l.gen.removeprefix("G.")
        l.truth = [x.removeprefix("T.") for x in l.truth]
    return a


def align(t_tree, t_text, g_tree, g_text, run_id: str) -> tuple[Alignment, list[str]]:
    from app.core import llm
    user, t_ids, g_ids = align_prompt(t_tree, t_text, g_tree, g_text)

    def ask(step: str, text: str) -> tuple[Alignment, list[str]]:
        a = strip_ids(llm.call(run_id, step, text, Alignment, reasoning_effort="low"))
        return a, check_alignment(a, set(t_ids), set(g_ids))

    a, problems = ask("align_trees", user)
    if problems:   # one retry with the problems listed, as every ingest check does
        a, problems = ask("align_trees_retry", user + "\n\nYour previous answer had these problems; return the whole "
                          "alignment again, one link per G leaf, `gen` a G id and `truth` T ids:\n- " + "\n- ".join(problems))
    return a, problems


# ---------------------------------------------------------------- the comparison

def map_trees(t_tree: tuple, t_unans: set[str], g_tree: tuple, g_unans: set[str], a: Alignment) -> tuple[tuple, tuple]:
    """Both trees over shared variables: T.<key leaf> and G.<generated-only leaf>. A generated leaf is its key leaf,
    NOT of it (negation; several = none of), ALL of several (combines) or ANY of several (any_of). Unanswerable leaves
    follow the app: never judged, so a key one is MET, and a generated one is MET where it is required and NOT_MET under
    a NOT (an unanswerable exclusion never fires); either way it only adds a review reason."""
    link = {l.gen: l for l in a.links}
    g_pol = polarity(g_tree)

    def g_leaf(i: str) -> tuple:
        if i in g_unans:
            return ("const", NOT_MET if g_pol.get(i) else MET)
        l = link.get(i)
        if l is None or l.relation == "none" or not l.truth:
            return ("leaf", "G." + i)
        if l.relation == "negation":   # the opposite of one T leaf, or "none of" several
            return ("not", ("leaf", "T." + l.truth[0]) if len(l.truth) == 1 else ("any", [("leaf", "T." + x) for x in l.truth]))
        if l.relation == "combines":
            return ("all", [("leaf", "T." + x) for x in l.truth])
        if l.relation == "any_of":     # one G leaf that holds when any of several T leaves holds ("a comorbidity such as")
            return ("any", [("leaf", "T." + x) for x in l.truth])
        return ("leaf", "T." + l.truth[0])

    return subst(t_tree, lambda i: ("const", MET) if i in t_unans else ("leaf", "T." + i)), subst(g_tree, g_leaf)


def compare(t_tree: tuple, t_text: dict, t_unans: set[str], t_thr: dict,
            g_tree: tuple, g_text: dict, g_unans: set[str], g_thr: dict, a: Alignment,
            seed: int = 0, n_random: int = 8192, max_pairs: int = 6000, cap: int = 20) -> dict:
    """The exact SAT check is authoritative (false_approvals, false_approvals_via_gen_only_routes, missed_good). The
    old neighbourhood search is kept as *_heuristic for comparison."""
    T, Gx = map_trees(t_tree, t_unans, g_tree, g_unans, a)
    t_pol, g_pol = polarity(T), polarity(Gx)
    vars_ = sorted(set(leaves(T)) | set(leaves(Gx)))
    # baseline: the value that satisfies the tree the variable belongs to
    base = {v: not (t_pol[v] if v.startswith("T.") and v in t_pol else g_pol.get(v, False)) for v in vars_}
    conflict = sorted(v for v in vars_ if v in t_pol and v in g_pol and t_pol[v] != g_pol[v])
    routes = gen_routes(T, Gx)
    # Heuristic FA pass: generated-only alternatives held off. (It used to flip every optional generated-only leaf,
    # including parts of an exclusion under a NOT, which switched the exclusion on and hid the false approval.)
    base_fa = {v: (not base[v] if v in routes else base[v]) for v in vars_}

    def search(base: dict[str, bool], frozen: frozenset = frozenset()):
        flippable = [v for v in vars_ if v not in frozen]
        rng = random.Random(seed)
        rows: list[tuple[str, tuple]] = [("baseline", ())]
        rows += [("flip", (v,)) for v in flippable]
        pairs = list(combinations(flippable, 2))
        if len(pairs) > max_pairs:
            pairs = rng.sample(pairs, max_pairs)
        rows += [("flip", p) for p in pairs]
        exhaustive = len(vars_) <= 16 and not frozen
        if exhaustive:
            for code in range(1 << len(vars_)):
                rows.append(("assign", tuple(v for b, v in enumerate(vars_) if code >> b & 1)))  # variables MET
        else:
            for _ in range(n_random):
                rows.append(("flip", tuple(v for v in flippable if rng.random() < 0.15)))
        full = (1 << len(rows)) - 1

        def value(kind, xs, v) -> bool:
            return (v in xs) if kind == "assign" else (base[v] ^ (v in xs))

        def env_for() -> dict[str, tuple[int, int]]:
            env = {}
            for v in vars_:
                bits = "".join("1" if value(kind, xs, v) else "0" for kind, xs in reversed(rows))
                m = int(bits, 2)
                env[v] = (m, full & ~m)
            return env

        env = env_for()
        tm, tn = ev(T, env, full)
        gm, gn = ev(Gx, env, full)
        fa, fd = gm & ~tm, tm & ~gm

        def witnesses(mask: int, cap: int = 40) -> list[dict]:
            def w(r):
                kind, xs = rows[r]
                flips = list(xs) if kind == "flip" else [v for v in vars_ if value(kind, xs, v) != base[v]]
                return {"flip": flips, "key": status_at((tm, tn), r), "gen": status_at((gm, gn), r)}
            hits = [i for i, c in enumerate(bin(mask)[:1:-1]) if c == "1"]
            small = [r for r in hits if rows[r][0] == "flip" and len(rows[r][1]) <= 1]
            singles = {v for r in small for v in rows[r][1]}
            small += [r for r in hits if rows[r][0] == "flip" and len(rows[r][1]) == 2 and not singles & set(rows[r][1])]
            if small:
                seen, out = set(), []
                for r in small:
                    k = tuple(sorted(rows[r][1]))
                    if k not in seen:
                        seen.add(k)
                        out.append(w(r))
                return out[:cap]
            return [min((w(r) for r in hits), key=lambda x: len(x["flip"]))] if hits else []

        return rows, (tm, tn), (gm, gn), fa, fd, witnesses, exhaustive

    rows, tmn, gmn, _, fd, wit_fd, exhaustive = search(base)
    (tm, tn), (gm, gn) = tmn, gmn
    _, _, _, fa_alt, _, wit_fa, _ = search(base_fa, frozenset(routes))

    # silence: baseline with every leaf under a NOT left INSUFFICIENT, separately per tree
    def silent_status(tree, pol) -> str:
        e = {v: ((1, 0) if base[v] else (0, 1)) for v in vars_}
        for v, neg in pol.items():
            if neg:
                e[v] = (0, 0)
        return status_at(ev(tree, e, 1), 0)

    thr = []
    for l in a.links:
        if l.relation in ("same", "narrower", "broader") and l.truth:
            x, y = t_thr.get(l.truth[0]), g_thr.get(l.gen)
            if x and y and (x.get("op"), str(x.get("value"))) != (y.get("op"), str(y.get("value"))):
                thr.append({"key": l.truth[0], "gen": l.gen, "key_threshold": x, "gen_threshold": y})

    n_all = len(rows)
    ex = {}
    if exhaustive:
        fa = search(base)[3]
        lo = n_all - (1 << len(vars_))
        part = ((1 << (1 << len(vars_))) - 1) << lo
        ex = {"assignments": 1 << len(vars_),
              "false_approvals": (fa & part).bit_count(), "missed_good": (fd & part).bit_count(),
              "key_ready": (tm & part).bit_count(), "gen_ready": (gm & part).bit_count()}
    x = exact_diff(T, Gx, cap=cap, cap_missed=cap)
    return {
        "variables": len(vars_), "exhaustive": exhaustive, "rows": n_all,
        "baseline": {"key": status_at((tm, tn), 0), "gen": status_at((gm, gn), 0)},
        "polarity_conflicts": conflict,
        "false_approval": x["false_approval"], "false_approvals": x["false_approvals"],
        "false_approvals_via_gen_only_routes": x["false_approvals_via_gen_only_routes"],
        "fa_capped": x["fa_capped"], "fa_by_key_leaf": x["fa_by_key_leaf"], "gen_only_routes": routes,
        "missed_good_exists": x["missed_good_exists"], "missed_good": x["missed_good"], "missed_capped": x["missed_capped"],
        "false_approvals_heuristic": wit_fa(fa_alt), "missed_good_heuristic": wit_fd(fd), "exact_heuristic": ex,
        "silence": {"key": silent_status(T, t_pol), "gen": silent_status(Gx, g_pol)},
        "thresholds": thr,
        "unanswerable": {"key": sorted(t_unans), "gen": sorted(g_unans)},
        "gen_only": sorted(v[2:] for v in vars_ if v.startswith("G.")),
        "key_unused": sorted(set(leaves(t_tree)) - {x for l in a.links for x in l.truth} - t_unans),
    }


# ---------------------------------------------------------------- the two sides of a pair

def gen_side(d: dict, view: str = "full") -> tuple[tuple, dict, set, dict]:
    """A step-H output ({narrowed, criteria}) -> (tree over its chosen pathways, leaf texts, unanswerable, thresholds).
    view 'coordinator': the admin leaves the app prunes for the case removed first (app.checklist.admin.split)."""
    cs = d["criteria"]
    ex = cs["expressions"]
    ex = {e["pathway"]: e["expr"] for e in ex} if isinstance(ex, list) else ex
    picks = [p for p in (d["narrowed"].get("chosen") or []) if p in ex]
    if view == "coordinator":
        ex = coordinator_exprs(cs, picks)
    trees = [from_expr(ex[p]) for p in picks]
    tree = trees[0] if len(trees) == 1 else ("any", trees)
    used = set(leaves(tree))
    crit = {c["id"]: c for c in cs["criteria"] if c["id"] in used}
    text = {i: f"{c.get('quote') or ''} | asks: {c['question']}" for i, c in crit.items()}
    return tree, text, {i for i, c in crit.items() if not c.get("answerable", True)}, \
        {i: c["threshold"] for i, c in crit.items() if c.get("threshold")}


def coordinator_exprs(cs: dict, picks: list[str]) -> dict:
    """The expressions after the app's per-case admin pruning, with no strikes or restores (no chart)."""
    from app.checklist import admin
    from app.core.models import CriteriaSet
    pruned, _ = admin.split(None, CriteriaSet.model_validate(cs), picks)
    return {e.pathway: e.expr for e in pruned.expressions}


def key_side(key: P.Key, sc: P.Scenario) -> tuple[tuple, dict, set, dict]:
    tree = from_key(sc.requires)
    used = set(leaves(tree))
    crit = {c.id: c for c in key.criteria if c.id in used}
    return tree, {i: f"{c.text} | asks: {c.question}" for i, c in crit.items()}, \
        {i for i, c in crit.items() if not c.answerable}, \
        {i: c.threshold for i, c in crit.items() if c.threshold}


def stamp_of(t: tuple, g: tuple) -> str:
    """What an alignment was made on: key tree, key texts, generated tree, generated texts."""
    return hashlib.sha256(json.dumps([t[0], t[1], g[0], g[1]], sort_keys=True).encode()).hexdigest()[:12]


def records(results: list[Path], stores: list[Path], only: set[str], view: str = "full", out: Path = OUT):
    """One record per pair: {arm, name, guideline, pathway, code, scenario_id, t, g, stamp, align_file}, or
    {..., no_tree: True} when the run produced no tree for the test."""
    ps = [p for r in results for p in P.results_pairs(r, only)] + (P.v11_pairs(stores, only) if stores else [])
    for p in ps:
        arm = p["arm"] + ("-coordinator" if view == "coordinator" else "")
        rec = {"arm": arm, "name": p["name"], "guideline": p["guideline"], "pathway": p["pathway"], "code": p["code"],
               "scenario_id": p["scenario_id"]}
        if p["gen"] is None:
            yield {**rec, "no_tree": True, "error": p["row"].get("error")}
            continue
        t, g = key_side(p["key"], p["scenario"]), gen_side(p["gen"], view)
        rec.update(t=t, g=g, stamp=stamp_of(t, g), align_file=out / arm / "align" / f"{p['name']}.json")
        if view == "coordinator":
            full = gen_side(p["gen"])
            rec.update(full_stamp=stamp_of(t, full), full_align_file=out / p["arm"] / "align" / f"{p['name']}.json")
        yield rec


def save_alignment(rec: dict, al: Alignment, problems: list[str], aligner: str) -> None:
    af = rec["align_file"]
    af.parent.mkdir(parents=True, exist_ok=True)
    af.write_text(json.dumps({"stamp": rec["stamp"], "guideline": rec["guideline"], "pathway": rec["pathway"],
                              "code": rec["code"], "aligner": aligner, "problems": problems,
                              "alignment": al.model_dump()}, indent=1))


def cached_alignment(rec: dict) -> tuple[Alignment | None, list[str]]:
    """The cached alignment when its stamp matches the pair's trees. Coordinator view with none of its own: the full
    view's (stamp checked on the full trees) with the pruned generated leaves' links dropped, cached as 'derived'."""
    t_ids, g_ids = set(leaves(rec["t"][0])), set(leaves(rec["g"][0]))
    af = rec["align_file"]
    if af.exists():
        c = json.loads(af.read_text())
        if c.get("stamp") == rec["stamp"]:
            al = Alignment.model_validate(c["alignment"])
            return al, check_alignment(al, t_ids, g_ids)
    ff = rec.get("full_align_file")
    if ff and ff.exists():
        c = json.loads(ff.read_text())
        if c.get("stamp") == rec["full_stamp"]:
            al = Alignment(links=[l for l in Alignment.model_validate(c["alignment"]).links if l.gen in g_ids])
            problems = check_alignment(al, t_ids, g_ids)
            save_alignment(rec, al, problems, "derived from the full view")
            return al, problems
    return None, []


def aligned(recs):
    """The records with a valid cached alignment, `al` attached (no model call)."""
    for rec in recs:
        if rec.get("no_tree"):
            continue
        al, problems = cached_alignment(rec)
        if al is not None:
            yield {**rec, "al": al, "alignment_problems": problems}


# ---------------------------------------------------------------- report

def describe(w: dict, t_text: dict, g_text: dict) -> str:
    def name(v):
        src, i = v.split(".", 1)
        return f"{'key' if src == 'T' else 'generated-only'} `{i}` " \
               f"({(t_text if src == 'T' else g_text).get(i, '').split(' | ')[0][:90]})"
    if not w["flip"]:
        return f"the qualifying chart itself: key {w['key']}, generated {w['gen']}"
    vals = w.get("values", {})
    s = "; ".join(name(v) + (f" {vals[v]}" if v in vals else "") for v in w["flip"]) + \
        f" flipped -> key {w['key']}, generated {w['gen']}"
    if w.get("routes_used"):
        s += " | via generated-only route " + ", ".join(w["routes_used"])
    return s


def summary(rows: list[dict]) -> list[str]:
    n = len(rows)
    sc = [r for r in rows if r.get("scored")]
    m = len(sc)
    cnt = lambda f: sum(1 for r in sc if f(r))
    why = lambda w: sum(1 for r in rows if r.get("why") == w)
    return [f"tests {n}; scored {m}; no tree {why('no tree')}; not aligned {why('not aligned')}",
            f"false approval (direct): {cnt(lambda r: r['false_approvals'])}/{m}",
            f"false approval only through a generated-only route (review): "
            f"{cnt(lambda r: r['false_approvals_via_gen_only_routes'] and not r['false_approvals'])}/{m}",
            f"missed good chart: {cnt(lambda r: r['missed_good'])}/{m}",
            f"not ready on the key's qualifying chart: {cnt(lambda r: r['baseline']['gen'] != MET)}/{m}",
            f"not ready when exclusions are silent: generated {cnt(lambda r: r['silence']['gen'] != MET)}/{m}, "
            f"key {cnt(lambda r: r['silence']['key'] != MET)}/{m}",
            f"alignment problems: {cnt(lambda r: r['alignment_problems'])}/{m}"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", action="append", default=[], help="a reduce runner results-*.jsonl (repeatable)")
    ap.add_argument("--store", action="append", default=[], help="a v1.1 score store (repeatable)")
    ap.add_argument("--only", default="", help="guideline ids, comma-separated")
    ap.add_argument("--view", choices=("full", "coordinator"), default="full")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--align-only", action="store_true")
    ap.add_argument("--export-prompts", default="", help="write alignment prompts for pairs with no valid cached "
                    "alignment to <dir>/<arm>/<name>.md instead of calling the model (answer each as <name>.json)")
    ap.add_argument("--import-answers", default="", help="validate <dir>/<arm>/<name>.json answers and cache them")
    a = ap.parse_args()
    if not a.results and not a.store:
        ap.error("give --results and/or --store")
    out = Path(a.out)
    run_id = None
    rows, md = [], ["# Tree diff: generated vs answer key", ""]
    for rec in records([Path(x) for x in a.results], [Path(x) for x in a.store],
                       {x for x in a.only.split(",") if x}, a.view, out):
        head = {k: rec[k] for k in ("arm", "name", "guideline", "pathway", "code", "scenario_id")}
        if rec.get("no_tree"):
            print(f"{rec['arm']} {rec['name']}: no tree", flush=True)
            rows.append({**head, "scored": False, "why": "no tree", "error": rec.get("error")})
            continue
        (t_tree, t_text, t_un, t_thr), (g_tree, g_text, g_un, g_thr) = rec["t"], rec["g"]
        user, t_ids, g_ids = align_prompt(t_tree, t_text, g_tree, g_text)
        al, problems = cached_alignment(rec)
        ans = next((f for f in (Path(a.import_answers) / rec["arm"] / f"{rec['name']}.json",
                                Path(a.import_answers) / f"{rec['name']}.json") if f.exists()), None) \
            if a.import_answers else None
        if al is None and ans:
            al = strip_ids(Alignment.model_validate(json.loads(ans.read_text())))
            problems = check_alignment(al, set(t_ids), set(g_ids))
            save_alignment(rec, al, problems, "imported")
        if al is None and a.export_prompts:
            d = Path(a.export_prompts) / rec["arm"]
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{rec['name']}.md").write_text(
                user + "\n\nReturn only a JSON object: {\"links\": [{\"gen\": \"G.<id>\", \"relation\": "
                "\"same|narrower|broader|negation|part_of|combines|any_of|none\", \"truth\": [\"T.<id>\", ...], "
                "\"why\": \"...\"}, ...]} with one link per G leaf.\n")
            print(f"{rec['arm']} {rec['name']}: prompt exported", flush=True)
            rows.append({**head, "scored": False, "why": "not aligned"})
            continue
        if al is None:
            from app.core import llm
            run_id = run_id or llm.new_run_id()
            al, problems = align(t_tree, t_text, g_tree, g_text, run_id)
            save_alignment(rec, al, problems, "model")
        print(f"{rec['arm']} {rec['name']}: aligned ({len(al.links)} links, {len(problems)} problems)", flush=True)
        if a.align_only:
            continue
        r = compare(t_tree, t_text, t_un, t_thr, g_tree, g_text, g_un, g_thr, al)
        r.update(head, scored=True, alignment_problems=problems, stamp=rec["stamp"],
                 fa_text=[describe(w, t_text, g_text) for w in r["false_approvals"]],
                 fa_route_text=[describe(w, t_text, g_text) for w in r["false_approvals_via_gen_only_routes"]])
        rows.append(r)
        md += [f"## {rec['arm']} · {rec['guideline']} · {rec['code']} · {rec['pathway']}",
               f"variables {r['variables']}; qualifying chart: key {r['baseline']['key']}, generated "
               f"{r['baseline']['gen']}; exclusions silent: key {r['silence']['key']}, generated {r['silence']['gen']}"]
        if r["unanswerable"]["gen"]:
            md.append(f"- generated unanswerable (always review): {', '.join(r['unanswerable']['gen'])}")
        if problems:
            md.append(f"- alignment problems: {'; '.join(problems)}")
        md += [f"- FALSE APPROVAL: {s}" for s in r["fa_text"][:8]]
        md += [f"- false approval via a generated-only route (review): {s}" for s in r["fa_route_text"][:8]]
        md += [f"- missed good chart: {describe(w, t_text, g_text)}" for w in r["missed_good"][:8]]
        for x in r["thresholds"]:
            md.append(f"- threshold: key `{x['key']}` {x['key_threshold'].get('op')} {x['key_threshold'].get('value')} "
                      f"vs generated `{x['gen']}` {x['gen_threshold'].get('op')} {x['gen_threshold'].get('value')}")
        md.append("")
    if a.align_only:
        return
    lines = []
    for arm in dict.fromkeys(r["arm"] for r in rows):
        lines += [f"{arm}:"] + [f"  {s}" for s in summary([r for r in rows if r["arm"] == arm])]
    md[1:1] = ["", "```", *lines, "```", ""]
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(rows, indent=1, default=str))
    (out / "report.md").write_text("\n".join(md))
    print("\n".join(lines))
    print(f"wrote {out / 'results.json'} and {out / 'report.md'}")


if __name__ == "__main__":
    main()
