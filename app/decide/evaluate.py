"""Step K (code): Expression x Verdicts. No model calls.

Expressions are JSON, leaves are criterion ids:
    "reflux"                                   one requirement
    {"all": [e, ...]}   {"any": [e, ...]}      {"not": e}      {"at_least": {"k": 2, "of": [e, ...]}}

    leaf      the verdict's status
    all       any NOT_MET -> NOT_MET ; else any INSUFFICIENT -> INSUFFICIENT ; else MET
    any       any MET -> MET ; else any INSUFFICIENT -> INSUFFICIENT ; else NOT_MET
    not       MET <-> NOT_MET ; INSUFFICIENT stays
    at_least  MET count >= k -> MET ; MET + INSUFFICIENT >= k -> INSUFFICIENT ; else NOT_MET

Each code is judged against the pathways chosen for it; several pathways for one code, or several codes: the
weakest decides.
"""
from __future__ import annotations

import json
import re
from math import prod
from typing import Any, Optional

from app.core.models import NodeResult, Verdict, VerdictStatus

RANK = {"MET": 2, "INSUFFICIENT": 1, "NOT_MET": 0}
MISSING_COST = 1        # not documented: staff can fix
CONTRADICTED_COST = 10  # the chart says otherwise


# ---------------------------------------------------------------- parse (used by the step H check)


def parse(e: Any, ids: set[str], problems: list[str], where: str = "expr") -> Optional[Any]:
    """Validate and normalise an expression. Problems are appended, never raised. Returns the normalised JSON."""
    if isinstance(e, str):
        if e not in ids:
            problems.append(f"{where}: references unknown criterion '{e}'")
        return e
    if isinstance(e, dict) and len(e) == 1:
        (op, arg), = e.items()
        if op in ("all", "any"):
            if not isinstance(arg, list) or not arg:
                problems.append(f"{where}: '{op}' needs a non-empty list")
                return None
            kids = [parse(x, ids, problems, f"{where}/{op}[{i}]") for i, x in enumerate(arg)]
            kids = [k for k in kids if k is not None]
            if not kids:
                return None
            return kids[0] if len(kids) == 1 else {op: kids}
        if op == "not":
            if isinstance(arg, list):
                if len(arg) != 1:
                    problems.append(f"{where}: 'not' takes one expression; wrap several in any/all")
                    return None
                arg = arg[0]
            child = parse(arg, ids, problems, f"{where}/not")
            return {"not": child} if child is not None else None
        if op == "at_least":
            if not isinstance(arg, dict) or not isinstance(arg.get("k"), int) or not isinstance(arg.get("of"), list):
                problems.append(f"{where}: 'at_least' needs {{\"k\": int, \"of\": [...]}}")
                return None
            kids = [parse(x, ids, problems, f"{where}/at_least[{i}]") for i, x in enumerate(arg["of"])]
            kids = [k for k in kids if k is not None]
            k = arg["k"]
            if not 1 <= k <= len(kids):
                problems.append(f"{where}: at_least k={k} with {len(kids)} items")
                return None
            return {"at_least": {"k": k, "of": kids}}
    problems.append(f"{where}: cannot parse expression {json.dumps(e)[:120]}")
    return None


# an id may start with digits ("37765_with_37766"); a bare number is AT_LEAST's k
_TOK = re.compile(r"\s*(\(|\)|,|&&|\|\||!|\d+(?=[A-Za-z_])[A-Za-z0-9_.\-]*|[A-Za-z_][A-Za-z0-9_.\-]*|\d+)")
_KW = {"and", "or", "not", "at_least", "atleast", "of"}


def from_logic(s: str, problems: list[str], where: str = "logic") -> Optional[Any]:
    """A logic string -> the JSON expression: ids joined by AND, OR, NOT and parentheses, NOT binding tightest, then
    AND, then OR; AT_LEAST k OF (a, b, c). Case-insensitive; &&, ||, ! accepted. Problems are appended."""
    toks, pos = [], 0
    s = re.sub(r"(?i)\bat\s+least\b", "AT_LEAST", s or "")
    while pos < len(s):
        m = _TOK.match(s, pos)
        if not m or not m.group(1):
            if s[pos:].strip():
                problems.append(f"{where}: cannot read {s[pos:pos + 30]!r}")
                return None
            break
        toks.append(m.group(1))
        pos = m.end()
    i = 0

    def peek():
        return toks[i].lower() if i < len(toks) else None

    def take(want=None):
        nonlocal i
        t = toks[i] if i < len(toks) else None
        if want and (t or "").lower() != want:
            raise ValueError(f"expected {want!r}, found {t!r}")
        i += 1
        return t

    def orx():
        kids = [andx()]
        while peek() in ("or", "||"):
            take()
            kids.append(andx())
        return kids[0] if len(kids) == 1 else {"any": kids}

    def andx():
        kids = [unary()]
        while peek() in ("and", "&&"):
            take()
            kids.append(unary())
        return kids[0] if len(kids) == 1 else {"all": kids}

    def unary():
        if peek() in ("not", "!"):
            take()
            return {"not": unary()}
        return primary()

    def primary():
        t = peek()
        if t == "(":
            take()
            e = orx()
            take(")")
            return e
        if t in ("at_least", "atleast"):
            take()
            k = int(take())
            if peek() == "of":
                take()
            take("(")
            kids = [orx()]
            while peek() == ",":
                take()
                kids.append(orx())
            take(")")
            return {"at_least": {"k": k, "of": kids}}
        if t is None or t in _KW or t in (")", ","):
            raise ValueError(f"expected a criterion id, found {t!r}")
        return take()

    try:
        e = orx()
        if i != len(toks):
            raise ValueError(f"unexpected {toks[i]!r}")
        return e
    except (ValueError, IndexError) as x:
        problems.append(f"{where}: {x} in {s[:160]!r}")
        return None


