"""Every patient has a path: /patients/<chart_id> (the screen, that patient selected) and /patients/<chart_id>/tree
(the same screen, main area in the guideline view) in every state; old links redirect. Offline."""
from __future__ import annotations

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from app import llm, main, pipeline
from tests.conftest import SAMPLES, sid
from tests.fake import Stub


@pytest.fixture
def world(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    def check(chart_id, override=None, **kw):
        monkeypatch.setattr(llm, "call", Stub(fl_spans, delgado_spans, **kw))
        return pipeline.run("", chart_id, gid, rspans=delgado_spans, override=override)
    return check, TestClient(main.app), gid


def tree_of(c, cid):
    r = c.get(f"/api/orders/{cid}/tree")
    assert r.status_code == 200, r.text
    return r.json()


def test_patient_and_tree_pages_for_every_determination(world, delgado_spans):
    check, c, _ = world
    against = sid(delgado_spans, "Competent. No reflux. Diameter 2.8 mm.")
    cases = {
        "met": (check("met"), "MET"),
        "insufficient": (check("insufficient", verdicts={"compression": {"status": "INSUFFICIENT", "for": []}}), "INSUFFICIENT"),
        "not_met": (check("not_met", verdicts={"size": {"status": "NOT_MET", "against": [against]}}), "NOT_MET"),
        "not_covered": (check("not_covered", override={"cpt": ["36468"], "target": "spider veins"}), "NOT_COVERED"),
        "cant_check": (check("cant_check", override={"cpt": ["33207"]}), "CANT_CHECK"),
        "which_section": (check("which_section", order={"target": None}), "INSUFFICIENT"),
    }
    for cid, (r, det) in cases.items():
        assert r.determination == det, cid
        page = c.get(f"/patients/{cid}")
        assert page.status_code == 200 and "<title>Prior auth</title>" in page.text, cid
        tree = c.get(f"/patients/{cid}/tree")        # the same screen; the page switches the main area by the path
        assert tree.status_code == 200 and tree.text == page.text, cid
        d = tree_of(c, cid)
        assert d["result"]["determination"] == det and not d.get("pending"), cid
        t = d["tree"]
        if det in ("MET", "NOT_MET") or cid == "insufficient":
            assert t["sections"] and t["sections"][0]["label"] == "Great or Small Saphenous Veins", cid
            assert any(ln["kind"] == "req" for ln in t["sections"][0]["lines"]), cid
        if det == "NOT_COVERED":
            assert t["codes"][0]["code"] == "36468" and "Non-covered" in t["codes"][0]["lines"][0]["text"] and not t["sections"]
        if det == "CANT_CHECK":
            assert not t["sections"] and not t["codes"] and not t["blocks"]
        if cid == "which_section":
            assert [x["name"] for x in t["candidates"]][:1] == ["Great or Small Saphenous Veins"] and not t["sections"]
    # marks per state
    assert tree_of(c, "insufficient")["tree"]["misses"][0]["mark"] == "missing"
    assert tree_of(c, "not_met")["tree"]["misses"][0]["mark"] == "contradicted"
    assert tree_of(c, "met")["tree"]["misses"] == []


def test_redirects_and_unknown_ids(world):
    check, c, _ = world
    check("delgado")
    r = c.get("/tree/delgado", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/patients/delgado/tree"
    assert c.get("/tree/delgado").status_code == 200           # followed: the screen in the guideline view
    # an unknown id serves the screen (the rail stays); its data answers 404 and the page says "No chart with this id"
    for path in ("/patients/nope", "/patients/nope/tree", "/tree/nope"):
        r = c.get(path)
        assert r.status_code == 200 and "<title>Prior auth</title>" in r.text and "No case with this id." in r.text, path
    assert c.get("/api/orders/nope/tree").status_code == 404
    assert c.get("/api/orders/nope").status_code == 404
    # the view is a component of the screen
    assert c.get("/static/tree.js").status_code == 200 and "TreeView" in c.get("/static/tree.js").text
    assert c.get("/static/tree.css").status_code == 200
    assert '/static/tree.js' in c.get("/patients/delgado").text


def test_tree_page_while_running_and_after_a_failure(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    c = TestClient(main.app)

    class Slow(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            time.sleep(0.08)
            return super().__call__(run_id, step, prompt, schema)
    monkeypatch.setattr(llm, "call", Slow(fl_spans, delgado_spans))
    with open(SAMPLES / "synthetic" / "maria_delgado_chart.pdf", "rb") as f:
        cid = c.post("/api/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid}).json()["chart_id"]
    # running: the patient's tree address serves the page, the data is the status
    assert c.get(f"/patients/{cid}/tree").status_code == 200
    d = c.get(f"/api/orders/{cid}/tree").json()
    assert d.get("pending") or d["result"]
    if d.get("pending"):
        assert d["status"]["state"] == "running" and "tree" not in d
    for _ in range(200):
        if c.get(f"/api/orders/{cid}/status").json()["state"] != "running":
            break
        time.sleep(0.02)
    d = c.get(f"/api/orders/{cid}/tree").json()
    assert d["result"]["determination"] == "MET" and d["tree"]["sections"]

    # failed before any result: the page is served, the data says where it stopped, retry brings the tree
    monkeypatch.setattr(main, "BACKGROUND", False)
    fail = {"on": True}

    class Flaky(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            if step == "judge_chart" and fail["on"]:
                raise RuntimeError("the model is down")
            return super().__call__(run_id, step, prompt, schema)
    monkeypatch.setattr(llm, "call", Flaky(fl_spans, delgado_spans))
    with open(SAMPLES / "synthetic" / "maria_delgado_chart.pdf", "rb") as f:
        r = c.post("/api/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid})
    assert r.status_code == 500
    cid2 = [x for x in c.get("/api/orders").json() if x["queue"] == "failed"][0]["chart_id"]
    assert c.get(f"/patients/{cid2}/tree").status_code == 200 and c.get(f"/patients/{cid2}").status_code == 200
    d = c.get(f"/api/orders/{cid2}/tree").json()
    assert d["pending"] and d["status"]["state"] == "failed" and "the model is down" in d["status"]["error"]
    assert [s["status"] for s in d["status"]["stages"]][6] == "failed"      # "read", after the record stage
    fail["on"] = False
    assert c.post(f"/api/orders/{cid2}/retry").json()["result"]["determination"] == "MET"
    assert c.get(f"/api/orders/{cid2}/tree").json()["tree"]["sections"]


def test_review_page_is_versioned_and_not_cached(tmp_store):
    from fastapi.testclient import TestClient
    from app import main
    c = TestClient(main.app)
    r = c.get("/review/abc")
    assert r.status_code == 200 and "no-cache" in r.headers["cache-control"]
    assert "/static/review.js?v=" in r.text and "/static/review-styles/plain.css?v=" in r.text
    assert "no-cache" in c.get("/static/review.js").headers["cache-control"]
    # one theme for both front ends: /review and / load the same tokens and the same theme key (Soft / Light / Dark)
    assert "/static/theme.css?v=" in r.text
    t = c.get("/static/theme.css")
    assert t.status_code == 200 and "no-cache" in t.headers["cache-control"] and 'data-theme="dark"' in t.text and 'data-theme="soft"' in t.text
    home = c.get("/").text
    assert '/static/theme.css' in home and 'data-style="plain"' in home and "review.theme" in home and 'id="themeBtn"' in home
