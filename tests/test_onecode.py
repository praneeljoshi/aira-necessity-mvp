"""One code, one pathway (app/understand/onecode.py): in the review flow an order with 2+ codes pauses at pick_code before C;
the picked code alone goes on to the section gate; an unpicked not-covered code does not stop the case; /split makes
a sibling case for another code; single-code orders and the / flow are unchanged. Offline: stub model, store and
feedback in tmp_path; never touches data/."""
from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline
from app.core import llm, status, store
from app.review import feedback
from app.understand import onecode
from tests.conftest import SAMPLES
from tests.fake import Stub

CHART = SAMPLES / "synthetic" / "maria_delgado_chart.pdf"


@pytest.fixture
def world(tmp_store, tmp_path, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    monkeypatch.setattr(feedback, "FEEDBACK", tmp_path / "feedback")
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    c = TestClient(main.app)

    class W:
        client, guideline = c, gid
        stub: Stub = None

        @staticmethod
        def model(**kw) -> Stub:
            W.stub = Stub(fl_spans, delgado_spans, **kw)
            monkeypatch.setattr(llm, "call", W.stub)
            return W.stub

        @staticmethod
        def codes(codes):
            """The Delgado chart prints only 36475 (detect_order drops codes not in the chart): put them back."""
            real = pipeline.detect_order

            def detect(rspans, chart_id, run_id):
                o = real(rspans, chart_id, run_id)
                o.procedure.cpt = list(codes)
                return o
            monkeypatch.setattr(pipeline, "detect_order", detect)

        @staticmethod
        def upload(codes=("36475", "36478"), **kw) -> str:
            W.codes(codes)
            W.model(order={"cpt": tuple(codes)}, **kw)
            with open(CHART, "rb") as f:
                r = c.post("/api/review/charts", files={"file": ("delgado.pdf", f, "application/pdf")},
                           data={"guideline_id": gid})
            assert r.status_code == 200, r.text
            return r.json()["chart_id"]

        @staticmethod
        def doc(cid: str) -> dict:
            r = c.get(f"/api/review/{cid}")
            assert r.status_code == 200, r.text
            return r.json()
    return W


def stages(d: dict) -> dict:
    return {s["id"]: s for s in d["status"]["stages"]}


def test_two_codes_pause_at_pick_code_before_c(world):
    cid = world.upload()
    assert world.stub.calls == ["detect_order"]                  # no narrow_guideline yet
    d = world.doc(cid)
    assert d["state"] == "paused"
    assert d["status"]["resume"] == {"stage": "guideline", "needs": "code", "endpoint": f"/api/review/{cid}/code"}
    g = d["gate"]
    assert g["kind"] == "pick_code" and g["endpoint"] == f"/api/review/{cid}/code"
    assert g["split_endpoint"] == f"/api/review/{cid}/split"
    assert [x["code"] for x in g["codes"]] == ["36475", "36478"]
    assert [x["suggested"] for x in g["codes"]] == [True, False]
    a, b = g["codes"]
    assert set(a) == {"code", "descriptor", "chart_lines", "tag", "suggested"}
    assert a["descriptor"].startswith("36475") and b["descriptor"].startswith("36478") and a["tag"] is None
    assert a["chart_lines"] and "36475" in a["chart_lines"][0]["text"] and a["chart_lines"][0]["page"] >= 1
    assert b["chart_lines"] == []                                # the chart never prints 36478
    o = stages(d)["order"]
    assert o["status"] == "needs_person" and o["gate"]["kind"] == "pick_code" and o["gate"]["options"] == ["36475", "36478"]
    assert stages(d)["guideline"]["status"] == "waiting"
    assert d["code"] is None and d["focus"] is None
    row = next(x for x in world.client.get("/api/orders").json() if x["chart_id"] == cid)
    assert row["queue"] == "paused" and row["code"] is None
    # the section endpoints refuse while the code is open
    assert world.client.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}]}).status_code == 409


