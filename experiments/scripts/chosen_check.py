"""Was the right section chosen? Decided by where the answer key's criteria sit in the guideline, never by names.

right       = exactly one pathway chosen; >= 80% of the key pathway's locatable criteria inside the chosen lines (its ranges
        plus always_on); every criterion unique to that pathway inside; no criterion unique to a sibling pathway for the
        same code inside; at least one criterion locatable.
unconfirmed = anything else, with the reason. The test errs on the side of doubt: shared criteria repeated in another
        section, keys that split one section into several pathways, and v1.1 ranges that skip a shared lead-in all
        land here. Read these by hand before calling a pick wrong; on 2026-10-10 all 17 of v1.1's unconfirmed picks
        were the right section on reading.
A criterion is located by its verbatim text (whitespace / hyphen / bullet normalised, space-insensitive fallback);
when it occurs more than once, the occurrence nearest the pathway's anchor (median line of its single-occurrence
criteria) is used. Name overlap was the earlier method; it marked correct picks wrong when headings were worded
differently, and was removed.
"""
from __future__ import annotations

import collections
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "truth"))
from check_truth import norm  # noqa: E402

from app.ingest.spans import in_range  # noqa: E402


def _leaves(n: dict) -> list[str]:
    if n["type"] == "leaf":
        return [n["criterion"]]
    if n["type"] == "not":
        return _leaves(n["child"])
    return [x for c in n["children"] for x in _leaves(c)]


class _Doc:
    def __init__(self, spans):
        buf, self.starts, pos = [], [], 0
        for s in spans:
            t = norm(s.text)
            self.starts.append(pos)
            buf.append(t)
            pos += len(t) + 1
        self.text = " ".join(buf)
        self.nospace = self.text.replace(" ", "")
        self.ns2t = [i for i, ch in enumerate(self.text) if ch != " "]

    def line_at(self, off: int) -> int:
        lo, hi = 0, len(self.starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            lo, hi = (mid, hi) if self.starts[mid] <= off else (lo, mid - 1)
        return lo

    def find_all(self, s: str) -> list[tuple[int, int]]:
        s = norm(s)
        if not s:
            return []
        out = [(self.line_at(m.start()), self.line_at(m.end() - 1)) for m in re.finditer(re.escape(s), self.text)]
        if not out:
            ns = s.replace(" ", "")
            out = [(self.line_at(self.ns2t[m.start()]), self.line_at(self.ns2t[m.end() - 1]))
                   for m in re.finditer(re.escape(ns), self.nospace)]
        return out


def _range(rg) -> object:
    if isinstance(rg, str):
        a, _, b = rg.partition("-")
        rg = {"first": a, "last": b or a}
    return type("R", (), rg)()


def check(key: dict, spans: list, narrowed: dict, code: str, pathway: str) -> tuple[str, str]:
    """('right' | 'unconfirmed', reason) for the key pathway named `pathway`, given v1.1's narrowed output (as a dict)."""
    doc, idx = _Doc(spans), {s.id: i for i, s in enumerate(spans)}
    occ = {c["id"]: doc.find_all(c["text"]) for c in key["criteria"]}
    use = collections.defaultdict(set)
    for sc in key["scenarios"]:
        for l in set(_leaves(sc["requires"])):
            use[l].add(sc["name"])
    anchor = {}
    for sc in key["scenarios"]:
        pts = [occ[l][0][0] for l in set(_leaves(sc["requires"])) if len(occ.get(l, [])) == 1]
        anchor[sc["name"]] = statistics.median(pts) if pts else None

    def place(cid: str, a) -> set | None:
        oc = occ.get(cid) or []
        if not oc:
            return None
        pick = oc[0] if len(oc) == 1 or a is None else min(oc, key=lambda o: abs(o[0] - a))
        return set(range(pick[0], pick[1] + 1))

    loc = {}
    for l, names in use.items():
        pl = place(l, anchor.get(pathway) if pathway in names else anchor.get(next(iter(names))))
        if pl is not None:
            loc[l] = pl
    chosen = narrowed.get("chosen") or []
    sibs = {s["name"] for s in key["scenarios"] if code in s.get("applies_to_cpt", []) or not s.get("applies_to_cpt")}
    mine = [l for l in use if pathway in use[l]]
    own = [l for l in mine if use[l] == {pathway}]
    sib_own = [l for l in use if len(use[l]) == 1 and next(iter(use[l])) != pathway and next(iter(use[l])) in sibs]
    lines = set()
    for pid in chosen:
        p = next((x for x in narrowed["pathways"] if x["id"] == pid), None)
        for rg in (p or {}).get("spans", []):
            lines |= {idx[s.id] for s in in_range(spans, _range(rg))}
    located = [l for l in mine if l in loc]
    inside = [l for l in located if loc[l] <= lines]
    own_loc = [l for l in own if l in loc]
    own_in = [l for l in own_loc if loc[l] <= lines]
    sib_in = [l for l in sib_own if l in loc and loc[l] <= lines]
    why = []
    if len(chosen) != 1:
        why.append(f"{len(chosen)} pathways chosen")
    if not located:
        why.append("no key criterion locatable")
    elif len(inside) / len(located) < 0.8:
        why.append(f"only {len(inside)}/{len(located)} of the pathway's criteria inside")
    if len(own_in) < len(own_loc):
        why.append(f"{len(own_loc) - len(own_in)} of its unique criteria outside")
    if sib_in:
        why.append(f"{len(sib_in)} sibling-unique criteria inside")
    return ("unconfirmed" if why else "right"), "; ".join(why)