def leaf_ids(e: Any) -> list[str]:
    """Criterion ids in order of appearance, deduped."""
    out: list[str] = []

    def walk(x):
        if isinstance(x, str):
            if x not in out:
                out.append(x)
        elif isinstance(x, dict):
            (op, arg), = x.items()
            if op == "not":
                walk(arg)
            elif op == "at_least":
                for c in arg["of"]:
                    walk(c)
            else:
                for c in arg:
                    walk(c)
    walk(e)
    return out


# ---------------------------------------------------------------- compile


def _confidence(kind: str, status: VerdictStatus, kids: list[NodeResult], k: int = 0) -> float:
    """all MET = product; any MET = noisy-or over MET children; at_least MET = product of the k most confident MET
    children; INSUFFICIENT = min over non-MET children; NOT_MET rules are placeholders the owner has not specified."""
    if not kids:
        return 1.0
    met = sorted((c.confidence for c in kids if c.status == "MET"), reverse=True)
    if status == "MET":
        if kind == "all":
            return prod(c.confidence for c in kids)
        if kind == "any":
            return 1 - prod(1 - c for c in met)
        return prod(met[:k])
    if status == "NOT_MET":
        if kind == "all":
            return 1 - prod(1 - c.confidence for c in kids if c.status == "NOT_MET")
        return prod(c.confidence for c in kids)
    return min([c.confidence for c in kids if c.status != "MET"] or [1.0])


def compile_expr(e: Any, verdicts: dict[str, Verdict]) -> NodeResult:
    if isinstance(e, str):
        v = verdicts.get(e)
        if v is None:
            return NodeResult(type="leaf", status="INSUFFICIENT", criterion=e, confidence=0.0)
        return NodeResult(type="leaf", status=v.status, criterion=e, confidence=v.confidence)
    (op, arg), = e.items()
    if op == "not":
        ch = compile_expr(arg, verdicts)
        s: VerdictStatus = {"MET": "NOT_MET", "NOT_MET": "MET", "INSUFFICIENT": "INSUFFICIENT"}[ch.status]
        return NodeResult(type="not", status=s, children=[ch], confidence=ch.confidence)
    if op == "at_least":
        kids = [compile_expr(x, verdicts) for x in arg["of"]]
        k = arg["k"]
        met = sum(c.status == "MET" for c in kids)
        ins = sum(c.status == "INSUFFICIENT" for c in kids)
        s = "MET" if met >= k else "INSUFFICIENT" if met + ins >= k else "NOT_MET"
        return NodeResult(type="at_least", k=k, status=s, children=kids, confidence=_confidence("at_least", s, kids, k))
    kids = [compile_expr(x, verdicts) for x in arg]
    st = [c.status for c in kids]
    if op == "all":
        s = "NOT_MET" if "NOT_MET" in st else "INSUFFICIENT" if "INSUFFICIENT" in st else "MET"
    else:
        s = "MET" if "MET" in st else "INSUFFICIENT" if "INSUFFICIENT" in st else "NOT_MET"
    return NodeResult(type=op, status=s, children=kids, confidence=_confidence(op, s, kids))


# ---------------------------------------------------------------- the deciding path


def cost(n: NodeResult) -> int:
    if n.status == "MET":
        return 0
    if n.type == "leaf":
        return MISSING_COST if n.status == "INSUFFICIENT" else CONTRADICTED_COST
    if n.type == "not":
        return cost(n.children[0]) if n.children[0].status != "MET" else CONTRADICTED_COST
    if n.type == "all":
        return sum(cost(c) for c in n.children)
    if n.type == "any":
        return min((cost(c) for c in n.children), default=1)
    if n.type == "at_least":
        need = (n.k or 1) - sum(c.status == "MET" for c in n.children)
        return sum(sorted(cost(c) for c in n.children if c.status != "MET")[:max(need, 0)])
    return 1


def _met_leaves(n: NodeResult) -> int:
    return sum(1 for x in leaves(n) if x.status == "MET")


def _cheapest(kids: list[NodeResult], n: int = 1) -> list[NodeResult]:
    return sorted(kids, key=lambda c: (cost(c), -_met_leaves(c)))[:n]


def leaves(n: NodeResult) -> list[NodeResult]:
    if n.type == "leaf":
        return [n]
    return [x for c in n.children for x in leaves(c)]


def path_nodes(n: NodeResult) -> list[NodeResult]:
    """Leaf and `not` nodes on the deciding path: every child of an `all`; for `any` the MET children when MET, else
    the cheapest branch; for `at_least` the MET children plus, when short, the cheapest of the rest. This is what
    the checklist and the packet list."""
    if n.type in ("leaf", "not"):
        return [n]
    if n.type == "all":
        return [x for c in n.children for x in path_nodes(c)]
    met = [c for c in n.children if c.status == "MET"]
    if n.type == "any":
        pick = met if n.status == "MET" else _cheapest(n.children)
    else:
        rest = [c for c in n.children if c.status != "MET"]
        pick = met + (_cheapest(rest, (n.k or 1) - len(met)) if n.status != "MET" else [])
    return [x for c in pick for x in path_nodes(c)]


def missing(n: NodeResult) -> list[NodeResult]:
    """Leaf or `not` nodes to fix, along the cheapest path to MET."""
    return [x for x in path_nodes(n) if x.status != "MET"]


def rank(n: NodeResult) -> tuple:
    return (RANK[n.status], -cost(n), n.confidence)


def weakest(nodes: list[NodeResult]) -> Optional[NodeResult]:
    return min(nodes, key=rank) if nodes else None
