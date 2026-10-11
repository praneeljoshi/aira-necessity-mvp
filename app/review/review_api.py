"""The coordinator review flow's API: /review pages, the indication gate, the side-by-side case, feedback.
Routes are added to app.main's FastAPI app via `app.include_router(router)`. See app/review/review.py and app/review/feedback.py.

    POST /api/review/charts                      upload; the check pauses at the section for the person to confirm
    GET  /api/review/{chart_id}                  one document for every state (review.review_doc)
    POST /api/review/{chart_id}/pathways         confirm the section(s); the check goes on (pipeline.resume)
    POST /api/review/{chart_id}/code             {code, by?}: at the pick_code gate (2+ codes), the one code this case
                                                 checks; C onward, pausing at the section (app/understand/onecode.py)
    POST /api/review/{chart_id}/split            {code, by?}: a new case from the same chart for another of the order's
                                                 codes (pauses at its section); returns {chart_id, from, code}
    POST /api/review/{chart_id}/retry            after a failure: resume from the confirmed section, else start over
    GET/POST /api/review/{chart_id}/feedback     feedback on the case; DELETE .../feedback/{fid}
    GET  /api/feedback?guideline=&pathway=&chart_id=   feedback across cases
    POST /api/review/{chart_id}/strikes          {criterion, code?, reason?, by?}: remove a requirement for this case
                                                 (a reason chip, a note, or both); K-L again
    DELETE /api/review/{chart_id}/strikes/{sid}  put it back (?by=); K-L again
    POST /api/review/{chart_id}/signoff          {by, version, gaps_checked}: sign off a ready case (409 when `version`, the document's,
                                                 no longer matches, or a sign-off already stands); DELETE withdraws it
    POST /api/review/{chart_id}/ask              {span_ids, by?}: the card for selected guideline lines (app/review/ask.py)
    POST /api/review/{chart_id}/additions        {span_ids, by?}: add the asked lines to this case's checklist; K-L again
    DELETE /api/review/{chart_id}/additions/{aid}  take it off (?by=); K-L again
    POST /api/review/{chart_id}/none             {by?}: at the gate, no section fits: "this guideline doesn't apply"
    POST /api/review/{chart_id}/recheck          {guideline_id, by?}: check the chart against another guideline (pauses)
    POST /api/review/{chart_id}/accepts          {criterion, by?}: accept the ruling and evidence for one requirement
    DELETE /api/review/{chart_id}/accepts/{aid}  undo it (?by=)
    GET  /experimental                           a tiny index of experimental pages: policy health per guideline on file
    GET  /experimental/health/{guideline_id}     the policy health page (static/health.html); not linked from /review or /
    GET  /review/health/{guideline_id}           redirects to /experimental/health/{guideline_id}
    GET  /api/health/{guideline_id}              what every case on the guideline says about it (app/review/health.py; read-only)

This module must not import app.main at module level (main imports it); `from . import main` inside functions.
"""
from __future__ import annotations

import re
import threading
import uuid
from urllib.parse import quote
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field

from app import pipeline
from app.checklist import admin
from app.core import log, status, store
from app.review import accepts, additions, ask, feedback, health, review, signoff, strikes, tree
from app.understand import onecode

ROOT = Path(__file__).resolve().parents[2]
CHART_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")     # what a chart id can be (uuid hex, cut to 10 on upload)
NAME_MAX = 60                                        # characters of a person's name kept on a record


def _valid_id(request: Request) -> None:
    """Every /api route that names a chart: an id that cannot be one (a path, a space, 300 characters) is "no such
    chart" (404), never a 500 from the file system. The page routes serve the page, which says so in words."""
    cid = request.path_params.get("chart_id")
    if cid is not None and request.url.path.startswith("/api/") and not CHART_ID.match(cid):
        raise HTTPException(404, "No case with this id")


def _name(by: Optional[str]) -> Optional[str]:
    """A person's name as records keep it: trimmed, at most NAME_MAX characters, None when empty."""
    return (by or "").strip()[:NAME_MAX] or None


