"""GET /api/review/{id} in every state, the gate document, the case document (quote positions, the chart's
evidence under each requirement), the pause/confirm endpoints. Offline: stub model, store in tmp_path, feedback in
tmp_path."""
from __future__ import annotations

import hashlib
import re

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline
from app.checklist import keys
from app.core import llm, status, store
from app.review import feedback, review
from app.understand.select import select
from app.ingest.spans import table
from tests.conftest import SAMPLES, sid
from tests.fake import Stub

FL_PDF = SAMPLES / "fl_varicose_veins_guideline.pdf"
DELGADO_PDF = SAMPLES / "synthetic" / "maria_delgado_chart.pdf"


@pytest.fixture
def world(tmp_store, tmp_path, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    monkeypatch.setattr(feedback, "FEEDBACK", tmp_path / "feedback")
    sha = hashlib.sha256(FL_PDF.read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    def check(chart_id, override=None, **kw):
        stub = Stub(fl_spans, delgado_spans, **kw)
        monkeypatch.setattr(llm, "call", stub)
        return pipeline.run("", chart_id, gid, rspans=delgado_spans, override=override), stub
    return check, TestClient(main.app), gid


def _needs_a():
    if not hasattr(pipeline, "resume"):
        pytest.skip("pipeline.resume not landed yet")
    import inspect
    if "pause_at_pathways" not in inspect.signature(main._start).parameters:
        pytest.skip("main._start(pause_at_pathways=) not landed yet")


# ---------------------------------------------------------------- states


def test_unknown_chart_is_404_and_pages_serve(world):
    _, c, _ = world
    r = c.get("/api/review/nope")
    assert r.status_code == 404 and r.json() == {"detail": "No case with this id"}
    assert c.get("/api/review/nope/feedback").status_code == 404
    assert c.get("/review").status_code == 200
    assert c.get("/review/nope").status_code == 200


def test_running_and_failed_states(world):
    _, c, gid = world
    rec = status.Recorder("run1", gid, "chart.pdf")
    d = c.get("/api/review/run1").json()
    assert d["state"] == "running" and d["gate"] is None and d["case"] is None and d["confirmation"] is None
    assert d["status"]["chart_id"] == "run1" and d["guideline"]["id"] == gid and d["guideline"]["title"] == "fl.pdf"
    assert d["feedback"] == [] and d["order"]["cpt"] == []
    rec.doc.update(state="failed", error="RuntimeError: boom", ended_at=status.now())
    rec.doc["stages"][1].update(status="failed", error="RuntimeError: boom")
    rec.save()
    d = c.get("/api/review/run1").json()
    assert d["state"] == "failed" and d["status"]["error"] == "RuntimeError: boom" and d["case"] is None


def test_done_state_case_doc(world, fl_spans, delgado_spans):
    check, c, gid = world
    r, _ = check("met")
    assert r.determination == "MET"
    d = c.get("/api/review/met").json()
    assert d["state"] == "done" and d["gate"] is None and d["confirmation"] is None
    assert d["order"]["patient_name"] == "Maria Elena Delgado" and d["order"]["cpt"] == ["36475"]
    assert d["guideline"] == {"id": gid, "title": "fl.pdf", "payer": "Florida Blue", "sha": hashlib.sha256(FL_PDF.read_bytes()).hexdigest(),
                              "name": "Treatments for Varicose Veins / Venous Insufficiency",
                              "number": "Medical Coverage Guideline 02-33000-31", "issuer": "Florida Blue"}
    case = d["case"]
    assert case["result"]["determination"] == "MET" and case["result"]["guideline_title"] == "fl.pdf"
    assert case["ask"].startswith("Nothing to ask") and case["packet"] and case["surgeon"].startswith("Dr. Elena")
    assert case["tree"]["sections"][0]["label"] == "Great or Small Saphenous Veins"
    assert case["h_key"] is None and case["confirmation"] is None
    # requirements: every judged criterion, in guideline order, with its tree block
    reqs = case["requirements"]
    ids = [x["criterion"] for x in reqs]
    assert set(ids) == {"reflux", "ceap", "size", "ulcer", "thromb", "hem", "symptoms", "adl", "compression"}
    assert ids.index("reflux") < ids.index("size") < ids.index("ulcer") < ids.index("symptoms")
    by = {x["criterion"]: x for x in reqs}
    assert by["reflux"]["mark"] == "documented" and by["reflux"]["say"] == "Documented" and not by["reflux"]["bad"]
    assert by["ulcer"]["mark"] == "not_needed" and by["ulcer"]["role"] == "requirement"
    assert all(x["block"] and x["block"].startswith("b") for x in reqs)
    # highlights: the quote's own characters inside the line, shifted by the line's indent
    gt = table(fl_spans)
    size = by["size"]
    assert size["refs"] == [sid(fl_spans, "The varicosities are at least 3 millimeters")]
    (h,) = size["highlights"]
    assert gt[h["id"]].text[h["start"]:h["end"]] == "The varicosities are at least 3 millimeters in size"
    # a quote that wraps over lines: a highlight on each line it touches, each inside that line's own text
    comp = by["compression"]
    assert len(comp["refs"]) > 1 and len(comp["highlights"]) >= 1
    joined = " ".join(gt[h["id"]].text[h["start"]:h["end"]] for h in comp["highlights"])
    assert re.sub(r"\s+", " ", joined) == comp["words"]
    for h in comp["highlights"]:
        t = gt[h["id"]].text
        assert 0 <= h["start"] < h["end"] <= len(t) and t[h["start"]] != " "
    # evidence: the judge's citations by side, expanded to chart lines, with the note heading and page
    ev = {e["side"] for e in by["reflux"]["evidence"]}
    assert ev == {"for"} and by["reflux"]["evidence"][0]["lines"] and by["reflux"]["evidence"][0]["date"] == "2025-03-25"
    assert by["ulcer"]["evidence"][0]["side"] == "against" and "No ulceration" in by["ulcer"]["evidence"][0]["text"]
    assert all("page" in e and "heading" in e for x in reqs for e in x["evidence"])
    rt = table(delgado_spans)
    no_ulcer = sid(delgado_spans, "No ulceration.")
    assert any(no_ulcer in e["lines"] and e["side"] == "against" for e in by["ulcer"]["evidence"])
    for x in reqs:
        for e in x["evidence"]:
            assert e["lines"] and all(i in rt for i in e["lines"]) and e["page"] == rt[e["lines"][0]].page
            assert e["heading"] and e["text"]
    # the chart itself is not sent: only its name and page count (the page shows the chart as evidence only)
    assert case["chart"] == {"filename": "chart.pdf", "pages": len({s.page for s in delgado_spans})}
    assert case["chart"]["pages"] >= 1


def test_done_state_for_a_stopped_code(world):
    check, c, _ = world
    r, _ = check("nc", override={"cpt": ["36468"], "target": "spider veins"})
    assert r.determination == "NOT_COVERED"
    d = c.get("/api/review/nc").json()
    assert d["state"] == "done" and d["case"]["tree"]["codes"][0]["code"] == "36468"
    assert d["case"]["requirements"] == []
    assert d["case"]["chart"]["filename"] == "chart.pdf" and isinstance(d["case"]["chart"]["pages"], int)
    assert d["case"]["chart"]["pages"] >= 1


# ---------------------------------------------------------------- the gate document (built from stored files)


def _pause_by_hand(check, chart_id, fl_spans, **kw):
    """A paused check written the way the pipeline writes it: selection.json + status paused with resume.key.
    Built from a finished check's cache so the gate view is tested on its own, whatever the pipeline does."""
    r, _ = check(chart_id, **kw)
    o = store.load_order(chart_id)
    gspans, sha, _ = store.load_guideline_spans(r.guideline_id)
    key = keys.cache_key(sha, o.procedure)
    n, _ = store.load_criteria(key)
    sel = select(n, o, gspans)
    (store.RESULTS / chart_id / "result.json").unlink()
    store._write(store.RESULTS / chart_id / "selection.json", sel.model_dump_json(indent=2))
    st = status.load_status(chart_id)
    st.update(state="paused", resume={"stage": "checklist", "needs": "pathways", "key": key,
                                      "endpoint": f"/api/review/{chart_id}/pathways"})
    status.save_status(chart_id, st)
    return sel, n


def test_gate_view(world, fl_spans, delgado_spans):
    check, c, _ = world
    sel, n = _pause_by_hand(check, "g1", fl_spans)
    d = c.get("/api/review/g1").json()
    assert d["state"] == "paused" and d["case"] is None
    g = d["gate"]
    assert g["none_chosen"] is False and g["suggested"] == [{"code": "36475", "pathway": "gsv"}]
    assert g["order"]["as_written"].startswith("Endovenous radiofrequency ablation") and g["order"]["cpt"] == ["36475"]
    assert g["order"]["target"] == "left great saphenous vein" and g["order"]["patient_name"] == "Maria Elena Delgado"
    ids = [ln["id"] for ln in g["order"]["lines"]]
    assert sid(delgado_spans, "ablation, left great saphenous vein") in ids and len(ids) >= 2
    assert all(set(ln) == {"id", "text", "page"} for ln in g["order"]["lines"])
    (code,) = g["codes"]
    assert code["code"] == "36475" and code["tag"] == "covered" and code["outcome"] == "judge" and code["mapped"] is False
    assert "36475" in code["lines"][0]["text"] and code["description"]
    assert g["stopped"] == []
    pw = {p["id"]: p for p in g["pathways"]}
    assert list(pw) == ["gsv", "accessory", "tributaries", "perforator"]
    gsv = pw["gsv"]
    assert gsv["name"] == "Great or Small Saphenous Veins" and gsv["suggested"] is True and "36475" in gsv["codes"]
    assert gsv["for_codes"] == ["36475"] and pw["accessory"]["for_codes"] == ["36475"] and pw["tributaries"]["for_codes"] == []
    assert pw["accessory"]["suggested"] is False
    assert len(gsv["lines"]) == 6 and gsv["lines"][0]["text"].strip().startswith("Great or Small Saphenous Veins")
    assert set(gsv["lines"][0]) == {"id", "text", "page", "blank_before"}
    assert gsv["n_lines"] > 6 and gsv["more"] == gsv["n_lines"] - 6 and gsv["pages"]
    assert gsv["targets"] == ["great saphenous vein", "small saphenous vein"]


def test_gate_view_when_none_chosen(world, fl_spans):
    check, c, _ = world
    _pause_by_hand(check, "g2", fl_spans, order={"target": None})
    g = c.get("/api/review/g2").json()["gate"]
    assert g["none_chosen"] is True and g["suggested"] == [] and not any(p["suggested"] for p in g["pathways"])
    assert g["order"]["target"] is None


def test_check_picks_rules(world, fl_spans):
    check, c, _ = world
    _pause_by_hand(check, "g3", fl_spans)
    assert review.check_picks("g3", []) == "pick at least one section"
    assert review.check_picks("g3", [{"code": "36475", "pathway": "gsv"}]) is None
    bad = review.check_picks("g3", [{"code": "99999", "pathway": "nope"}])
    assert "nope" in bad and "99999" in bad
    r = c.post("/api/review/g3/pathways", json={"picks": [{"code": "36475", "pathway": "nope"}]})
    assert r.status_code == 400 and "nope" in r.json()["detail"]
    r = c.post("/api/review/g3/pathways", json={"picks": []})
    assert r.status_code == 400
    assert c.post("/api/review/g3/retry").status_code == 409          # paused: confirm first
    assert c.post("/api/review/nope/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}]}).status_code == 404
    assert c.post("/api/review/nope/retry").status_code == 404


def test_pathways_endpoint_refuses_when_not_paused(world):
    check, c, _ = world
    check("done1")
    r = c.post("/api/review/done1/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}]})
    assert r.status_code == 409


# ---------------------------------------------------------------- end to end through the pipeline (needs A's resume)


def _upload(c, gid):
    with open(DELGADO_PDF, "rb") as f:
        r = c.post("/api/review/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid})
    assert r.status_code == 200, r.text
    return r.json()


def test_upload_pauses_confirm_resumes(world, fl_spans, delgado_spans, monkeypatch):
    _needs_a()
    _, c, gid = world
    stub = Stub(fl_spans, delgado_spans)
    monkeypatch.setattr(llm, "call", stub)
    d = _upload(c, gid)
    cid = d["chart_id"]
    assert d["state"] == "paused" and d["case"] is None and d["gate"]["suggested"] == [{"code": "36475", "pathway": "gsv"}]
    sec = next(s for s in d["status"]["stages"] if s["id"] == "section")
    assert sec["status"] == "needs_person" and sec["gate"]["kind"] == "confirm_pathways"
    assert d["status"]["resume"]["endpoint"] == f"/api/review/{cid}/pathways"
    assert "criteria_guideline" not in stub.calls and "judge_chart" not in stub.calls
    assert any(x["chart_id"] == cid and x["queue"] == "paused" for x in c.get("/api/orders").json())
    assert c.post(f"/api/review/{cid}/retry").status_code == 409
    # confirm the suggested section
    stub.calls.clear()
    r = c.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}], "by": "pat"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "done" and set(stub.calls) <= {"criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"}
    assert d["case"]["result"]["determination"] == "MET"
    conf = d["confirmation"]
    assert conf["confirmed"] == [{"code": "36475", "pathway": "gsv"}] and conf["suggested"] == conf["confirmed"]
    assert conf["by"] == "pat" and conf["h_key"] and d["case"]["h_key"] == conf["h_key"]
    assert d["gate"] is not None and d["gate"]["suggested"] == [{"code": "36475", "pathway": "gsv"}]   # kept for the record
    by = {x["criterion"]: x for x in d["case"]["requirements"]}
    assert by["size"]["mark"] == "documented" and by["size"]["highlights"]
    # not paused any more
    assert c.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}]}).status_code == 409
    # feedback carries the confirmed section and the H key
    fb = c.post(f"/api/review/{cid}/feedback", json={"kind": "logic_wrong", "side": "guideline", "text": "x",
                                                     "spans": [by["size"]["refs"][0]]})
    assert fb.status_code == 201
    item = fb.json()
    assert item["pathway"] == ["gsv"] and item["h_key"] == conf["h_key"] and item["run_id"] == d["status"]["run_id"]
    assert c.get(f"/api/review/{cid}").json()["feedback"] == [item]
    # on an evidence quote: side chart, the quote's lines, the requirement it hangs under
    quote = by["size"]["evidence"][0]
    fb = c.post(f"/api/review/{cid}/feedback", json={"kind": "evidence_elsewhere", "side": "chart", "text": "other leg",
                                                     "spans": quote["lines"], "requirements": ["size"]})
    assert fb.status_code == 201
    ev_item = fb.json()
    assert ev_item["side"] == "chart" and ev_item["spans"] == quote["lines"] and ev_item["requirements"] == ["size"]
    assert ev_item["pathway"] == ["gsv"] and ev_item["h_key"] == conf["h_key"]
    assert c.get(f"/api/review/{cid}").json()["feedback"] == [item, ev_item]


