"""The progressive case page (review.preview_view): while H builds, the confirmed indication's lines; once the
checklist exists and the chart is read, the same lines with the requirements' word runs; once finished, no preview.
Offline: stub model, store in tmp_path; the preview is read from inside the stub at H and at the judge."""
from __future__ import annotations

import hashlib

import pytest

from app import pipeline
from app.core import llm
from app.review import review
from tests.conftest import SAMPLES
from tests.fake import Stub


@pytest.fixture
def seen(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    stub = Stub(fl_spans, delgado_spans)
    got: dict[str, dict] = {}

    def call(run_id, step, prompt, schema, **kw):
        if step in ("criteria_guideline", "judge_chart") and step not in got:
            got[step] = review.review_doc("c1")
        return stub(run_id, step, prompt, schema, **kw)
    monkeypatch.setattr(llm, "call", call)
    assert pipeline.run("", "c1", gid, rspans=delgado_spans, pause_at_pathways=True) is None
    assert "preview" not in review.review_doc("c1")            # paused at the gate: nothing yet
    pipeline.resume("c1", [{"code": "36475", "pathway": "gsv"}], by="Dana")
    return got


def _keys(x) -> set:
    if isinstance(x, dict):
        return set(x) | {k for v in x.values() for k in _keys(v)}
    if isinstance(x, list):
        return {k for v in x for k in _keys(v)}
    return set()


def test_guideline_while_the_checklist_is_built(seen):
    doc = seen["criteria_guideline"]
    assert doc["state"] == "running" and doc["status"]["current"] == "checklist"
    p = doc["preview"]
    assert set(p) == {"phase", "guideline"} and p["phase"] == "guideline"
    t = p["guideline"]["tree"]
    lines = [ln for sec in t["sections"] for ln in sec["lines"]]
    assert lines and all({"id", "text", "page", "blank_before", "kind", "block"} <= set(ln) for ln in lines)
    assert all(ln["block"] is None for ln in lines) and t["blocks"] == [] and p["guideline"]["rest"] == []
    assert doc["case"] is None


def test_highlights_once_the_checklist_exists(seen):
    doc = seen["judge_chart"]
    assert doc["status"]["current"] == "read"
    p = doc["preview"]
    assert set(p) == {"phase", "guideline", "marks"} and p["phase"] == "highlights"
    assert p["marks"] and all(set(m) <= {"criterion", "refs", "block", "highlights", "same", "near"} for m in p["marks"])
    assert all(m["highlights"] for m in p["marks"])
    blocks = p["guideline"]["tree"]["blocks"]
    assert blocks and all(set(b) == {"id", "lines", "items"} for b in blocks)
    assert all(set(it) == {"criterion"} for b in blocks for it in b["items"])
    assert p["guideline"]["rest"]                              # the rest of the policy, folded as case.rest
    assert not _keys(p) & {"mark", "say", "bad", "status", "evidence", "verdict", "accepted", "in_ask", "progress",
                           "packet", "set_aside", "misses", "counts"}       # nothing about status
    assert doc["case"] is None


def test_finished_has_no_preview_and_the_same_drawing(seen):
    doc = review.review_doc("c1")
    assert doc["state"] == "done" and "preview" not in doc and doc["case"]
    p = seen["judge_chart"]["preview"]
    case = doc["case"]
    assert [s["lines"] for s in case["tree"]["sections"]] == [s["lines"] for s in p["guideline"]["tree"]["sections"]]
    assert case["rest"] == p["guideline"]["rest"]
    want = {x["criterion"]: x["highlights"] for x in case["requirements"]}
    assert {m["criterion"]: m["highlights"] for m in p["marks"]} == want