router = APIRouter(dependencies=[Depends(_valid_id)])
logger = log.get("review")
_case_lock = threading.Lock()           # strikes and sign-offs on a case change files together; one at a time


def _versioned(name: str) -> HTMLResponse:
    html = (ROOT / "static" / name).read_text()

    def ver(m):
        f = ROOT / m.group(1).lstrip("/")
        return f'{m.group(1)}?v={int(f.stat().st_mtime)}' if f.exists() else m.group(1)
    html = re.sub(r'(/static/(?:review[\w./-]*|health[\w.-]*|theme)\.(?:js|css))', ver, html)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})


@router.get("/experimental/health/{guideline_id}")
def health_page(guideline_id: str):
    """The policy health page for one guideline (static/health.html), versioned and no-cache like /review. Experimental:
    nothing in /review or / links here; /experimental lists it."""
    return _versioned("health.html")


@router.get("/review/health/{guideline_id}")
def health_page_moved(guideline_id: str):
    """The old address of the policy health page."""
    return RedirectResponse(f"/experimental/health/{quote(guideline_id, safe='')}", status_code=307)


@router.get("/experimental")
def experimental_index():
    """A tiny index of the experimental pages: policy health for each guideline on file (by its own title and number)."""
    from html import escape
    rows = []
    for g in store.list_guidelines():
        name = g.get("title_text") or g["id"]
        kicker = " · ".join(x for x in (g.get("issuer") or g.get("payer") or "", g.get("number") or "") if x)
        rows.append(f'<li><a href="/experimental/health/{quote(g["id"], safe="")}">{escape(name)}</a>'
                    + (f'<span>{escape(kicker)}</span>' if kicker else "") + "</li>")
    body = f"<ul>{''.join(rows)}</ul>" if rows else "<p>No guidelines on file.</p>"
    html = f"""<!doctype html><html lang="en" data-style="plain" data-theme="soft"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Experimental</title>
<link rel="stylesheet" href="/static/theme.css"><script>try{{const t=localStorage.getItem('review.theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>body{{margin:0;padding:32px 16px;background:var(--bg);color:var(--ink);font:15px/1.5 var(--f-ui)}}main{{max-width:640px;margin:0 auto}}
h1{{font-size:22px;font-weight:600;margin:0 0 4px}}p{{color:var(--sec);margin:0 0 20px}}ul{{list-style:none;padding:0;margin:0}}li{{padding:10px 0;border-top:1px solid var(--line)}}
a{{color:var(--act)}}li span{{display:block;font-size:13px;color:var(--sec)}}</style></head>
<body><main><h1>Experimental</h1><p>Policy health for each guideline on file. Not part of the review.</p>{body}</main></body></html>"""
    return HTMLResponse(html, headers={"Cache-Control": "no-cache, must-revalidate"})


@router.get("/api/health/{guideline_id}")
def health_doc(guideline_id: str):
    """Aggregated across every case on the guideline (app/review/health.py). Reads only; 404 for a guideline not on file."""
    d = health.build(guideline_id)
    if d is None:
        raise HTTPException(404, "no such guideline")
    return d


@router.get("/review")
@router.get("/review/{chart_id}")
def review_page(chart_id: str = ""):
    """review.html with every /static/review* URL (and the shared /static/theme.css) versioned by the file's
    modification time (?v=…), served no-cache with its files (main.log_requests), so a browser never pairs a cached
    page with newer scripts."""
    return _versioned("review.html")


# ---------------------------------------------------------------- the check, paused at the section


def _doc_or_404(chart_id: str) -> dict:
    d = review.review_doc(chart_id)
    if d is None:
        raise HTTPException(404, "No case with this id")
    return d


