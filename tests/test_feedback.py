"""Feedback on a case: create, list, remove (a tombstone, never a rewrite), every stored field, and the cross-case
list by guideline and section. Offline; the feedback root is tmp_path."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import feedback, llm, main, pipeline
from tests.conftest import SAMPLES, sid
from tests.fake import Stub

FL_PDF = SAMPLES / "fl_varicose_veins_guideline.pdf"


@pytest.fixture
def world(tmp_store, tmp_path, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    monkeypatch.setattr(feedback, "FEEDBACK", tmp_path / "feedback")
    sha = hashlib.sha256(FL_PDF.read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    def check(chart_id, override=None, **kw):
        monkeypatch.setattr(llm, "call", Stub(fl_spans, delgado_spans, **kw))
        return pipeline.run("", chart_id, gid, rspans=delgado_spans, override=override)
    return check, TestClient(main.app), gid, sha, tmp_path / "feedback"


def test_create_list_remove_and_fields(world, fl_spans, delgado_spans):
    check, c, gid, sha, root = world
    r = check("met")
    g1, g2 = sid(fl_spans, "There is demonstrated saphenous reflux"), sid(fl_spans, "class C2* or greater")
    body = {"kind": "edit", "side": "guideline", "text": "reads as one requirement", "proposal": "Reflux is shown on duplex",
            "spans": [f"{g1}-{g2}"], "requirements": ["reflux", "ceap"], "by": "pat"}
    resp = c.post("/api/review/met/feedback", json=body)
    assert resp.status_code == 201, resp.text
    item = resp.json()
    assert len(item["id"]) == 12 and int(item["id"], 16) >= 0
    assert item["chart_id"] == "met" and item["kind"] == "edit" and item["side"] == "guideline"
    assert item["text"] == "reads as one requirement" and item["proposal"] == "Reflux is shown on duplex"
    assert item["spans"][0] == g1 and item["spans"][-1] == g2 and len(item["spans"]) > 1       # the range, expanded
    assert item["requirements"] == ["reflux", "ceap"] and item["by"] == "pat" and item["at"]
    assert item["guideline_id"] == gid and item["guideline_sha"] == sha
    assert item["pathway"] == ["gsv"] and item["h_key"] is None and item["run_id"] == r.run_id
    assert set(item) == {"id", "chart_id", "kind", "side", "text", "proposal", "spans", "requirements", "guideline_id",
                         "guideline_sha", "pathway", "h_key", "run_id", "by", "at", "code"}
    # a chart-side item: an evidence quote under a requirement, filed with the quote's lines
    reqs = {x["criterion"]: x for x in c.get("/api/review/met").json()["case"]["requirements"]}
    quote = next(e for e in reqs["ulcer"]["evidence"] if e["side"] == "against")
    assert sid(delgado_spans, "No ulceration.") in quote["lines"]
    i2 = c.post("/api/review/met/feedback", json={"kind": "wrong_evidence", "side": "chart", "text": "", "spans": quote["lines"],
                                                  "requirements": ["ulcer"]}).json()
    assert i2["spans"] == quote["lines"] and i2["proposal"] is None and i2["by"] is None
    assert [x["id"] for x in c.get("/api/review/met/feedback").json()] == [item["id"], i2["id"]]
    assert c.get("/api/review/met").json()["feedback"] == [item, i2]
    # on disk: append-only jsonl, the index under the guideline's sha16 and the section
    lines = [json.loads(x) for x in (root / "met.jsonl").read_text().splitlines()]
    assert [x["id"] for x in lines] == [item["id"], i2["id"]]
    idx = root / "by-guideline" / sha[:16] / "gsv.jsonl"
    assert [json.loads(x) for x in idx.read_text().splitlines()] == [{"id": item["id"], "chart_id": "met", "at": item["at"]},
                                                                      {"id": i2["id"], "chart_id": "met", "at": i2["at"]}]
    # remove: a tombstone line, the list filters it, a second remove is 404
    assert c.delete(f"/api/review/met/feedback/{item['id']}").json() == {"ok": True}
    assert [x["id"] for x in c.get("/api/review/met/feedback").json()] == [i2["id"]]
    lines = [json.loads(x) for x in (root / "met.jsonl").read_text().splitlines()]
    assert len(lines) == 3 and lines[-1]["op"] == "remove" and lines[-1]["id"] == item["id"]
    assert json.loads(idx.read_text().splitlines()[-1])["op"] == "remove"
    assert c.delete(f"/api/review/met/feedback/{item['id']}").status_code == 404
    assert c.delete("/api/review/met/feedback/000000000000").status_code == 404


def test_bad_requests(world):
    check, c, _, _, _ = world
    check("met")
    assert c.post("/api/review/met/feedback", json={"kind": "nope", "side": "guideline", "spans": ["g0001"]}).status_code == 400
    assert c.post("/api/review/met/feedback", json={"kind": "logic_wrong", "side": "guideline", "spans": []}).status_code == 400
    assert c.post("/api/review/met/feedback", json={"kind": "logic_wrong", "side": "elsewhere", "spans": ["g0001"]}).status_code == 400
    assert c.post("/api/review/nope/feedback", json={"kind": "logic_wrong", "side": "guideline", "spans": ["g0001"]}).status_code == 404
    assert c.get("/api/feedback").status_code == 400
    assert c.get("/api/review/met/feedback").json() == []


def test_every_kind_is_accepted(world):
    check, c, _, _, _ = world
    check("met")
    assert {"wrong_evidence", "evidence_elsewhere", "is_evidence"} <= set(feedback.KINDS)     # is_evidence: compatibility
    for k in feedback.KINDS:
        side = "chart" if k in ("wrong_evidence", "evidence_elsewhere", "is_evidence") else "guideline"
        assert c.post("/api/review/met/feedback", json={"kind": k, "side": side, "spans": ["g0001"]}).status_code == 201, k
    assert [x["kind"] for x in feedback.list_for("met")] == list(feedback.KINDS)


def test_evidence_elsewhere_on_a_quote(world, delgado_spans):
    """"This evidence is about something else", filed on a quote under a requirement: stored on the chart side with
    the quote's r ids (a range span is expanded) and the requirement it was attached to; indexed under the section."""
    check, c, _, sha, root = world
    check("met")
    reqs = {x["criterion"]: x for x in c.get("/api/review/met").json()["case"]["requirements"]}
    quote = reqs["reflux"]["evidence"][0]
    assert quote["side"] == "for" and quote["lines"] and quote["span"]
    item = c.post("/api/review/met/feedback", json={"kind": "evidence_elsewhere", "side": "chart", "text": "the right leg",
                                                    "spans": [quote["span"]], "requirements": ["reflux"], "by": "pat"}).json()
    assert item["kind"] == "evidence_elsewhere" and item["side"] == "chart" and item["text"] == "the right leg"
    assert item["spans"] == quote["lines"] and all(x.startswith("r") for x in item["spans"])
    assert item["requirements"] == ["reflux"] and item["pathway"] == ["gsv"] and item["by"] == "pat"
    assert set(item["spans"]) & set(quote["lines"])                   # the page matches a chip to its quote this way
    idx = root / "by-guideline" / sha[:16] / "gsv.jsonl"
    assert json.loads(idx.read_text().splitlines()[-1])["id"] == item["id"]
    assert c.get("/api/feedback", params={"guideline": sha[:16], "pathway": "gsv"}).json() == [item]
    assert c.get("/api/review/met").json()["feedback"] == [item]


