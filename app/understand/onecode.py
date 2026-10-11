"""One code, one pathway: a check is ONE procedure code under ONE indication of the guideline.

In the review flow (pipeline.run(pause_at_pathways=True)) an order whose procedure carries 2+ codes stops after
step B, before C, at the `pick_code` gate on the `order` stage (status `paused`, resume {stage: "guideline",
needs: "code", endpoint}). The gate's options are the codes, each with the guideline line that prints it and the
chart lines it was read from, found by code (no model call); C runs once, for the chosen code.

    gate(s, ...)            at the pause: pick_code.json {codes, suggested, picked: null, by: null, at: null}
    pick(chart_id, code)    a person picked: pick_code.json records who / when / which, answered_by on the order
                            stage, the case's override cpt = [code] (so re-checks keep it), then C onward with a
                            one-code order (pausing at the section gate as usual). An unpicked code (investigational,
                            not covered) is not part of this case and no longer stops it.
    split_prepare(...)      a NEW case from the same stored chart for another of the order's codes (copied spans,
                            sections and order; override cpt = [code]; same guideline); split.json in both cases
                            lists {from, to, code, by, at}
    case_code / focus       the case's one code, and {code, procedure_short, pathway_name, guideline_title}

The `/` flow and the CLI never pause here: an order with 2+ codes runs as it always did.
"""
from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from typing import Optional

from app.core import log, store
from app.core.models import Order, Span
from app.ingest.spans import expand, table

logger = log.get("onecode")
CHART_LINES = 3          # chart lines shown per code at the gate


def _token(code: str) -> re.Pattern:
    """The code as a word: not inside a longer number or word; a modifier after it ("36475-LT") is fine."""
    return re.compile(rf"(?<![0-9A-Za-z]){re.escape(code)}(?![0-9])")


def _path(chart_id: str, name: str):
    return store.RESULTS / chart_id / name


def load(chart_id: str, name: str = "pick_code.json"):
    p = _path(chart_id, name)
    return json.loads(p.read_text()) if p.exists() else None


def _save(chart_id: str, name: str, obj) -> None:
    p = _path(chart_id, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2))


# ---------------------------------------------------------------- the gate


def _chart_lines(code: str, order: Order, rspans: list[Span]) -> list[dict]:
    tok, rt = _token(code), table(rspans)
    ids = [i for i in expand(order.refs, rt) if i in rt and tok.search(rt[i].text)]
    if not ids:
        ids = [s.id for s in rspans if tok.search(s.text)]
    return [{"text": rt[i].text.strip(), "page": rt[i].page} for i in list(dict.fromkeys(ids))[:CHART_LINES]]


def _descriptor(code: str, gspans: list[Span]) -> Optional[str]:
    tok = _token(code)
    return next((s.text.strip() for s in gspans if tok.search(s.text)), None)


def _cached_tag(code: str, order: Order, gspans: list[Span], sha: str) -> Optional[str]:
    """A code-table tag only when step C is already cached for this guideline and this code (alone or with the
    order's codes); never a model call."""
    from app.checklist import keys
    for cpt in ([code], list(order.procedure.cpt)):
        try:
            n, _ = store.load_criteria(keys.cache_key(sha, order.procedure.model_copy(update={"cpt": cpt}), gspans))
        except Exception:
            n = None
        hit = next((c for c in (n.codes if n else []) if c.code == code), None)
        if hit is not None:
            return hit.tag
    return None


def _suggested(codes: list[str], order: Order, rspans: list[Span]) -> str:
    """The first code the order's procedure line names (as written, then the lines it was read from, by position),
    else the first in order.cpt."""
    rt = table(rspans)
    texts = [order.procedure.as_written or ""] + [rt[i].text for i in expand(order.refs, rt) if i in rt]
    for t in texts:
        hits = [(m.start(), c) for c in codes for m in [_token(c).search(t)] if m]
        if hits:
            return min(hits)[1]
    return codes[0]