@router.post("/api/review/charts")
def upload_chart(file: UploadFile = File(...), guideline_id: Optional[str] = Form(None),
                 guideline: Optional[UploadFile] = File(None)):
    """Same as POST /api/charts, but the check stops at the section stage for the coordinator to confirm."""
    from app import main

    if not guideline_id and not (guideline and guideline.filename):
        raise HTTPException(400, "Pick a guideline on file (guideline_id) or upload one (guideline).")
    if guideline and guideline.filename:
        gtext, gsha = main._read_pdf(guideline)
        guideline_id = pipeline.add_guideline(gtext, guideline.filename, gsha)
    elif not store.guideline_exists(guideline_id):
        raise HTTPException(404, "no such guideline")
    text, _ = main._read_pdf(file)
    chart_id = uuid.uuid4().hex[:10]
    out = main._start(chart_id, text, guideline_id, file.filename or "chart.pdf", pause_at_pathways=True)
    return out if main.BACKGROUND else _doc_or_404(chart_id)


@router.get("/api/review/{chart_id}")
def get_review(chart_id: str):
    return _doc_or_404(chart_id)


class Picks(BaseModel):
    picks: list[dict] = Field(default_factory=list)
    by: Optional[str] = None


def _resume(chart_id: str, picks: list[dict], by: Optional[str]) -> dict:
    """pipeline.resume in a thread (or inline); the status record is marked failed when it raises outside a stage,
    so nothing fails silently. Same pattern as main._start."""
    from app import main

    def go(reraise: bool = False):
        try:
            pipeline.resume(chart_id, picks, by=by)
        except Exception as e:
            logger.exception("resume of chart %s failed", chart_id)
            st = status.load_status(chart_id)
            if st and st.get("state") != "failed":           # raised outside any stage
                st.update(state="failed", error=f"{type(e).__name__}: {e}", ended_at=status.now(), current=None)
                status.save_status(chart_id, st)
            if reraise:
                raise

    if main.BACKGROUND:
        main.run_tracked(chart_id, go, f"resume-{chart_id}")
        return {"chart_id": chart_id, "pending": True, "status": status.load_status(chart_id)}
    try:
        main.run_tracked(chart_id, lambda: go(reraise=True), f"resume-{chart_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"check failed: {e}")
    return _doc_or_404(chart_id)


@router.post("/api/review/{chart_id}/pathways")
def confirm_pathways(chart_id: str, body: Picks):
    st = status.load_status(chart_id)
    if not st:
        raise HTTPException(404, "No case with this id")
    if st.get("state") != "paused" or onecode.waiting(st):
        raise HTTPException(409, "this check is not waiting for a section")
    bad = review.check_picks(chart_id, body.picks)
    if bad:
        raise HTTPException(400, bad)
    return _resume(chart_id, body.picks, _name(body.by))


class CodeIn(BaseModel):
    code: str
    by: Optional[str] = None


def _in_background(chart_id: str, work, name: str) -> dict:
    """`work()` in a thread (or inline), marked failed when it raises outside a stage; the _resume pattern."""
    from app import main

    def go(reraise: bool = False):
        try:
            work()
        except Exception as e:
            logger.exception("%s of chart %s failed", name, chart_id)
            st = status.load_status(chart_id)
            if st and st.get("state") != "failed":
                st.update(state="failed", error=f"{type(e).__name__}: {e}", ended_at=status.now(), current=None)
                status.save_status(chart_id, st)
            if reraise:
                raise

    if main.BACKGROUND:
        main.run_tracked(chart_id, go, f"{name}-{chart_id}")
        return {"chart_id": chart_id, "pending": True, "status": status.load_status(chart_id)}
    try:
        main.run_tracked(chart_id, lambda: go(reraise=True), f"{name}-{chart_id}")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"check failed: {e}")
    return _doc_or_404(chart_id)


@router.post("/api/review/{chart_id}/code")
def pick_code(chart_id: str, body: CodeIn):
    """One code, one pathway: the code this case checks, at the pick_code gate."""
    st = status.load_status(chart_id)
    if not st:
        raise HTTPException(404, "No case with this id")
    if not onecode.waiting(st):
        raise HTTPException(409, "this check is not waiting for a code")
    code = (body.code or "").strip()
    if code not in onecode.order_codes(chart_id):
        raise HTTPException(400, f"not a code in this order: {code}")
    who = _name(body.by)
    return _in_background(chart_id, lambda: onecode.pick(chart_id, code, who), "pick")


