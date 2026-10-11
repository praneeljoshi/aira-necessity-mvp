"""Feedback a coordinator files on a case: a guideline line that should (or should not) be a requirement, logic
that reads wrong, a proposed wording, an evidence quote that is wrong or about something else (side "chart", the
quote's span ids, the requirement it was attached to). A strike (app/strikes.py) files a not_a_requirement item
with `strike` = the strike id and `code` = the strike's reason chip (strikes.REASONS); un-striking removes it. Every
item carries `code` (None unless a strike filed it; older items lack it and read as None).

    data/feedback/<chart_id>.jsonl                         every item, in order; a remove is {"op":"remove","id"}
    data/feedback/by-guideline/<sha16>/<pathway|none>.jsonl   {"id","chart_id","at"} per item (and the remove lines)

Append-only: nothing is rewritten, a removed item stays in the file under its tombstone and is filtered when read.
The index lets GET /api/feedback find every item filed against one guideline (and one of its sections) across
cases without reading every chart's file. `FEEDBACK` is a module constant so tests can point it at tmp_path.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from . import status, store
from .spans import expand, table

FEEDBACK = store.DATA / "feedback"

KINDS = ("should_be_requirement", "not_a_requirement", "logic_wrong", "edit",
         "wrong_evidence", "evidence_elsewhere",          # on an evidence quote: wrong / about something else
         "is_evidence")                                   # older pages filed this on a chart line; still accepted
SIDES = ("guideline", "chart")


def _root() -> Path:
    return Path(FEEDBACK)


def _chart_file(chart_id: str) -> Path:
    return _root() / f"{chart_id}.jsonl"


def _index_files(sha: Optional[str], pathways: list[str]) -> list[Path]:
    d = _root() / "by-guideline" / ((sha or "")[:16] or "none")
    return [d / f"{p}.jsonl" for p in (pathways or ["none"])]


def _append(p: Path, obj: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(obj) + "\n")


def _read(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for ln in p.read_text().splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
    return out


def _live(lines: list[dict]) -> list[dict]:
    """Items in file order with the removed ones gone."""
    gone = {x.get("id") for x in lines if x.get("op") == "remove"}
    return [x for x in lines if x.get("op") != "remove" and x.get("id") not in gone]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------- what the case tells us


def context_of(chart_id: str) -> dict:
    """guideline id and sha, the confirmed (else used) section, the H key and run id, from what the check stored."""
    from .review import confirmation

    st = status.load_status(chart_id) or {}
    conf = confirmation(chart_id) or {}
    rec: dict = {}
    try:
        rec = store.load_result(chart_id)
    except FileNotFoundError:
        pass
    result = rec.get("result") or {}
    gid = conf.get("guideline_id") or (rec.get("meta") or {}).get("guideline_id") or result.get("guideline_id") or st.get("guideline_id")
    sha = conf.get("guideline_sha")
    if not sha and gid:
        sha = next((g["sha256"] for g in store.list_guidelines() if g["id"] == gid), None)
    if conf.get("confirmed"):
        pathway = list(dict.fromkeys(p["pathway"] for p in conf["confirmed"]))
    else:
        pathway = list(result.get("pathway_used") or [])
    return {"guideline_id": gid, "guideline_sha": sha, "pathway": pathway, "h_key": conf.get("h_key"),
            "run_id": result.get("run_id") or conf.get("run_id") or st.get("run_id")}


def _expand_spans(chart_id: str, gid: Optional[str], spans: list[str]) -> list[str]:
    """Citations (ids or ranges) -> ids: g ids against the guideline's spans, r ids against the chart's."""
    gt: dict = {}
    rt: dict = {}
    if gid and store.guideline_exists(gid):
        gt = table(store.load_guideline_spans(gid)[0])
    try:
        rt = table(store.load_chart_spans(chart_id))
    except FileNotFoundError:
        pass
    out: list[str] = []
    for x in spans:
        x = str(x).strip()
        tbl = gt if x.startswith("g") else rt
        for i in (expand([x], tbl) if tbl else [x]):
            if i not in out:
                out.append(i)
    return out


# ---------------------------------------------------------------- the operations


def add(chart_id: str, kind: str, side: str, text: str, spans: list[str], requirements: Optional[list[str]] = None,
        proposal: Optional[str] = None, by: Optional[str] = None, extra: Optional[dict] = None) -> dict:
    """`extra`: fields filed with the item by code, not by the page (a strike's id: {"strike": id})."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind: {kind}")
    if side not in SIDES:
        raise ValueError(f"unknown side: {side}")
    if not spans:
        raise ValueError("pick at least one line")
    ctx = context_of(chart_id)
    item = {"id": uuid.uuid4().hex[:12], "chart_id": chart_id, "kind": kind, "side": side, "text": text or "",
            "proposal": proposal,
            "spans": _expand_spans(chart_id, ctx["guideline_id"], spans), "requirements": list(requirements or []),
            "guideline_id": ctx["guideline_id"], "guideline_sha": ctx["guideline_sha"], "pathway": ctx["pathway"],
            "h_key": ctx["h_key"], "run_id": ctx["run_id"], "by": by, "at": now(), "code": None, **(extra or {})}
    _append(_chart_file(chart_id), item)
    for p in _index_files(item["guideline_sha"], item["pathway"]):
        _append(p, {"id": item["id"], "chart_id": chart_id, "at": item["at"]})
    return item


def list_for(chart_id: str) -> list[dict]:
    return [{"code": None, **x} for x in _live(_read(_chart_file(chart_id)))]


def get(chart_id: str, fid: str) -> Optional[dict]:
    return next((x for x in list_for(chart_id) if x.get("id") == fid), None)


def remove(chart_id: str, fid: str) -> bool:
    item = get(chart_id, fid)
    if item is None:
        return False
    stone = {"op": "remove", "id": fid}
    _append(_chart_file(chart_id), stone)
    for p in _index_files(item.get("guideline_sha"), item.get("pathway") or []):
        _append(p, stone)
    return True


def _sha16_of(guideline: str) -> Optional[str]:
    """A guideline id or a sha prefix -> the 16-character sha the index is filed under."""
    for g in store.list_guidelines():
        if g["id"] == guideline or g["sha256"].startswith(guideline):
            return g["sha256"][:16]
    d = _root() / "by-guideline"
    if d.exists():
        for sub in d.iterdir():
            if sub.name.startswith(guideline):
                return sub.name
    return None


def search(guideline: Optional[str] = None, pathway: Optional[str] = None, chart_id: Optional[str] = None) -> list[dict]:
    """Items across cases. `guideline` is an id or a sha16; `pathway` narrows to one section; `chart_id` to one
    case (combined with the others when given)."""
    if chart_id and not guideline:
        items = list_for(chart_id)
        return [x for x in items if not pathway or pathway in (x.get("pathway") or [])]
    if not guideline:
        return []
    sha16 = _sha16_of(guideline)
    if not sha16:
        return []
    d = _root() / "by-guideline" / sha16
    files = [d / f"{pathway}.jsonl"] if pathway else (sorted(d.glob("*.jsonl")) if d.exists() else [])
    refs: list[dict] = []
    for p in files:
        for x in _live(_read(p)):
            if x not in refs:
                refs.append(x)
    by_chart: dict[str, dict[str, dict]] = {}
    out = []
    for ref in sorted(refs, key=lambda x: x.get("at") or ""):
        cid = ref.get("chart_id")
        if chart_id and cid != chart_id:
            continue
        if cid not in by_chart:
            by_chart[cid] = {x["id"]: x for x in list_for(cid)}
        item = by_chart[cid].get(ref.get("id"))
        if item and item not in out:
            out.append(item)
    return out
