"""The API shape the screen reads, offline (stub model, store in tmp_path)."""
from fastapi.testclient import TestClient

from app import llm, main
from tests.conftest import SAMPLES
from tests.fake import Stub


def test_chart_upload_and_detail(tmp_store, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "call", Stub(fl_spans, delgado_spans))
    monkeypatch.setattr(main, "BACKGROUND", False)       # inline: the upload answers with the finished check
    c = TestClient(main.app)
    with open(SAMPLES / "fl_varicose_veins_guideline.pdf", "rb") as g:
        gid = c.post("/api/guidelines", files={"file": ("fl.pdf", g, "application/pdf")}).json()["id"]
    assert [x["id"] for x in c.get("/api/guidelines").json()] == [gid]
    with open(SAMPLES / "synthetic" / "maria_delgado_chart.pdf", "rb") as f:
        d = c.post("/api/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid}).json()
    assert d["result"]["determination"] == "MET" and d["result"]["queue"] == "ready"
    assert d["packet"] and all(p["status"] == "met" for p in d["packet"])
    assert d["decided"]["sections"][0]["name"] == "Great or Small Saphenous Veins"
    assert d["decided"]["codes"] == [{"code": "36475", "tag": "covered", "description": d["decided"]["codes"][0]["description"], "ordered": True}]
    rows = c.get("/api/orders").json()
    assert rows[0]["queue"] == "ready" and rows[0]["patient_name"] == "Maria Elena Delgado"
    assert c.get(f"/api/orders/{d['chart_id']}").json()["ask"].startswith("Nothing to ask")
    r = c.post(f"/api/orders/{d['chart_id']}/recheck", json={"target": "left great saphenous vein"}).json()
    assert r["result"]["determination"] == "MET"
    st = c.get(f"/api/orders/{d['chart_id']}/status").json()
    assert st["state"] == "done" and [s["status"] for s in st["stages"]] == ["done"] * 9
    t = c.get(f"/api/orders/{d['chart_id']}/tree").json()["tree"]
    assert t["sections"][0]["label"] == "Great or Small Saphenous Veins"
    assert c.get(f"/tree/{d['chart_id']}").status_code == 200