@router.post("/api/review/{chart_id}/split")
def split_case(chart_id: str, body: CodeIn):
    """A new case from the same chart for one more of the order's codes; it starts at once and pauses at its section."""
    from app import main

    code = (body.code or "").strip()
    try:
        x = onecode.split_prepare(chart_id, code, _name(body.by))
    except LookupError:
        raise HTTPException(404, "No case with this id")
    except ValueError as e:
        raise HTTPException(400, str(e))
    main._start(x["chart_id"], "", x["gid"], x["filename"], source=x["source"], override=x["override"],
                order=x["order"], rspans=x["rspans"], pause_at_pathways=True)
    return {"chart_id": x["chart_id"], "from": chart_id, "code": code}


@router.post("/api/review/{chart_id}/retry")
def retry(chart_id: str):
    """Run again after a failure: from the confirmed section when one was confirmed, else from the start, pausing
    at the section as POST /api/review/charts does."""
    from app import main

    st = status.load_status(chart_id)
    meta_c = store.chart_meta(chart_id)
    if not st or not meta_c:
        raise HTTPException(404, "No case with this id")
    if main.still_running(st):
        raise HTTPException(409, "this check is still running")
    if st.get("state") == "paused":
        raise HTTPException(409, "stopped at a gate; confirm the indication first")
    conf = review.confirmation(chart_id)
    if conf and st.get("state") == "failed" and conf.get("confirmed"):
        return _resume(chart_id, [{"code": p["code"], "pathway": p["pathway"]} for p in conf["confirmed"]], conf.get("by"))
    out = main._start(chart_id, "", st["guideline_id"], meta_c.get("filename") or "chart.pdf", source=meta_c.get("source", "api"),
                      override=st.get("override"), order=store.load_order(chart_id), rspans=store.load_chart_spans(chart_id),
                      pause_at_pathways=True)
    return out if main.BACKGROUND else _doc_or_404(chart_id)


# ---------------------------------------------------------------- feedback


class FeedbackIn(BaseModel):
    kind: str
    side: str = "guideline"
    text: str = ""
    spans: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    proposal: Optional[str] = None
    by: Optional[str] = None


@router.get("/api/review/{chart_id}/feedback")
def list_feedback(chart_id: str):
    if not review.chart_exists(chart_id):
        raise HTTPException(404, "No case with this id")
    return feedback.list_for(chart_id)


@router.post("/api/review/{chart_id}/feedback", status_code=201)
def add_feedback(chart_id: str, body: FeedbackIn):
    if not review.chart_exists(chart_id):
        raise HTTPException(404, "No case with this id")
    try:
        return feedback.add(chart_id, body.kind, body.side, body.text, body.spans, body.requirements, body.proposal, body.by)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/api/review/{chart_id}/feedback/{fid}")
def remove_feedback(chart_id: str, fid: str):
    if not feedback.remove(chart_id, fid):
        raise HTTPException(404, "no such feedback")
    return {"ok": True}


@router.get("/api/feedback")
def search_feedback(guideline: Optional[str] = None, pathway: Optional[str] = None, chart_id: Optional[str] = None):
    if not guideline and not chart_id:
        raise HTTPException(400, "give guideline (an id or a sha) or chart_id")
    return feedback.search(guideline, pathway, chart_id)


# ---------------------------------------------------------------- strikes: a requirement removed for this case


def _finished(chart_id: str) -> None:
    """404 for an unknown id, 409 unless the check is finished (not running, paused or failed)."""
    st = status.load_status(chart_id)
    has = (store.RESULTS / chart_id / "result.json").exists()
    if st is None and not has:
        raise HTTPException(404, "No case with this id")
    if review._state(st, has) != "done":
        raise HTTPException(409, "this check is not finished")