def test_confirm_a_different_section(world, fl_spans, delgado_spans, monkeypatch):
    _needs_a()
    _, c, gid = world
    stub = Stub(fl_spans, delgado_spans)
    monkeypatch.setattr(llm, "call", stub)
    cid = _upload(c, gid)["chart_id"]
    r = c.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": "accessory"}]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "done" and d["case"]["result"]["pathway_used"] == ["accessory"]
    assert d["confirmation"]["confirmed"] == [{"code": "36475", "pathway": "accessory"}]
    assert d["confirmation"]["suggested"] == [{"code": "36475", "pathway": "gsv"}]
    assert d["gate"]["suggested"] == [{"code": "36475", "pathway": "gsv"}]


def test_retry_after_a_failed_resume(world, fl_spans, delgado_spans, monkeypatch):
    _needs_a()
    _, c, gid = world
    stub = Stub(fl_spans, delgado_spans)
    monkeypatch.setattr(llm, "call", stub)
    cid = _upload(c, gid)["chart_id"]
    real = pipeline.judge.judge

    def failing(*a, **k):
        raise RuntimeError("judge down")
    monkeypatch.setattr(pipeline.judge, "judge", failing)
    r = c.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}], "by": "pat"})
    assert r.status_code == 500
    d = c.get(f"/api/review/{cid}").json()
    assert d["state"] == "failed" and d["confirmation"]["confirmed"] == [{"code": "36475", "pathway": "gsv"}]
    assert "judge down" in (d["status"]["error"] or "")
    monkeypatch.setattr(pipeline.judge, "judge", real)
    r = c.post(f"/api/review/{cid}/retry")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "done" and d["case"]["result"]["determination"] == "MET"
    assert d["confirmation"]["by"] == "pat"


def test_evidence_order_leads_with_what_the_page_shows_first():
    """One quote shows by default: the strongest against quote when contradicted, else the first for quote; a duration
    leads with the start note and the latest note comes next."""
    from app.review.review import order_evidence
    f1, f2, f3, a1, a2 = ({"side": "for", "span": "r1", "date": "2025-07-22"}, {"side": "for", "span": "r2", "date": "2025-03-18"},
                          {"side": "for", "span": "r3", "date": None}, {"side": "against", "span": "r4"}, {"side": "against", "span": "r5"})
    assert [e["span"] for e in order_evidence([f1, f2, a1, a2], "contradicted", False)] == ["r4", "r5", "r1", "r2"]
    assert [e["span"] for e in order_evidence([a1, f1, f2], "documented", False)] == ["r1", "r2", "r4"]
    assert [e["span"] for e in order_evidence([f3, f1, f2, a1], "documented", True)] == ["r2", "r1", "r3", "r4"]
    mid = {"side": "for", "span": "r6", "date": "2025-05-01"}
    assert [e["span"] for e in order_evidence([f1, mid, f2], "missing", True)] == ["r2", "r1", "r6"]
    assert order_evidence([], "missing", True) == []