def options(chart_id: str, gid: str, order: Order, rspans: list[Span]) -> list[dict]:
    codes = list(dict.fromkeys(order.procedure.cpt))
    try:
        gspans, sha, _ = store.load_guideline_spans(gid)
    except FileNotFoundError:
        gspans, sha = [], ""
    first = _suggested(codes, order, rspans)
    return [{"code": c, "descriptor": _descriptor(c, gspans), "chart_lines": _chart_lines(c, order, rspans),
             "tag": _cached_tag(c, order, gspans, sha) if gspans else None, "suggested": c == first} for c in codes]


def gate(s, chart_id: str, gid: str, order: Order, rspans: list[Span]) -> None:
    """Inside the order stage: raise the pick_code gate and write pick_code.json."""
    opts = options(chart_id, gid, order, rspans)
    codes = [o["code"] for o in opts]
    s.gate("pick_code", f"This order names {len(codes)} codes ({', '.join(codes)}). A check is one code: pick the "
           "code to check here; another code can be checked as its own case.", options=codes,
           action={"pick": {"endpoint": f"/api/review/{chart_id}/code"},
                   "split": {"endpoint": f"/api/review/{chart_id}/split"}})
    s.rec["gate"]["codes"] = opts
    _save(chart_id, "pick_code.json", {"chart_id": chart_id, "guideline_id": gid, "codes": opts,
                                       "suggested": next(o["code"] for o in opts if o["suggested"]),
                                       "picked": None, "by": None, "at": None})


def waiting(st: Optional[dict]) -> bool:
    return bool(st and st.get("state") == "paused" and (st.get("resume") or {}).get("needs") == "code")


def order_codes(chart_id: str, seen: Optional[set] = None) -> list[str]:
    """Every code of the order this case came from: pick_code.json, else (a split case) its origin's, else the
    order's own."""
    pc = load(chart_id)
    if pc:
        return [o["code"] for o in pc["codes"]]
    seen = (seen or set()) | {chart_id}
    for x in load(chart_id, "split.json") or []:
        if x.get("to") == chart_id and x.get("from") not in seen:
            return order_codes(x["from"], seen)
    o = store.load_order(chart_id)
    return list(dict.fromkeys(o.procedure.cpt)) if o else []


# ---------------------------------------------------------------- a person picked