class StrikeIn(BaseModel):
    criterion: str
    code: Optional[str] = None          # the reason chip (strikes.REASONS); older pages send a reason only
    reason: str = ""                    # the note: always optional
    by: Optional[str] = None


@router.post("/api/review/{chart_id}/strikes", status_code=201)
def add_strike(chart_id: str, body: StrikeIn):
    """Remove one requirement from this case only (app/review/strikes.py): no reason needed, the cached criteria are
    not touched, the sign-off (if any) is withdrawn and K-L run again. Answers the review document."""
    _finished(chart_id)
    note = (body.reason or "").strip()
    code = (body.code or "").strip() or None
    if code is not None and code not in strikes.LABELS:
        raise HTTPException(400, "unknown reason: " + code)
    with _case_lock:
        rec = store.load_result(chart_id)
        used = list(rec["result"].get("pathway_used") or [])
        gid = (rec.get("meta") or {}).get("guideline_id") or rec["result"].get("guideline_id")
        gspans, sha, _ = store.load_guideline_spans(gid)
        _, cs = review._criteria_for_case(sha, store.load_order(chart_id), review.confirmation(chart_id), chart_id)
        bad = strikes.check(chart_id, body.criterion, admin.applied(chart_id, cs, used), gspans, used)
        if bad:
            raise HTTPException(409 if "already" in bad else 400, bad)
        # the human is the judge: any requirement can be dropped with no reason, a gap too; never silent: who and
        # when are kept, and the sign-off and the audit note say a requirement the chart did not document was removed
        was = next((x["mark"] for x in review.case_view(chart_id)["requirements"] if x["criterion"] == body.criterion), None)
        by = _name(body.by)
        strikes.add(chart_id, body.criterion, note or (strikes.LABELS[code] if code else ""), by, cs, gspans, was=was, code=code)
        signoff.withdraw(chart_id, by, "strike")
        strikes.redecide(chart_id, by, "strike")
    return _doc_or_404(chart_id)


@router.delete("/api/review/{chart_id}/strikes/{strike_id}")
def remove_strike(chart_id: str, strike_id: str, by: Optional[str] = None):
    _finished(chart_id)
    with _case_lock:
        if strikes.undo(chart_id, strike_id, by) is None:
            raise HTTPException(404, "no such removal on this case")
        signoff.withdraw(chart_id, by, "un-strike")
        strikes.redecide(chart_id, by, "un-strike")
    return _doc_or_404(chart_id)


# ---------------------------------------------------------------- admin leaves: "Ask it anyway" (app/checklist/admin.py)


class UnpruneIn(BaseModel):
    criterion: str
    by: Optional[str] = None


@router.post("/api/review/{chart_id}/unprune", status_code=201)
def unprune(chart_id: str, body: UnpruneIn):
    """Restore one admin leaf this case set aside: it re-enters the logic and the requirements with the verdict of one
    judge call for it (none if that call fails: it reads as not in the chart yet), the sign-off (if any) is
    withdrawn and K-L run again. 400 when the requirement is not set aside on this case. Answers the review document."""
    _finished(chart_id)
    by = _name(body.by)
    with _case_lock:
        rec = store.load_result(chart_id)
        used = list(rec["result"].get("pathway_used") or [])
        gid = (rec.get("meta") or {}).get("guideline_id") or rec["result"].get("guideline_id")
        gspans, sha, _ = store.load_guideline_spans(gid)
        _, cs = review._criteria_for_case(sha, store.load_order(chart_id), review.confirmation(chart_id), chart_id)
        if cs is None or body.criterion not in admin.split(chart_id, cs, used)[1]:
            raise HTTPException(400, "this requirement is not set aside on this case")
        admin.unprune(chart_id, body.criterion, by, cs, gspans, rec["result"].get("run_id"))
        signoff.withdraw(chart_id, by, "asked anyway")
        strikes.redecide(chart_id, by, "asked anyway")
    return _doc_or_404(chart_id)