def test_cross_case_list(world, fl_spans):
    check, c, gid, sha, root = world
    check("a")
    check("b")
    check("c", override={"cpt": ["36468"], "target": "spider veins"})       # stopped at the code gate: no section
    g = sid(fl_spans, "The varicosities are at least 3 millimeters")
    fa = c.post("/api/review/a/feedback", json={"kind": "logic_wrong", "side": "guideline", "text": "a", "spans": [g]}).json()
    fb = c.post("/api/review/b/feedback", json={"kind": "not_a_requirement", "side": "guideline", "text": "b", "spans": [g]}).json()
    fc = c.post("/api/review/c/feedback", json={"kind": "should_be_requirement", "side": "guideline", "text": "c", "spans": [g]}).json()
    assert fc["pathway"] == [] and (root / "by-guideline" / sha[:16] / "none.jsonl").exists()
    ids = lambda rows: [x["id"] for x in rows]
    assert ids(c.get("/api/feedback", params={"guideline": gid}).json()) == [fa["id"], fb["id"], fc["id"]]
    assert ids(c.get("/api/feedback", params={"guideline": sha[:16]}).json()) == [fa["id"], fb["id"], fc["id"]]
    assert ids(c.get("/api/feedback", params={"guideline": gid, "pathway": "gsv"}).json()) == [fa["id"], fb["id"]]
    assert ids(c.get("/api/feedback", params={"guideline": gid, "pathway": "accessory"}).json()) == []
    assert ids(c.get("/api/feedback", params={"chart_id": "b"}).json()) == [fb["id"]]
    assert ids(c.get("/api/feedback", params={"guideline": gid, "chart_id": "b"}).json()) == [fb["id"]]
    assert c.get("/api/feedback", params={"guideline": "unknown-guideline"}).json() == []
    # removed items leave the cross-case list too
    c.delete(f"/api/review/a/feedback/{fa['id']}")
    assert ids(c.get("/api/feedback", params={"guideline": gid, "pathway": "gsv"}).json()) == [fb["id"]]


def test_feedback_before_the_check_finishes(world, delgado_spans):
    """A running check has a status but no result: feedback is still accepted, the fields it can't know are null."""
    check, c, gid, sha, _ = world
    from app import status
    status.Recorder("run1", gid, "chart.pdf")
    item = c.post("/api/review/run1/feedback", json={"kind": "logic_wrong", "side": "guideline", "spans": ["g0001-g0002"]}).json()
    assert item["guideline_id"] == gid and item["guideline_sha"] == sha and item["pathway"] == [] and item["run_id"] is None
    assert item["spans"] == ["g0001", "g0002"]
