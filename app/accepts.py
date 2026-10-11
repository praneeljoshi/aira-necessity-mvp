"""A coordinator accepts a requirement: she approves the ruling and the chart evidence the check gave it, for this
case. Accept means proof: for a requirement the chart does not document yet (or contradicts) the same record means
"add it to the ask" (the message to the surgeon); it never counts as accepted (review.case_view: `accepted` vs
`in_ask`). Accepting is how the case is built toward a submission: sign-off needs every requirement accepted or struck
and nothing left to ask (app/review.progress), and the packet and the message to the surgeon are assembled from
accepted items only.

    data/results/<chart_id>/accepts.json     {"accepts": [{id, criterion, words, basis, mark, by, at,
                                               undone: null | {by, at}, tree: {criteria_key, step_h, model, run_id}}]}

`basis` pins what was accepted: the run id, the checklist (criteria key), the criterion id and a hash of the
verdict it was shown with. A re-run (a new run id, or a new verdict) no longer matches, so the accept is stale and
no longer counts, the same way a sign-off goes stale; K-L again after a strike or an addition keep the run id and
the stored verdicts, so accepts survive them. Append-only in spirit: Undo sets `undone`.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Optional

from . import store
from .models import Verdict


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _path(chart_id: str):
    return store.RESULTS / chart_id / "accepts.json"


def load(chart_id: str) -> list[dict]:
    p = _path(chart_id)
    if not p.exists():
        return []
    try:
        return list(json.loads(p.read_text()).get("accepts") or [])
    except ValueError:
        return []


def _save(chart_id: str, items: list[dict]) -> None:
    p = _path(chart_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"accepts": items}, indent=2))


TREE_FIELDS = ("criteria_key", "step_h", "model", "run_id")


def tree_of(chart_id: str) -> dict:
    """The tree this case's checklist was built with, from status.json's `tree` (pipeline._tree_meta): {criteria_key,
    step_h, model, run_id}, each None when the status or the field is absent. Stamped on accept and sign-off records."""
    from .status import load_status
    t = (load_status(chart_id) or {}).get("tree") or {}
    return {k: t.get(k) for k in TREE_FIELDS}


def active(chart_id: str) -> list[dict]:
    return [x for x in load(chart_id) if not x.get("undone")]


def basis(run_id: Optional[str], cs_key: Optional[str], criterion: str, v: Optional[Verdict]) -> str:
    vh = hashlib.sha1(json.dumps(v.model_dump(by_alias=True, exclude_none=True) if v else None, sort_keys=True).encode())
    return f"{run_id}:{cs_key}:{criterion}:{vh.hexdigest()[:12]}"


def current(chart_id: str, bases: dict[str, str]) -> dict[str, dict]:
    """{criterion: the accept that still counts}, given each requirement's basis now."""
    out: dict[str, dict] = {}
    for x in active(chart_id):
        if bases.get(x.get("criterion")) == x.get("basis"):
            out[x["criterion"]] = x
    return out


def add(chart_id: str, criterion: str, words: str, b: str, mark: str, by: Optional[str],
        as_: Optional[str] = None, together: Optional[str] = None) -> dict:
    """`as_` ("accept" | "ask") is the person's choice for requirements decided together (review.merge_groups): it
    overrides what the evidence alone would say; `together` is the id it was decided with."""
    items = load(chart_id)
    for x in items:                      # one live accept per requirement: an older one (stale) is closed
        if x.get("criterion") == criterion and not x.get("undone"):
            x["undone"] = {"by": by, "at": now(), "why": "accepted again"}
    item = {"id": uuid.uuid4().hex[:8], "criterion": criterion, "words": words, "basis": b, "mark": mark, "by": by,
            "at": now(), "undone": None, "tree": tree_of(chart_id)}
    if as_:
        item.update({"as": as_, "note": f"{'accepted' if as_ == 'accept' else 'added to the ask'} together with {together}" if together else None})
    _save(chart_id, items + [item])
    return item


def undo(chart_id: str, accept_id: str, by: Optional[str]) -> Optional[dict]:
    items = load(chart_id)
    x = next((i for i in items if i.get("id") == accept_id and not i.get("undone")), None)
    if x is None:
        return None
    x["undone"] = {"by": by, "at": now()}
    _save(chart_id, items)
    return x