@router.delete("/api/review/{chart_id}/unprune/{criterion}")
def reprune(chart_id: str, criterion: str, by: Optional[str] = None):
    _finished(chart_id)
    with _case_lock:
        if admin.reprune(chart_id, criterion, by) is None:
            raise HTTPException(404, "this requirement was not restored on this case")
        signoff.withdraw(chart_id, by, "set aside again")
        strikes.redecide(chart_id, by, "set aside again")
    return _doc_or_404(chart_id)


# ---------------------------------------------------------------- sign-off before Ready


class SignIn(BaseModel):
    by: Optional[str] = None


class SignOffIn(BaseModel):
    by: Optional[str] = None
    version: Optional[str] = None       # the case document's `version` the signer's page was drawn from
    gaps_checked: bool = False          # "I've checked the removed requirements": needed when any was not in the chart


@router.post("/api/review/{chart_id}/signoff", status_code=201)
def sign_off(chart_id: str, body: SignOffIn):
    """A person signs off a ready case (app/review/signoff.py); until then it is "Ready for sign-off". 400 without a name,
    409 when the case is not ready (nothing short of ready is ever signed off as Ready) or not finished, when the
    case is no longer the version the page sent (another tab changed it), or when a sign-off already stands."""
    _finished(chart_id)
    with _case_lock:
        try:
            signoff.sign(chart_id, body.by, version=body.version, gaps_checked=body.gaps_checked)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except (LookupError, PermissionError, signoff.Conflict) as e:
            raise HTTPException(409, str(e))
    return _doc_or_404(chart_id)


@router.delete("/api/review/{chart_id}/signoff")
def withdraw_sign_off(chart_id: str, by: Optional[str] = None):
    _finished(chart_id)
    with _case_lock:
        if signoff.withdraw(chart_id, by) is None:
            raise HTTPException(404, "this case is not signed off")
    return _doc_or_404(chart_id)


# ---------------------------------------------------------------- highlight to ask, and adding to this case's checklist


class AskIn(BaseModel):
    span_ids: list[str] = Field(default_factory=list)
    by: Optional[str] = None


@router.post("/api/review/{chart_id}/ask")
def ask_lines(chart_id: str, body: AskIn):
    """The card for the selected guideline lines: free when they are already requirements of this case (the stored
    verdicts), or asked earlier (cached); otherwise one focused judge call. Not under the case lock: the model call
    may take seconds and changes nothing the case is decided from."""
    _finished(chart_id)
    try:
        return ask.ask(chart_id, body.span_ids, (body.by or "").strip() or None)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/api/review/{chart_id}/additions", status_code=201)
def add_lines(chart_id: str, body: AskIn):
    """Add the asked lines to this case's checklist (app/review/additions.py): one more AND term, judged by the ask; the
    sign-off (if any) is withdrawn and K-L run again. 409 until the lines were asked about, or when they are
    already on the checklist; 400 when a chart cannot show them. Answers the review document."""
    _finished(chart_id)
    by = _name(body.by)
    with _case_lock:
        try:
            raw, words, cs = ask.answer_to_add(chart_id, body.span_ids)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except LookupError as e:
            raise HTTPException(409, str(e))
        except PermissionError as e:
            raise HTTPException(400 if "cannot" in str(e) else 409, str(e))
        additions.add(chart_id, raw, words, by, cs)
        signoff.withdraw(chart_id, by, "addition")
        strikes.redecide(chart_id, by, "addition")
    return _doc_or_404(chart_id)


@router.delete("/api/review/{chart_id}/additions/{addition_id}")
def remove_lines(chart_id: str, addition_id: str, by: Optional[str] = None):
    _finished(chart_id)
    with _case_lock:
        if additions.undo(chart_id, addition_id, by) is None:
            raise HTTPException(404, "no such addition on this case")
        signoff.withdraw(chart_id, by, "addition taken off")
        strikes.redecide(chart_id, by, "addition taken off")
    return _doc_or_404(chart_id)


# ---------------------------------------------------------------- accept: a person approves a requirement's ruling and evidence


