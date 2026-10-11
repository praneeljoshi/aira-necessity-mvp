"""The API behind static/index.html. See the page's header comment for the contract."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import pipeline
from app.checklist import keys
from app.core import log, status, store
from app.review import review, review_api, signoff, tree
from app.understand import onecode
from app.core.models import CriteriaSet, Narrowed, Order, Result, Selection
from app.ingest.pdf import EmptyPdfText, pdf_to_text
from app.understand.select import pathway_name
from app.ingest.spans import table, text_of
from app.decide.templates import fmt_date

ROOT = Path(__file__).resolve().parents[1]
@asynccontextmanager
async def _lifespan(_app):
    _interrupted_on_restart()
    yield


app = FastAPI(title="necessity", version="1.1", lifespan=_lifespan)
logger = log.get("api")
BACKGROUND = True        # checks run in a thread after upload and the page polls; tests set False to run inline
LIVE: dict[str, threading.Thread] = {}   # chart_id -> the worker running its check or resume in this process
_LIVE_LOCK = threading.Lock()


def run_tracked(chart_id: str, go, name: str) -> None:
    """Runs `go` for `chart_id` in a worker (or inline when BACKGROUND is off), listed in LIVE from before it starts
    until it ends, so a restart sweep and retry can tell a check being worked on from one cut off."""
    def body():
        try:
            go()
        finally:
            with _LIVE_LOCK:
                if LIVE.get(chart_id) is t:
                    LIVE.pop(chart_id, None)

    t = threading.Thread(target=body, name=name, daemon=True) if BACKGROUND else threading.current_thread()
    with _LIVE_LOCK:
        LIVE[chart_id] = t
    if BACKGROUND:
        t.start()
    else:
        body()


def is_live(chart_id: str) -> bool:
    with _LIVE_LOCK:
        t = LIVE.get(chart_id)
    return bool(t and t.is_alive())


def still_running(st: dict) -> bool:
    """True when a "running" check is really being worked on (here or by another process); one that is not was cut
    off by a restart and is marked failed now, so retry can run it again."""
    if st.get("state") != "running":
        return False
    if is_live(st["chart_id"]) or status.held_elsewhere(st):
        return True
    st.update(status.mark_interrupted(st["chart_id"], st) or {})
    return False


def _interrupted_on_restart() -> None:
    """At startup: a check left running by the previous server is failed with a plain message (retry runs it)."""
    marked = status.sweep_interrupted(is_live)
    if marked:
        logger.info("marked %d check(s) cut off by the restart: %s", len(marked), ", ".join(marked))


@app.middleware("http")
async def log_requests(request: Request, call_next):
    t0 = time.time()
    response = await call_next(request)
    path = request.url.path
    if path.startswith(("/static/review", "/review", "/static/theme", "/static/health")):   # the review page and the shared theme: never a stale mix of files
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    if path.startswith("/api") and path != "/api/health":
        logger.info("%s %s -> %d in %.1fs", request.method, path, response.status_code, time.time() - t0)
    return response


def _read_pdf(up: UploadFile) -> tuple[str, str]:
    if not (up.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF.")
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        data = up.file.read()
        f.write(data)
        path = Path(f.name)
    try:
        return pdf_to_text(path), hashlib.sha256(data).hexdigest()
    except EmptyPdfText as e:
        raise HTTPException(422, str(e))
    finally:
        path.unlink(missing_ok=True)


def _gl_row(gid: str) -> dict:
    row = next((g for g in store.list_guidelines() if g["id"] == gid), {"id": gid})
    return {"id": gid, "payer": row.get("payer") or "", "title": row.get("filename") or gid, "guideline_number": None}


def _decided(chart_id: str, r: Result, sel: Selection, gid: str) -> dict:
    """What "How this was decided" shows: codes with tags, the section chosen and why, sentences set aside."""
    o = store.load_order(chart_id)
    try:
        gspans, sha, _ = store.load_guideline_spans(gid)
    except FileNotFoundError:
        return {}
    gt = table(gspans)
    n: Optional[Narrowed] = None
    cs: Optional[CriteriaSet] = None
    if o:
        n, cs = store.load_criteria(keys.case_order_key(sha, o.procedure, chart_id))
    conf = store.load_confirmation(chart_id)
    if conf and conf.get("h_key"):
        cs = store.load_criteria(conf["h_key"])[1] or cs
    cs = store.load_case_criteria(chart_id) or cs   # the exact set this case was judged with (older cases: none)
    out: dict = {"codes": [], "sections": [], "set_aside": [], "run_id": r.run_id}
    if n:
        asked = set(o.procedure.cpt) | ({n.mapped_cpt.code} if n.mapped_cpt else set())
        out["codes"] = [{"code": c.code, "tag": c.tag, "description": c.description[:200], "ordered": c.code in asked}
                        for c in n.codes if c.code in asked] or []
        because = o.procedure.target or o.procedure.as_written or ""
        out["sections"] = [{"code": p.code, "name": pathway_name(n, p.pathway, gspans),
                            "because": because, "how": p.how} for p in sel.pathways]
        out["candidates"] = {c: [pathway_name(n, x, gspans) for x in ids] for c, ids in sel.candidates.items()}
    if cs:
        out["loopholes"] = cs.loopholes
    return out


def _pending(chart_id: str, st: dict) -> dict:
    """A check with no result yet: what the screen shows while it runs or after it stopped."""
    o = store.load_order(chart_id)
    order = {"patient_name": o.patient_name, "procedure_text": o.procedure.as_written, "cpt": o.procedure.cpt,
             "payer": o.payer, "target": o.procedure.target} if o else dict(st.get("order") or {})
    return {"chart_id": chart_id, "pending": True, "order": order, "key": order, "result": None, "ask": "", "packet": [],
            "surgeon": o.procedure.surgeon if o else None, "guideline": _gl_row(st.get("guideline_id") or ""),
            "status": st, "filename": st.get("filename")}


def _detail(chart_id: str) -> dict:
    st = status.load_status(chart_id)
    try:
        rec = store.load_result(chart_id)
    except FileNotFoundError:
        if st:
            return _pending(chart_id, st)
        raise HTTPException(404, "No case with this id")
    r = Result.model_validate(rec["result"])
    sel = Selection.model_validate(rec["selection"])
    verdicts = rec.get("verdicts") or {}
    gid = (rec.get("meta") or {}).get("guideline_id") or r.guideline_id
    o = store.load_order(chart_id)
    gl = _gl_row(gid)
    order = {"patient_name": o.patient_name, "procedure_text": o.procedure.as_written, "cpt": o.procedure.cpt,
             "payer": o.payer, "target": o.procedure.target} if o else {}
    rank = {"NOT_MET": 0, "INSUFFICIENT": 1, "MET": 2}
    labels = {"MET": "met", "INSUFFICIENT": "missing", "NOT_MET": "contradicted"}
    packet = [{"label": c.text, "status": labels[c.status], "missing": c.status == "INSUFFICIENT",
               "note": (verdicts.get(c.criterion) or {}).get("rationale", "") if c.status != "MET" else "",
               "quotes": [{"quote": q.text, "source": fmt_date(q.date)} for q in c.quotes]}
              for c in sorted(r.checklist, key=lambda c: rank[c.status])]
    result = json.loads(r.model_dump_json())
    result.update(needs_review=r.queue == "review", guideline_title=gl["title"], guideline_payer=gl["payer"])
    return {"chart_id": chart_id, "order": order, "key": order, "verification": None,
            "override": (rec.get("meta") or {}).get("override"), "guideline": gl, "result": result, "ask": r.ask,
            "packet": packet, "surgeon": o.procedure.surgeon if o else None, "decided": _decided(chart_id, r, sel, gid),
            "signoff": signoff.state_of(chart_id),
            "status": st}


def _start(chart_id: str, text: str, gid: str, filename: str, source: str = "api", override: Optional[dict] = None,
           order: Optional[Order] = None, rspans=None, pause_at_pathways: bool = False) -> dict:
    """Runs the check in a thread (or inline when BACKGROUND is off) and returns what the page needs right away:
    the chart id and the status to poll. The recorder owns status.json from this moment; a stage that raises is
    recorded as failed by the recorder itself, so nothing fails silently. `pause_at_pathways` is the review flow's
    stop at the section gate (app/review/review_api.py); the check then waits for pipeline.resume."""
    signoff.withdraw(chart_id, None, "re-check")   # a sign-off never outlives the check it was made on (a no-op if none)
    rec = status.Recorder(chart_id, gid, filename, override, source)

    def go():
        try:
            pipeline.run(text, chart_id, gid, override=override, filename=filename, source=source, order=order,
                         rspans=rspans, status=rec, pause_at_pathways=pause_at_pathways)
        except Exception:
            logger.exception("check of chart %s failed", chart_id)
            if rec.state != "failed":                     # raised outside any stage
                rec.doc.update(state="failed", error="check failed before it started", ended_at=status.now())
                rec.save()

    run_tracked(chart_id, go, f"check-{chart_id}")
    if BACKGROUND:
        return {"chart_id": chart_id, "pending": True, "status": rec.doc}
    if rec.state == "failed":
        raise HTTPException(500, f"check failed: {rec.doc.get('error')}")
    return _detail(chart_id)


@app.get("/")
def index():
    return FileResponse(ROOT / "static" / "index.html")


# Every patient has a path: /patients/<chart_id> is the screen with that patient selected (summary view),
# /patients/<chart_id>/tree the same screen with the main area in the guideline view (static/tree.js). The page
# reads the path; an unknown id shows "No chart with this id" in the main area, the rail stays.
# The old /#<id> and /tree/<id> redirect to these.
@app.get("/patients/{chart_id}")
@app.get("/patients/{chart_id}/tree")
def patient_page(chart_id: str):
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "has_key": bool(os.environ.get("OPENAI_API_KEY"))}


@app.get("/api/guidelines")
def list_guidelines():
    return [{"id": g["id"], "payer": g.get("payer") or "", "title": g.get("filename") or g["id"], "guideline_number": None,
             "n_pathways": g.get("n_pathways"), "n_codes": g.get("n_codes"),
             # the review page's names: the guideline's own title and number (app/review/titles.py), never the file name
             "name": g.get("title_text") or "", "number": g.get("number") or "", "issuer": g.get("issuer") or g.get("payer") or ""}
            for g in store.list_guidelines()]


@app.post("/api/guidelines")
def add_guideline(file: UploadFile = File(...)):
    text, sha = _read_pdf(file)
    cached = store.find_guideline_by_sha(sha) is not None
    gid = pipeline.add_guideline(text, file.filename or "guideline.pdf", sha)
    if pipeline.precompute_wanted():          # PRECOMPUTE_H=1: build every indication's checklist now, in the background
        threading.Thread(target=_precompute, args=(gid,), name=f"precompute-{gid}", daemon=True).start()
    return {"id": gid, "payer": "", "title": file.filename, "guideline_number": None, "cached": cached, "replaced": [],
            "precomputing": pipeline.precompute_wanted()}


def _precompute(gid: str) -> None:
    try:
        pipeline.precompute(gid)
    except Exception:
        logger.exception("precompute for guideline %s failed", gid)


@app.delete("/api/guidelines/{gid}")
def delete_guideline(gid: str):
    store.delete_guideline(gid)
    return {"ok": True}


@app.get("/api/orders")
def list_orders():
    rows = store.list_results()
    for x in rows:
        gl = _gl_row(x["guideline_id"]) if x.get("guideline_id") else {}
        x.update(guideline_title=gl.get("title"), guideline_payer=gl.get("payer"), guideline_number=None)
        st = status.load_status(x["chart_id"])
        x["status"] = status.summary_row(st) if st else None
        x["signoff"] = signoff.state_of(x["chart_id"])      # the review rail: ready for sign-off vs signed off
        x.update(review.lane(x["chart_id"]))                # the review rail: in the ask, and since when
        x["code"] = onecode.case_code(x["chart_id"])        # one code, one pathway: tells sibling cases apart
        if st and st["state"] == "running":            # a re-check in progress: the queue shows it as checking
            x["queue"] = "running"
        elif st and st["state"] == "paused":           # a re-check waiting for a person at the section gate
            x["queue"] = "paused"
    for st in status.list_pending():                   # no result yet: running, waiting at the section gate, or failed
        o = st.get("order") or {}
        gl = _gl_row(st["guideline_id"]) if st.get("guideline_id") else {}
        rows.insert(0, {"chart_id": st["chart_id"], "patient_name": o.get("patient_name"), "procedure_text": o.get("procedure_text"),
                        "cpt": o.get("cpt") or [], "payer": o.get("payer"), "determination": None,
                        "queue": {"failed": "failed", "paused": "paused"}.get(st["state"], "running"), "needs_review": False,
                        "run_id": st.get("run_id"), "created_at": st.get("started_at"), "guideline_id": st.get("guideline_id"),
                        "guideline_title": gl.get("title"), "guideline_payer": gl.get("payer"), "guideline_number": None,
                        "status": status.summary_row(st), "filename": st.get("filename"),
                        "code": onecode.case_code(st["chart_id"])})
    return rows


@app.get("/api/orders/{chart_id}/status")
def get_status(chart_id: str):
    st = status.load_status(chart_id)
    if not st:
        raise HTTPException(404, "no status for this case")
    return st


@app.get("/api/orders/{chart_id}/tree")
def get_tree(chart_id: str):
    d = _detail(chart_id)
    if d.get("pending"):
        return d
    d["tree"] = tree.build(chart_id)
    return d


@app.get("/tree/{chart_id}")
def tree_page(chart_id: str):
    return RedirectResponse(f"/patients/{chart_id}/tree", status_code=307)


@app.get("/api/orders/{chart_id}")
def get_order(chart_id: str):
    return _detail(chart_id)


@app.post("/api/charts")
def upload_chart(file: UploadFile = File(...), guideline_id: Optional[str] = Form(None),
                 guideline: Optional[UploadFile] = File(None)):
    if not guideline_id and not (guideline and guideline.filename):
        raise HTTPException(400, "Pick a guideline on file (guideline_id) or upload one (guideline).")
    if guideline and guideline.filename:
        gtext, gsha = _read_pdf(guideline)
        guideline_id = pipeline.add_guideline(gtext, guideline.filename, gsha)
    elif not store.guideline_exists(guideline_id):
        raise HTTPException(404, "no such guideline")
    text, _ = _read_pdf(file)
    chart_id = uuid.uuid4().hex[:10]
    return _start(chart_id, text, guideline_id, file.filename or "chart.pdf")


class Recheck(BaseModel):
    cpt: Optional[list[str]] = None
    target: Optional[str] = None
    plan: Optional[str] = None             # the member's plan as the coordinator corrects it (step H prunes plan-only conditions)
    guideline_id: Optional[str] = None
    payer: Optional[str] = None            # accepted from the screen; v1.1 does not route on payer


@app.post("/api/orders/{chart_id}/recheck")
def recheck_order(chart_id: str, body: Recheck):
    if body.guideline_id and not store.guideline_exists(body.guideline_id):
        raise HTTPException(404, "no such guideline")
    try:
        meta = store.load_result(chart_id).get("meta", {})
    except FileNotFoundError:
        st = status.load_status(chart_id)
        if not st:
            raise HTTPException(404, "No case with this id")
        meta = {"guideline_id": st.get("guideline_id"), "override": st.get("override")}
    merged = dict(meta.get("override") or {})
    merged.update({k: v for k, v in body.model_dump(exclude_none=True).items() if v not in (None, "", [])})
    gid = merged.get("guideline_id") or meta.get("guideline_id")
    meta_c = store.chart_meta(chart_id)
    if not meta_c:
        raise HTTPException(404, "No case with this id")
    return _start(chart_id, "", gid, meta_c.get("filename") or "chart.pdf", source=meta_c.get("source", "api"),
                  override=merged or None, order=store.load_order(chart_id), rspans=store.load_chart_spans(chart_id))


@app.post("/api/orders/{chart_id}/retry")
def retry_order(chart_id: str):
    """Run the check again after a failure, from the stored chart; the order is read again only if it never was."""
    st = status.load_status(chart_id)
    meta_c = store.chart_meta(chart_id)
    if not st or not meta_c:
        raise HTTPException(404, "No case with this id")
    if still_running(st):
        raise HTTPException(409, "this check is still running")
    if st["state"] == "paused":
        raise HTTPException(409, "stopped at a gate; confirm the indication first")
    return _start(chart_id, "", st["guideline_id"], meta_c.get("filename") or "chart.pdf", source=meta_c.get("source", "api"),
                  override=st.get("override"), order=store.load_order(chart_id), rspans=store.load_chart_spans(chart_id))


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    try:
        return store.load_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404, "no such run")


@app.get("/api/runs/{run_id}/{step}")
def get_run_step(run_id: str, step: str):
    try:
        d = store.load_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404, "no such run")
    if step not in d:
        raise HTTPException(404, "no such step in this run")
    return d[step]


app.include_router(review_api.router)
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")
