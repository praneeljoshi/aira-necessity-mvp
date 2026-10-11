"""The section gate as the coordinator reads it: each section with the chart lines that bear on it ("why it might
fit"), sections that look alike offered for comparison, and "None of these": the guideline doesn't apply, with the
other guidelines on file and a re-check against one of them. Offline: the stub model, tmp_path. Never touches data/."""
from __future__ import annotations

from app import pipeline
from app.core import llm
from tests.conftest import SAMPLES
from tests.fake import Stub
from tests.test_strikes import CHART, world  # noqa: F401  (the review-flow fixture)


def paused(world, monkeypatch, fl_spans, delgado_spans) -> str:
    monkeypatch.setattr(llm, "call", Stub(fl_spans, delgado_spans))
    with open(CHART, "rb") as f:
        r = world.client.post("/api/review/charts", files={"file": ("d.pdf", f, "application/pdf")}, data={"guideline_id": world.guideline})
    cid = r.json()["chart_id"]
    assert world.doc(cid)["state"] == "paused"
    return cid


def test_each_section_says_why_it_might_fit(world, monkeypatch, fl_spans, delgado_spans):
    cid = paused(world, monkeypatch, fl_spans, delgado_spans)
    g = {p["id"]: p for p in world.doc(cid)["gate"]["pathways"]}
    gsv = g["gsv"]
    assert gsv["suggested"] and gsv["why"], gsv
    assert any(q["order"] for q in gsv["why"]) and all(q["text"] and q["page"] for q in gsv["why"])
    assert all("great saphenous" in q["text"].lower() or "small saphenous" in q["text"].lower() for q in gsv["why"])
    # a line that only repeats the order's code is not distinctive: a chip, not a quote
    assert gsv["shares_codes"] == ["36475"] and g["accessory"]["shares_codes"] == ["36475"]
    assert not any("CPT" in q["text"] and "saphenous" not in q["text"].lower() for p in g.values() for q in p["why"])
    assert len(gsv["body"]) == gsv["n_lines"] and gsv["body"][0]["text"].strip() == "Great or Small Saphenous Veins"
    assert "accessory" in gsv["alike"] and "gsv" in g["accessory"]["alike"] and not g["tributaries"]["alike"]


def test_none_of_these_means_the_guideline_does_not_apply(world, monkeypatch, fl_spans, delgado_spans, fl_text):
    cid = paused(world, monkeypatch, fl_spans, delgado_spans)
    other = pipeline.add_guideline(fl_text, "fl-copy.pdf", "f" * 64, "fl-copy")
    c = world.client
    r = c.post(f"/api/review/{cid}/none", json={"by": "Dana"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "done" and d["nofit"]["by"] == "Dana" and d["nofit"]["suggested"]
    assert d["nofit"]["suggested_names"] == ["Great or Small Saphenous Veins"]
    res = d["case"]["result"]
    assert res["determination"] == "CANT_CHECK" and "Dana judged that no indication" in res["reason"]
    assert [x["id"] for x in d["guidelines"]] == [other]
    assert world.row(cid)["queue"] == "cant_check"
    assert c.post(f"/api/review/{cid}/none", json={"by": "Dana"}).status_code == 409          # not at the gate now
    # check it against the other guideline: it pauses again at that guideline's sections
    r = c.post(f"/api/review/{cid}/recheck", json={"guideline_id": other, "by": "Dana"})
    assert r.status_code == 200, r.text
    d = world.doc(cid)
    assert d["state"] == "paused" and d["guideline"]["id"] == other and d["nofit"] is None and d["gate"]["pathways"]
    assert c.post(f"/api/review/{cid}/recheck", json={"guideline_id": "nope"}).status_code == 404


def test_a_paused_gate_shows_this_runs_suggestion_not_an_old_confirmation(world, monkeypatch, fl_spans, delgado_spans):
    """A re-checked case pauses again: its gate suggests what this run's selection.json says, never the suggestion
    recorded in an earlier run's pathways.json."""
    from app.core import store
    cid = paused(world, monkeypatch, fl_spans, delgado_spans)
    store.save_confirmation(cid, {"suggested": [{"code": "36475", "pathway": "accessory"}],
                                  "confirmed": [{"code": "36475", "pathway": "accessory"}], "by": "Dana", "at": "2026-01-01T00:00:00"})
    g = world.doc(cid)["gate"]
    assert g["suggested"] == [{"code": "36475", "pathway": "gsv"}]
    assert {p["id"]: p["suggested"] for p in g["pathways"]}["gsv"] and not {p["id"]: p["suggested"] for p in g["pathways"]}["accessory"]
