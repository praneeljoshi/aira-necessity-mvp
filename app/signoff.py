"""Sign-off before Ready, in the review flow: a case whose computed result is ready (queue "ready") reads "Ready for
sign-off" until a person signs it off; only then is it "Ready to submit" and the packet is final.

    data/results/<chart_id>/signoff.json     {by, at, fingerprint, run_id, determination, queue, packet, strikes,
                                              additions, tree: {criteria_key, step_h, model, run_id},
                                              withdrawn: null | {by, at}}

The record holds a fingerprint of what was signed (result.json, meta.json, the active strikes and the active
additions). Any later change to the case, a strike or an un-strike, an addition or taking one off (K-L again), a
re-run, a re-check, rewrites result.json / meta.json, the strikes or the additions and so no longer matches: the sign-off is then stale and the case is back to "Ready for sign-off". Nothing
deletes the record; `stale` and `withdrawn` say why it no longer counts. A result that is not ready cannot be signed
off, nor one with a requirement neither accepted nor struck (app/accepts.py, review.progress). The model never takes
part.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Optional

from . import accepts, additions, admin, store, strikes


NAME_MAX = 60                      # characters of a signer's name kept (the sign-in box allows as many)


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _path(chart_id: str):
    return store.RESULTS / chart_id / "signoff.json"


def load(chart_id: str) -> Optional[dict]:
    p = _path(chart_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


def fingerprint(chart_id: str) -> str:
    d = store.RESULTS / chart_id
    h = hashlib.sha1()
    for name in ("result.json", "meta.json"):
        p = d / name
        h.update(p.read_bytes() if p.exists() else b"-")
    h.update(json.dumps(sorted(x["id"] for x in strikes.active(chart_id))).encode())
    adds = sorted(x["id"] for x in additions.active(chart_id))
    if adds:                                  # no additions: the fingerprint is what it was before additions existed
        h.update(json.dumps(adds).encode())
    back = sorted(x["id"] for x in admin.active(chart_id))
    if back:                                  # likewise for admin leaves a person restored ("Ask it anyway")
        h.update(("unpruned" + json.dumps(back)).encode())
    acc = sorted(x["id"] for x in accepts.active(chart_id))
    if acc:                                   # likewise for accepts: taking one back after signing makes it stale
        h.update(("accepts" + json.dumps(acc)).encode())
    return h.hexdigest()[:16]


def _result(chart_id: str) -> Optional[dict]:
    p = store.RESULTS / chart_id / "result.json"
    return json.loads(p.read_text()) if p.exists() else None


def ready(r: Optional[dict]) -> bool:
    """A result that can be signed off: ready, or documented (MET) with nothing to review but requirements no chart
    can show (`confirm_reasons`); those are closed one by one by "Confirmed outside the chart" (an accept of a
    requirement marked confirm), which sign-off needs like any other accept (review.progress_of)."""
    if not r:
        return False
    if r.get("queue") == "ready":
        return True
    rs, ok = r.get("review_reasons") or [], set(r.get("confirm_reasons") or [])
    return r.get("determination") == "MET" and bool(rs) and all(x in ok for x in rs)


def view(chart_id: str) -> dict:
    """state: not_ready (no result, or a result that is not ready) · needed (ready, not signed off, or signed off
    before the case changed) · signed. `record` is the stored sign-off whatever its state; `stale` = it was made
    on an earlier version of the case; `strikes` = the requirements removed for this case and `additions` = the lines
    added to its checklist, for the signer to see; `gaps` = how many of the removals were of requirements the chart
    did not document (the page keeps saying so, and sign-off needs `gaps_checked`)."""
    r = _result(chart_id)
    rec = load(chart_id)
    ready_ = ready(r)
    valid = bool(rec and not rec.get("withdrawn") and rec.get("fingerprint") == fingerprint(chart_id))
    state = "signed" if ready_ and valid else "needed" if ready_ else "not_ready"
    return {"state": state, "ready": ready_, "signed": state == "signed", "record": rec,
            "stale": bool(rec and not rec.get("withdrawn") and not valid), "strikes": strikes.active(chart_id),
            "gaps": len(gap_strikes(chart_id)),
            "additions": [additions.summary(x) for x in additions.active(chart_id)]}


def state_of(chart_id: str) -> str:
    return view(chart_id)["state"]


class Conflict(Exception):
    """The case is not the one the signer saw (another tab changed it), or a sign-off already stands: 409."""


def gap_strikes(chart_id: str) -> list[dict]:
    """The active removals of requirements the chart did not document (or contradicted) when struck: a case ready
    only because of them is signed off only with an explicit check (`gaps_checked`), and says so after."""
    from .tree import BAD                      # tree is a heavier module; never needed at import
    return [x for x in strikes.active(chart_id) if x.get("was") in BAD]


def sign(chart_id: str, by: Optional[str], version: Optional[str] = None, gaps_checked: bool = False) -> dict:
    """`version` is the case document's `version` (= fingerprint) the signer's page was drawn from: a sign-off is
    tied to what the signer saw, so a different one is refused (Conflict). Older callers that send none are taken
    at the case as it is now. A second sign-off while a valid one stands is refused too."""
    by = (by or "").strip()[:NAME_MAX]
    if not by:
        raise ValueError("say who is signing off")
    r = _result(chart_id)
    if not r:
        raise LookupError("this case has no result yet")
    if not ready(r):
        raise PermissionError("only a case that is ready can be signed off")
    now_fp = fingerprint(chart_id)
    if version is not None and version != now_fp:
        raise Conflict("this case changed after the page was drawn; look at it again before signing off")
    rec0 = load(chart_id)
    if rec0 and not rec0.get("withdrawn") and rec0.get("fingerprint") == now_fp:
        raise Conflict(f"Already signed off by {rec0.get('by') or 'a person'}")
    from .review import progress                 # review imports this module; never at module top
    p = progress(chart_id)
    if not p["can_sign"]:
        raise PermissionError(f"accept or strike every requirement first ({len(p['open'])} still open)")
    gaps = gap_strikes(chart_id)
    if gaps and not gaps_checked:
        raise ValueError(f"{len(gaps)} requirement{'s' if len(gaps) > 1 else ''} not in the case "
                         f"{'were' if len(gaps) > 1 else 'was'} removed; confirm you checked the removals before signing off")
    rec = {"by": by, "at": now(), "fingerprint": fingerprint(chart_id), "run_id": r.get("run_id"),
           "determination": r.get("determination"), "queue": r.get("queue"),
           "packet": [p.get("criterion") for p in r.get("packet") or []],
           "strikes": [{k: x.get(k) for k in ("id", "criterion", "words", "code", "reason", "by", "at")} for x in strikes.active(chart_id)],
           "additions": [additions.summary(x) for x in additions.active(chart_id)],
           "accepts": [{k: x.get(k) for k in ("id", "criterion", "words", "by", "at")} for x in accepts.active(chart_id)],
           "gaps": [x.get("id") for x in gaps], "gaps_checked": bool(gaps), "version": now_fp,
           "tree": accepts.tree_of(chart_id), "withdrawn": None}
    _path(chart_id).write_text(json.dumps(rec, indent=2))
    return rec


def withdraw(chart_id: str, by: Optional[str], why: str = "withdrawn") -> Optional[dict]:
    """A person takes the sign-off back, or the case changed under it (`why` = "strike" / "un-strike" / "addition" /
    "addition taken off"; the fingerprint would catch the change too, this makes it explicit even within the same
    second)."""
    rec = load(chart_id)
    if not rec or rec.get("withdrawn"):
        return None
    rec["withdrawn"] = {"by": (by or "").strip() or None, "at": now(), "why": why}
    _path(chart_id).write_text(json.dumps(rec, indent=2))
    return rec
