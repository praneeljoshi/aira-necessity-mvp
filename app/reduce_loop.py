"""Step H as loose with an external fixpoint loop (STEP_H=loose-loop), and loose itself with the reduce runner's inputs
and spend (STEP_H=loose). Drop-ins for criteria.build; the loose prompts and criteria.build's behaviour are unchanged.

    loose:      criteria.build (one reading, one retry on check problems, the add-only audit), given the runner's
                inputs (the order with its allow-listed fields and plan, the confirmed heading) and a spend tally
    loose-loop: round 1 = criteria_guideline_loop (loose's prompt + "Be exhaustive"); round n >= 2 = the same prompt +
                the previous round's whole extraction + loop_round ("re-read; return it again, unchanged or
                corrected"). Each round gets loose's check and one retry. The loop stops when the extraction's
                canonical form (leaves by normalized quote / threshold / answerable / polarity, and the expression over
                those leaves with children sorted) repeats: unchanged = fixpoint; seen earlier = cycle (the largest of
                the cycle stands); MAX_ROUNDS = cap (the larger of the last two stands); a round that still fails its
                checks after the retry ends the loop with the last valid tree. Removals are allowed and noted with the
                round's notes. Then loose's add-only audit, once.

Code checks citations and well-formedness only; convergence is on the model's extraction, never on line coverage.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from . import criteria, llm, log
from .criteria import HOut
from .evaluate import leaf_ids
from .models import CriteriaSet, Criterion, Expression, Narrowed, Procedure, Selection, Span

logger = log.get("reduce_loop")

MAX_ROUNDS = 8


# ---------------------------------------------------------------- canonical form


def _norm(q: Optional[str]) -> str:
    return re.sub(r"\s+", " ", re.sub(r"-\s+", "", (q or "").lower())).strip(" .;,:")


def _leaf(c: Criterion) -> tuple:
    t = c.threshold
    return (_norm(c.quote), (t.op, str(t.value), _norm(t.unit)) if t else None, bool(c.answerable))


def _expr(e, leaf: dict) -> tuple:
    """The expression over leaf keys; all / any children sorted, so order and ids do not count."""
    if isinstance(e, str):
        return ("leaf", leaf.get(e, ("unknown", e)))
    (op, arg), = e.items()
    if op == "not":
        return ("not", _expr(arg, leaf))
    if op == "at_least":
        return ("at_least", arg["k"], tuple(sorted((_expr(x, leaf) for x in arg["of"]), key=repr)))
    return (op, tuple(sorted((_expr(x, leaf) for x in arg), key=repr)))


def _negated(e, neg=False, out=None) -> set:
    out = set() if out is None else out
    if isinstance(e, str):
        if neg:
            out.add(e)
        return out
    (op, arg), = e.items()
    for x in ([arg] if op == "not" else arg["of"] if op == "at_least" else arg):
        _negated(x, neg ^ (op == "not"), out)
    return out


def canonical(crit: list[Criterion], exprs: list[Expression]) -> tuple:
    """(leaves with polarity, expressions): renaming ids, rewording questions or reordering children changes nothing."""
    leaf = {c.id: _leaf(c) for c in crit}
    used = {i for e in exprs for i in leaf_ids(e.expr)}
    neg = {i for e in exprs for i in _negated(e.expr)}
    leaves = frozenset((leaf[i], i in neg) for i in used if i in leaf)
    return leaves, tuple(sorted((e.pathway, _expr(e.expr, leaf)) for e in exprs))


def _size(r: dict) -> int:
    return len({i for e in r["exprs"] for i in leaf_ids(e.expr)})


def _shown(h: HOut) -> str:
    return json.dumps({"notes": h.notes, "criteria": [c.model_dump() for c in h.criteria],
                       "logic": [x.model_dump() for x in h.logic]}, indent=1)


# ---------------------------------------------------------------- the loop


def loop(base: str, spans: list[Span], want: list[str], run_id: str, model: str, tally: dict) -> tuple[dict, dict]:
    """(the round that stands {h, problems, crit, exprs}, the record)."""
    rounds: list[dict] = []
    seen: dict[tuple, int] = {}
    rec = {"rounds": 0, "converged": False, "reason": "cap", "counts": [], "added": [], "removed": []}
    final = None
    for r in range(1, MAX_ROUNDS + 1):
        prompt = base if r == 1 else base + "\n\n" + llm.prompt("loop_round", previous=_shown(rounds[-1]["h"]))
        h, problems, crit, exprs = criteria.first_pass(prompt, spans, want, run_id, model, "criteria_loop", tally)
        rec["rounds"] = r
        if problems:
            if rounds:                   # the last valid tree stands
                rec["reason"] = "check-fail"
                logger.warning("loop round %d failed its checks after the retry; round %d stands", r, len(rounds))
                break
            final = {"h": h, "problems": problems, "crit": crit, "exprs": exprs}     # nothing valid: as loose would
            rec["reason"] = "check-fail"
            break
        cur = {"h": h, "problems": [], "crit": crit, "exprs": exprs, "canon": canonical(crit, exprs), "round": r}
        rec["counts"].append(_size(cur))
        if rounds:
            prev = rounds[-1]
            pk = {_leaf(c): c.id for c in prev["crit"] if c.id in {i for e in prev["exprs"] for i in leaf_ids(e.expr)}}
            ck = {_leaf(c): c.id for c in crit if c.id in {i for e in exprs for i in leaf_ids(e.expr)}}
            gone = [pk[k] for k in pk if k not in ck]
            rec["added"].append({"round": r, "ids": [ck[k] for k in ck if k not in pk]})
            if gone:
                rec["removed"].append({"round": r, "ids": gone, "why": (h.notes or "")[:500]})
                logger.info("loop round %d removed %s", r, ", ".join(gone))
        if rounds and cur["canon"] == rounds[-1]["canon"]:
            rec.update(converged=True, reason="fixpoint")
            final = cur
            break
        if cur["canon"] in seen:
            cyc = rounds[seen[cur["canon"]] - 1:] + [cur]
            final = max(cyc, key=_size)
            rec["reason"] = "cycle"
            logger.warning("loop: cycle at round %d (back to round %d)", r, seen[cur["canon"]])
            break
        seen[cur["canon"]] = r
        rounds.append(cur)
    if final is None:                    # the cap, or a check failure after a valid round
        final = max(rounds[-2:], key=_size) if rec["reason"] == "cap" else rounds[-1]
        if rec["reason"] == "cap":
            logger.warning("loop: no fixpoint after %d rounds", rec["rounds"])
    rec["kept_round"] = final.get("round")
    return final, rec


def note(rec: dict) -> str:
    n = rec["rounds"]
    head = {"fixpoint": f"Loop: fixpoint after {n} rounds",
            "cycle": f"Loop: no fixpoint after {n} rounds (cycle)",
            "cap": f"Loop: no fixpoint after {n} rounds (cap)",
            "check-fail": (f"Loop: round {n} failed its checks; the last valid tree (round {rec.get('kept_round')}) stands"
                           if rec.get("kept_round") else f"Loop: round {n} failed its checks")}[rec["reason"]]
    out = [head + f"; conditions per round {rec['counts']}"]
    out += [f"Loop removed in round {x['round']}: {', '.join(x['ids'])}. The model's notes: {x['why']}"
            for x in rec["removed"]]
    return "\n".join(out)


# ---------------------------------------------------------------- the drop-ins


def _cost(run_id: str, step: str, tally: dict) -> None:
    llm._log(run_id, f"{step}-cost", {"all": {**tally, "dollars": llm.dollars(tally)}})


def loose(spans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
          procedure: Optional[Procedure] = None, extra: Optional[dict] = None,
          indication: Optional[str] = None) -> CriteriaSet:
    """STEP_H=loose through the reduce runner: criteria.build with the runner's inputs, and its spend."""
    tally: dict = {}
    cs = criteria.build(spans, n, sel, key, run_id, procedure, extra=extra, indication=indication, tally=tally)
    _cost(run_id, "criteria_loose", tally)
    return cs


def build(spans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
          procedure: Optional[Procedure] = None, extra: Optional[dict] = None,
          indication: Optional[str] = None) -> CriteriaSet:
    want, v = criteria.inputs(spans, n, sel, procedure, extra, indication)
    base = llm.prompt("criteria_guideline_loop", **v)
    model = llm.pick_models()[0]
    tally: dict = {}
    final, rec = loop(base, spans, want, run_id, model, tally)
    h = final["h"].model_copy(update={"notes": "\n\n".join(x for x in (final["h"].notes, note(rec)) if x)})
    cs = criteria.audit(h, list(final["problems"]), final["crit"], final["exprs"], spans, want, v, key, run_id, model,
                        tally)
    cs.loop = rec
    llm._log(run_id, "criteria_loop-rounds", rec)
    _cost(run_id, "criteria_loop", tally)
    logger.info("criteria (loose-loop) %s: %s after %d round(s), counts %s, %d criteria, %s, $%.2f", key, rec["reason"],
                rec["rounds"], rec["counts"], len(cs.criteria), cs.status, llm.dollars(tally))
    return cs