class AcceptIn(BaseModel):
    criterion: str
    by: Optional[str] = None
    together: list[str] = []        # identical requirements decided with it (review.merge_groups), whatever their evidence
    ask: bool = False               # together only: add them all to the ask instead of accepting them


@router.post("/api/review/{chart_id}/accepts", status_code=201)
def accept(chart_id: str, body: AcceptIn):
    """Lock one requirement in (app/review/accepts.py): a documented one is accepted (proof, it goes into the packet); one
    the chart does not document yet or contradicts is added to the ask (the message to the surgeon) instead. 400 for
    a requirement this case is not built from or one struck, 409 when it is already in. No K-L: this changes what a
    person approved, not the decision."""
    _finished(chart_id)
    by = _name(body.by)
    if not by:
        raise HTTPException(400, "say who is accepting (a name)")
    with _case_lock:
        reqs = {x["criterion"]: x for x in review.case_view(chart_id)["requirements"]}
        x = reqs.get(body.criterion)
        if x is None or not x["counted"]:
            raise HTTPException(400, "not a requirement this case is built from")
        if x["mark"] == "struck":
            raise HTTPException(400, "this requirement is removed for this case")
        if x["accepted"] or x["in_ask"]:
            raise HTTPException(409, "this requirement is already accepted" if x["accepted"] else "this requirement is already in the ask")
        if body.together:           # one decision for the whole identical group, no splitting by evidence
            for cid in body.together:
                y = reqs.get(cid)
                if y is None or not y["counted"] or y["mark"] == "struck" or cid not in (x.get("same") or []):
                    raise HTTPException(400, "not a requirement decided together with this one")
            how = "ask" if body.ask else "accept"
            for y in [x] + [reqs[c] for c in body.together if not (reqs[c]["accepted"] or reqs[c]["in_ask"])]:
                accepts.add(chart_id, y["criterion"], y["words"], y["basis"], y["mark"], by, how, None if y is x else x["criterion"])
        else:
            accepts.add(chart_id, body.criterion, x["words"], x["basis"], x["mark"], by)
    return _doc_or_404(chart_id)


@router.delete("/api/review/{chart_id}/accepts/{accept_id}")
def unaccept(chart_id: str, accept_id: str, by: Optional[str] = None):
    _finished(chart_id)
    with _case_lock:
        if accepts.undo(chart_id, accept_id, by) is None:
            raise HTTPException(404, "no such accept on this case")
        signoff.withdraw(chart_id, by, "accept undone")
    return _doc_or_404(chart_id)


# ---------------------------------------------------------------- at the gate: no section fits; another guideline


@router.post("/api/review/{chart_id}/none")
def none_fits(chart_id: str, body: SignIn):
    st = status.load_status(chart_id)
    if not st:
        raise HTTPException(404, "No case with this id")
    if st.get("state") != "paused":
        raise HTTPException(409, "this check is not waiting for a section")
    try:
        pipeline.no_section(chart_id, body.by)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _doc_or_404(chart_id)


class RecheckIn(BaseModel):
    guideline_id: str
    by: Optional[str] = None


@router.post("/api/review/{chart_id}/recheck")
def recheck_other(chart_id: str, body: RecheckIn):
    """Check the same chart against another guideline on file; the check pauses at that guideline's sections."""
    from app import main

    st = status.load_status(chart_id)
    meta_c = store.chart_meta(chart_id)
    if not st or not meta_c:
        raise HTTPException(404, "No case with this id")
    if main.still_running(st):
        raise HTTPException(409, "this check is still running")
    if not store.guideline_exists(body.guideline_id):
        raise HTTPException(404, "no such guideline")
    out = main._start(chart_id, "", body.guideline_id, meta_c.get("filename") or "chart.pdf", source=meta_c.get("source", "api"),
                      override=st.get("override"), order=store.load_order(chart_id), rspans=store.load_chart_spans(chart_id),
                      pause_at_pathways=True)
    return out if main.BACKGROUND else _doc_or_404(chart_id)