def pick(chart_id: str, code: str, by: Optional[str] = None):
    """Continue a check paused at pick_code with `code` (one of the order's codes): C onward, pausing at the
    section gate. Raises ValueError when not paused here or the code is not the order's."""
    from app import pipeline
    from app.core.status import Recorder, load_status

    doc = load_status(chart_id)
    if not waiting(doc):
        raise ValueError("this check is not waiting for a code")
    pc = load(chart_id) or {}
    codes = [o["code"] for o in pc.get("codes") or []]
    if code not in codes:
        raise ValueError(f"not a code in this order: {code}")
    order = store.load_order(chart_id)
    if order is None:
        raise ValueError("the order for this check is gone; run the check again")
    who = (by or "").strip() or None
    pc.update(picked=code, by=who, at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    _save(chart_id, "pick_code.json", pc)
    override = dict(doc.get("override") or {}, cpt=[code])      # kept on the case: re-checks stay on this code
    st = Recorder.from_doc(doc)
    st.doc["override"] = override
    st.answer("order", who, [code], [pc.get("suggested")] if pc.get("suggested") else [])
    order = pipeline.apply_override(order, override)
    store.save_order(order)
    st.doc["order"] = dict(st.doc.get("order") or {}, cpt=order.procedure.cpt)
    st.stage_rec("order")["summary"] = (pipeline._order_summary(order) + f" · code {code} picked by "
                                        f"{who or 'a person'} from {', '.join(codes)}")
    st.save()
    logger.info("chart %s: code %s picked by %s from %s", chart_id, code, who or "a person", ", ".join(codes))
    return pipeline.from_guideline(st, chart_id, doc["guideline_id"], override, order, store.load_chart_spans(chart_id),
                                   doc.get("run_id") or "", pause_at_pathways=True)


# ---------------------------------------------------------------- split into a new case


def split_prepare(chart_id: str, code: str, by: Optional[str] = None) -> dict:
    """A new case for `code` from this case's stored chart: copies the chart's spans and sections (A2's cache) and
    the order (before any pick), records split.json in both cases. Returns what main._start needs. Raises
    LookupError (no such chart) or ValueError (not one of the order's codes)."""
    from app.core.status import load_status

    st = load_status(chart_id) or {}
    meta = store.chart_meta(chart_id)
    order = store.load_order(chart_id)
    if not meta or order is None or not st.get("guideline_id"):
        raise LookupError("No case with this id")
    codes = order_codes(chart_id)
    if code not in codes:
        raise ValueError(f"not a code in this order: {code}")
    new = uuid.uuid4().hex[:10]
    rspans = store.load_chart_spans(chart_id)
    store.save_chart(new, meta.get("filename") or "chart.pdf", rspans, source=meta.get("source", "api"))
    sec = store.CHARTS / chart_id / "sections.json"
    if sec.exists():
        shutil.copyfile(sec, store.CHARTS / new / "sections.json")
    o2 = order.model_copy(deep=True, update={"id": new, "chart_id": new})
    o2.procedure.cpt = list(codes)
    store.save_order(o2)
    override = dict(st.get("override") or {}, cpt=[code])
    rec = {"from": chart_id, "to": new, "code": code, "by": (by or "").strip() or None,
           "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for cid in (chart_id, new):
        _save(cid, "split.json", (load(cid, "split.json") or []) + [rec])
    logger.info("chart %s split: %s -> %s for code %s", chart_id, chart_id, new, code)
    return {"chart_id": new, "gid": st["guideline_id"], "filename": meta.get("filename") or "chart.pdf",
            "source": meta.get("source", "api"), "override": override, "order": o2, "rspans": rspans}


# ---------------------------------------------------------------- what the page shows


def case_code(chart_id: str) -> Optional[str]:
    """The case's one code (None while the order still has several, or none)."""
    o = store.load_order(chart_id)
    cpt = list(dict.fromkeys(o.procedure.cpt)) if o else []
    return cpt[0] if len(cpt) == 1 else None


def procedure_short(order: Order, code: Optional[str], rspans: list[Span], n: int = 60) -> Optional[str]:
    """A short name for the procedure of this code: the chart line naming the code (the code and its dash set
    aside), else the procedure as written up to its first comma."""
    t = ""
    if code:
        lines = _chart_lines(code, order, rspans)
        if lines:
            t = re.sub(r"^[\s\-–—:·•]+|[\s\-–—:·•]+$", "", _token(code).sub("", lines[0]["text"], count=1))
            t = re.sub(r"\s+", " ", re.sub(r"^\s*(CPT|code)\b[\s:#]*", "", t, flags=re.I)).strip(" -–—:")
    if not t:
        t = (order.procedure.as_written or order.procedure.target or "").split(",")[0].strip()
    if len(t) > n:
        t = t[:n].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return t or None


def focus(chart_id: str, pathway_names: list[str], guideline_title: Optional[str]) -> Optional[dict]:
    """{code, procedure_short, pathway_name, guideline_title} once the case's code is known; pathway_name is None
    until the indication is confirmed."""
    code = case_code(chart_id)
    o = store.load_order(chart_id)
    if not code or o is None:
        return None
    try:
        rspans = store.load_chart_spans(chart_id)
    except FileNotFoundError:
        rspans = []
    return {"code": code, "procedure_short": procedure_short(o, code, rspans),
            "pathway_name": "; ".join(pathway_names) or None, "guideline_title": guideline_title}
