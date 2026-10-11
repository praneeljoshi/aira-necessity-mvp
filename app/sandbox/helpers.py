"""helpers.py: uploaded into the model's sandbox next to guideline.txt, order.json and codes.json. The model's tree.py
imports it. The same file is imported by the host (app/reduce_code.py) to re-check what comes back.

Checks are citation and well-formedness only: a quote is printed in the guideline, ids are unique, every expression
leaf is a condition or a block, every condition is used, the expression parses, thresholds are well formed. No
structural rules.

    from helpers import C, block, write, th
    reflux = C("reflux", "There is demonstrated saphenous reflux", "Does a duplex show reflux in the vein to be treated?")
    base = block("osa_adult", [ahi_15, adult], {"all": ["ahi_15", "adult"]})
    write(indication=["...the sentence(s) that grant it..."], not_covered=None,
          conditions=[reflux, ahi_15, adult], expr={"all": ["reflux", "osa_adult"]}, blocks=[base], notes="...")
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = ""
_t = Path("guideline.txt")
if _t.exists():
    T = _t.read_text()

OPS = {">=", ">", "<=", "<", "=="}


class QuoteNotFound(Exception):
    pass


class TreeError(Exception):
    pass


def _flat(text: str) -> str:
    return " ".join(ln.strip() for ln in text.splitlines() if ln.strip())


def find(quote: str, text: str = None):
    """The quote as printed (the text's own characters), or None. Forgiven: whitespace and line breaks, and a hyphen
    broken across a line ("inter- fere")."""
    flat = _flat(T if text is None else text)
    words = (quote or "").split()
    if not words:
        return None
    for pat in (r"\s+".join(re.escape(w) for w in words),
                r"\s+".join("(?:-\\s)?".join(re.escape(ch) for ch in w) for w in words)):
        m = re.search(pat, flat)
        if m:
            return m.group(0)
    return None


def fq(quote: str) -> str:
    got = find(quote)
    if got is None:
        raise QuoteNotFound(f"QUOTE NOT FOUND: {quote!r}")
    return got


def th(op: str, value, unit: str = None) -> dict:
    return {"op": op, "value": value, "unit": unit}


def C(id: str, quote: str, question: str, threshold: dict = None, answerable: bool = True) -> dict:
    """One condition. The quote is checked now, so a wrong quote fails where it is written."""
    return {"id": id, "quote": fq(quote), "question": question, "threshold": threshold, "answerable": answerable}


def block(name: str, conditions: list, expr) -> dict:
    """A reusable named group: write `name` as a leaf in an expression and it stands for `expr`."""
    return {"name": name, "conditions": [c["id"] for c in conditions], "expr": expr, "_conds": conditions}


# ---------------------------------------------------------------- checks (shared with the host)


def walk(e, leaf):
    if isinstance(e, str):
        leaf(e)
        return
    if not isinstance(e, dict) or len(e) != 1:
        raise TreeError(f"cannot parse expression {json.dumps(e)[:120]}")
    (op, arg), = e.items()
    if op in ("all", "any"):
        if not isinstance(arg, list) or not arg:
            raise TreeError(f"'{op}' needs a non-empty list")
        for x in arg:
            walk(x, leaf)
    elif op == "not":
        walk(arg[0] if isinstance(arg, list) and len(arg) == 1 else arg, leaf)
    elif op == "at_least":
        if not isinstance(arg, dict) or not isinstance(arg.get("k"), int) or not isinstance(arg.get("of"), list):
            raise TreeError("'at_least' needs {\"k\": int, \"of\": [...]}")
        if not 1 <= arg["k"] <= len(arg["of"]):
            raise TreeError(f"at_least k={arg['k']} with {len(arg['of'])} items")
        for x in arg["of"]:
            walk(x, leaf)
    else:
        raise TreeError(f"unknown operator '{op}' (use all, any, not, at_least)")


def expand(e, blocks: dict, seen=()):
    """Block names replaced by their expressions (recursively)."""
    if isinstance(e, str):
        if e in blocks:
            if e in seen:
                raise TreeError(f"block '{e}' refers to itself")
            return expand(blocks[e], blocks, seen + (e,))
        return e
    (op, arg), = e.items()
    if op == "not":
        return {"not": expand(arg[0] if isinstance(arg, list) and len(arg) == 1 else arg, blocks, seen)}
    if op == "at_least":
        return {"at_least": {"k": arg["k"], "of": [expand(x, blocks, seen) for x in arg["of"]]}}
    return {op: [expand(x, blocks, seen) for x in arg]}


def problems(tree: dict, text: str = None) -> list:
    """Every citation and well-formedness problem in a tree (a list of strings; empty = OK)."""
    out = []
    conds = tree.get("conditions") or []
    ids = [c.get("id") for c in conds]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        out.append(f"condition ids used twice: {', '.join(dup)}")
    for c in conds:
        if not c.get("id") or not c.get("question"):
            out.append(f"condition {c.get('id')!r}: needs an id and a question")
        if find(c.get("quote") or "", text) is None:
            out.append(f"condition {c.get('id')!r}: QUOTE NOT FOUND: {(c.get('quote') or '')[:100]!r}")
        t = c.get("threshold")
        if t is not None and (not isinstance(t, dict) or t.get("op") not in OPS):
            out.append(f"condition {c.get('id')!r}: threshold must be {{op: one of >=, >, <=, <, ==; value; unit}}; "
                       "a range is two conditions, one per bound (or one with no threshold and the range in the question)")
    for k in ("indication", "not_covered"):
        v = tree.get(k)
        for q in ([v] if isinstance(v, str) else v or []):
            if find(q, text) is None:
                out.append(f"{k}: QUOTE NOT FOUND: {q[:100]!r}")
    blocks = {b["name"]: b["expr"] for b in tree.get("blocks") or []}
    clash = sorted(set(blocks) & set(ids))
    if clash:
        out.append(f"names used for both a block and a condition: {', '.join(clash)}")
    used = set()

    def leaf(x):
        if x not in ids and x not in blocks:
            out.append(f"expression leaf {x!r} is neither a condition id nor a block name")
        used.add(x)
    try:
        walk(tree.get("expression"), leaf)
        for name, e in blocks.items():
            walk(e, leaf)
        flat = expand(tree.get("expression"), blocks)
        walk(flat, lambda x: None)
    except TreeError as x:
        out.append(f"expression: {x}")
    except (KeyError, TypeError, ValueError, AttributeError) as x:
        out.append(f"expression: cannot read it ({type(x).__name__}: {x})")
    unused = [i for i in ids if i not in used]
    if unused and tree.get("expression") is not None:
        out.append(f"conditions not used in the expression: {', '.join(unused)}")
    return out


def write(indication, not_covered, conditions, expr, blocks=None, notes=None, path="tree.json"):
    """Check and write tree.json; prints OK, or raises TreeError listing every problem."""
    blocks = blocks or []
    conds = list(conditions)
    have = {c["id"] for c in conds}
    for b in blocks:                          # a block's conditions count as listed
        for c in b.get("_conds", []):
            if c["id"] not in have:
                conds.append(c)
                have.add(c["id"])
    if isinstance(indication, (list, tuple)):
        indication = [fq(q) for q in indication]
    elif indication:
        indication = fq(indication)
    tree = {"indication": indication or None,
            "not_covered": fq(not_covered) if not_covered else None,
            "conditions": conds, "blocks": [{"name": b["name"], "expr": b["expr"]} for b in blocks],
            "expression": expr, "notes": notes or ""}
    bad = problems(tree)
    if bad:
        raise TreeError("tree has problems:\n- " + "\n- ".join(bad))
    Path(path).write_text(json.dumps(tree, indent=1))
    print("OK", path, f"{len(conds)} conditions")
    return tree


if __name__ == "__main__":       # python helpers.py tree.json: re-check a written tree
    t = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "tree.json").read_text())
    bad = problems(t)
    print("OK" if not bad else "\n".join(bad))