def test_pick_goes_on_to_the_section_with_one_code(world):
    cid = world.upload()
    c = world.client
    assert c.post(f"/api/review/{cid}/code", json={"code": "99999", "by": "Dana"}).status_code == 400
    world.model()
    r = c.post(f"/api/review/{cid}/code", json={"code": "36475", "by": "Dana"})
    assert r.status_code == 200, r.text
    assert world.stub.calls == ["narrow_guideline"]
    assert Stub._procedure(world.stub.prompts[0][1])["cpt"] == ["36475"]
    d = world.doc(cid)
    assert d["state"] == "paused" and d["gate"]["suggested"] == [{"code": "36475", "pathway": "gsv"}]
    assert stages(d)["order"]["answered_by"]["by"] == "Dana" and stages(d)["order"]["answered_by"]["confirmed"] == ["36475"]
    assert d["pick_code"]["picked"] == "36475" and d["pick_code"]["by"] == "Dana" and d["pick_code"]["at"]
    assert d["status"]["override"]["cpt"] == ["36475"] and d["order"]["cpt"] == ["36475"]
    assert d["code"] == "36475" and d["focus"]["code"] == "36475" and d["focus"]["pathway_name"] is None
    assert d["focus"]["guideline_title"] == "Treatments for Varicose Veins / Venous Insufficiency"
    assert d["focus"]["procedure_short"] and "36475" not in d["focus"]["procedure_short"]
    # not paused at the code any more
    assert c.post(f"/api/review/{cid}/code", json={"code": "36475"}).status_code == 409
    world.model()
    r = c.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}], "by": "Dana"})
    assert r.status_code == 200, r.text
    d = world.doc(cid)
    assert d["state"] == "done" and d["case"]["result"]["determination"] == "MET" and d["case"]["code"] == "36475"
    assert d["focus"] == {"code": "36475", "procedure_short": d["focus"]["procedure_short"],
                          "pathway_name": "Great or Small Saphenous Veins",
                          "guideline_title": "Treatments for Varicose Veins / Venous Insufficiency"}
    assert store.load_result(cid)["meta"]["override"]["cpt"] == ["36475"]       # a re-check keeps the code
    row = next(x for x in c.get("/api/orders").json() if x["chart_id"] == cid)
    assert row["code"] == "36475"


def test_an_unpicked_not_covered_code_does_not_stop(world):
    cid = world.upload(codes=("36475", "36468"))
    world.model()
    assert world.client.post(f"/api/review/{cid}/code", json={"code": "36475"}).status_code == 200
    d = world.doc(cid)
    assert d["state"] == "paused" and d["gate"]["suggested"] == [{"code": "36475", "pathway": "gsv"}]
    world.model()
    world.client.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": "gsv"}]})
    d = world.doc(cid)
    assert d["case"]["result"]["determination"] == "MET"
    assert [g["code"] for g in store.load_result(cid)["selection"]["code_gate"]] == ["36475"]


def test_split_makes_a_sibling_case_for_the_other_code(world):
    cid = world.upload(codes=("36475", "36468"))
    c = world.client
    assert c.post(f"/api/review/{cid}/split", json={"code": "12345"}).status_code == 400
    assert c.post("/api/review/nope/split", json={"code": "36475"}).status_code == 404
    world.model()
    r = c.post(f"/api/review/{cid}/split", json={"code": "36468", "by": "Dana"})
    assert r.status_code == 200, r.text
    new = r.json()["chart_id"]
    assert new != cid and r.json() == {"chart_id": new, "from": cid, "code": "36468"}
    assert world.stub.calls == ["narrow_guideline"]                # B is the stored order; A2 not reached
    d = world.doc(new)
    # 36468 is non-covered: that case alone ends not covered; the original still waits for its code
    assert d["code"] == "36468" and d["case"]["result"]["determination"] == "NOT_COVERED"
    assert d["order"]["patient_name"] == world.doc(cid)["order"]["patient_name"]
    assert world.doc(cid)["state"] == "paused" and world.doc(cid)["gate"]["kind"] == "pick_code"
    link = d["split"][0]
    assert set(link) == {"from", "to", "code", "by", "at"} and link["from"] == cid and link["to"] == new
    assert world.doc(cid)["split"] == [link]
    assert store.chart_meta(new)["filename"] == store.chart_meta(cid)["filename"]
    # a split case knows the original order's codes: split again from it
    world.model()
    r = c.post(f"/api/review/{new}/split", json={"code": "36475"})
    assert r.status_code == 200, r.text
    d2 = world.doc(r.json()["chart_id"])
    assert d2["state"] == "paused" and d2["gate"]["suggested"] == [{"code": "36475", "pathway": "gsv"}]
    rows = {x["chart_id"]: x for x in c.get("/api/orders").json()}
    assert rows[new]["code"] == "36468" and rows[r.json()["chart_id"]]["code"] == "36475" and rows[cid]["code"] is None


def test_single_code_order_unchanged(world):
    cid = world.upload(codes=("36475",))
    assert world.stub.calls == ["detect_order", "narrow_guideline"]
    d = world.doc(cid)
    assert d["state"] == "paused" and d["gate"].get("kind") != "pick_code"
    assert d["gate"]["suggested"] == [{"code": "36475", "pathway": "gsv"}] and d["pick_code"] is None
    assert stages(d)["order"]["gate"] is None and d["code"] == "36475"


def test_home_flow_two_codes_unchanged(world, delgado_spans):
    world.model(order={"cpt": ("36475", "36478")})
    r = pipeline.run("", "home", world.guideline, rspans=delgado_spans, override={"cpt": ["36475", "36478"]})
    assert r is not None and "narrow_guideline" in world.stub.calls
    assert onecode.load("home") is None and status.load_status("home")["state"] != "paused"
    assert [g["code"] for g in store.load_result("home")["selection"]["code_gate"]] == ["36475", "36478"]
