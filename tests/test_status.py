"""The check's status, stage by stage (app/core/status.py), recorded by pipeline.run and read by the screen. Offline:
stub model, store in tmp_path."""
from __future__ import annotations

import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline
from app.core import llm, status
from tests.conftest import SAMPLES
from tests.fake import Stub

STAGES = ["chart", "order", "guideline", "section", "checklist", "record", "read", "verify", "decide"]


@pytest.fixture
def setup(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    def go(chart_id="delgado", stub=None, **kw):
        stub = stub or Stub(fl_spans, delgado_spans, **kw)

        def call(run_id, step, prompt, schema, **k):      # the stub, writing a run log the way llm.call does
            out = stub(run_id, step, prompt, schema, **k)
            llm._log(run_id, step, {"step": step, "model": "stub", "parsed": out.model_dump()})
            return out
        monkeypatch.setattr(llm, "call", call)
        try:
            r = pipeline.run("", chart_id, gid, rspans=delgado_spans, source="cli")
        except Exception as e:
            r = e
        return r, status.load_status(chart_id), stub
    return go


def by_id(st):
    return {s["id"]: s for s in st["stages"]}


def test_normal_run_records_every_stage(setup):
    r, st, _ = setup()
    assert r.determination == "MET"
    assert [s["id"] for s in st["stages"]] == STAGES
    assert [s["status"] for s in st["stages"]] == ["done"] * 9
    assert st["state"] == "done" and st["run_id"] == r.run_id and st["ended_at"] and st["current"] is None
    s = by_id(st)
    for x in st["stages"]:
        assert x["started_at"] and x["ended_at"], x["id"]
    assert s["chart"]["summary"].startswith(f"{len(pipeline.store.load_chart_spans('delgado'))} lines over")
    assert "Maria Elena Delgado" in s["order"]["summary"] and "36475" in s["order"]["summary"]
    assert "Florida Blue" in s["guideline"]["summary"] and "4 section" in s["guideline"]["summary"]
    assert s["section"]["summary"] == "Code 36475 is covered; section: Great or Small Saphenous Veins"
    assert s["checklist"]["summary"].startswith("9 requirement(s) under “Great or Small Saphenous Veins”")
    assert s["read"]["summary"] == "9 of 9 requirement(s) answered"
    assert "date(s) verified" in s["verify"]["summary"]
    assert s["decide"]["summary"] == r.reason and s["decide"]["gate"] is None
    assert not any(x["cached"] for x in st["stages"])
    # each model stage links its run log
    assert s["order"]["logs"][0]["file"] == f"data/runs/{r.run_id}/detect_order.json"
    assert [x["logs"][0]["url"].rsplit("/", 1)[1] for x in (s["guideline"], s["checklist"], s["read"])] == \
        ["narrow_guideline", "criteria_guideline", "judge_chart"]
    assert st["order"]["patient_name"] == "Maria Elena Delgado"


def test_cached_run_marks_c_and_h_cached(setup):
    setup()
    r, st, stub = setup(chart_id="delgado2")
    assert stub.calls == ["detect_order", "chart_sections", "judge_chart"]
    s = by_id(st)
    assert s["guideline"]["cached"] and s["checklist"]["cached"]
    assert s["guideline"]["status"] == "done" and s["guideline"]["logs"] == []    # nothing was called, so no log
    assert not s["order"]["cached"] and not s["read"]["cached"]


def test_gate_which_section(setup):
    r, st, stub = setup(order={"target": None})
    assert r.determination == "INSUFFICIENT"
    s = by_id(st)
    assert s["section"]["status"] == "needs_person"
    g = s["section"]["gate"]
    assert g["kind"] == "which_section" and g["blocking"] is True
    assert "Great or Small Saphenous Veins" in g["options"] and g["action"] == {"recheck": {"field": "target"}}
    assert "Which of these" in g["needs"]
    assert [s[x]["status"] for x in ("checklist", "record", "read", "verify")] == ["skipped"] * 4
    assert s["checklist"]["summary"].startswith("Not run:")
    assert s["decide"]["status"] == "needs_person" and s["decide"]["gate"]["kind"] == "review"
    assert st["state"] == "needs_person"
    assert "criteria_guideline" not in stub.calls


def test_gate_confirm_mapped_code(setup, fl_spans, delgado_spans):
    from tests.fake import narrow_answer

    class Mapped(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            if step == "narrow_guideline":
                d = narrow_answer(self.g, self._procedure(prompt))
                row = next(x for x in d["codes"] if x["code"] == "36475")
                d["chosen"]["mapped_cpt"] = {"code": "36475", "refs": row["refs"]}
                self.calls.append(step)
                return schema.model_validate(d)
            return super().__call__(run_id, step, prompt, schema)
    r, st, _ = setup(stub=Mapped(fl_spans, delgado_spans, order={"cpt": ()}))
    s = by_id(st)
    assert s["section"]["status"] == "needs_person"
    assert s["section"]["gate"]["kind"] == "confirm_code" and s["section"]["gate"]["options"] == ["36475"]
    assert s["section"]["gate"]["blocking"] is False
    assert s["read"]["status"] == "done"            # the check went on with the matched code


def test_not_covered_stops_at_the_code(setup):
    r, st, _ = setup(order={"cpt": ("36468",), "target": "spider veins"})
    s = by_id(st)
    assert r.determination == "CANT_CHECK" or r.determination == "NOT_COVERED"
    assert s["section"]["status"] == "done" and [s[x]["status"] for x in ("checklist", "record", "read", "verify")] == ["skipped"] * 4
    assert s["decide"]["gate"]["kind"] == "review"


def test_model_failure_is_a_failed_stage(setup, fl_spans, delgado_spans):
    class Boom(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            if step == "judge_chart":
                raise RuntimeError("judge_chart: model output failed validation twice")
            return super().__call__(run_id, step, prompt, schema)
    err, st, _ = setup(stub=Boom(fl_spans, delgado_spans))
    assert isinstance(err, RuntimeError)
    s = by_id(st)
    assert st["state"] == "failed" and "failed validation twice" in st["error"]
    assert s["read"]["status"] == "failed" and s["read"]["error"].startswith("RuntimeError: judge_chart")
    assert s["read"]["traceback"] and s["read"]["ended_at"]
    assert [s[x]["status"] for x in ("chart", "order", "guideline", "section", "checklist")] == ["done"] * 5
    assert [s[x]["status"] for x in ("verify", "decide")] == ["waiting"] * 2
    # nothing was decided: no result on disk, but the status says where it stopped
    with pytest.raises(FileNotFoundError):
        pipeline.store.load_result("delgado")
    assert status.list_pending()[0]["chart_id"] == "delgado"
    assert status.summary_row(st)["stage"] == "read"


def test_api_runs_in_the_background_and_the_page_can_follow(tmp_store, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    calls: list[str] = []

    class Slow(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            calls.append(step)
            time.sleep(0.05)
            return super().__call__(run_id, step, prompt, schema)
    monkeypatch.setattr(llm, "call", Slow(fl_spans, delgado_spans))
    c = TestClient(main.app)
    with open(SAMPLES / "fl_varicose_veins_guideline.pdf", "rb") as g:
        gid = c.post("/api/guidelines", files={"file": ("fl.pdf", g, "application/pdf")}).json()["id"]
    with open(SAMPLES / "synthetic" / "maria_delgado_chart.pdf", "rb") as f:
        d = c.post("/api/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid}).json()
    assert d["pending"] is True and d["status"]["state"] == "running"
    cid = d["chart_id"]
    # while it runs: the queue lists it as checking, the detail is the status
    seen_running = False
    for _ in range(200):
        st = c.get(f"/api/orders/{cid}/status").json()
        if st["state"] == "running":
            seen_running = True
            det = c.get(f"/api/orders/{cid}").json()      # pending, unless the run ended between the two calls
            assert det["status"]["chart_id"] == cid and (det.get("pending") or det["result"])
        else:
            break
        time.sleep(0.02)
    assert st["state"] == "done", st
    assert seen_running
    rows = c.get("/api/orders").json()
    assert rows[0]["chart_id"] == cid and rows[0]["queue"] == "ready" and rows[0]["status"]["state"] == "done"
    det = c.get(f"/api/orders/{cid}").json()
    assert det["result"]["determination"] == "MET" and det["status"]["state"] == "done"


def test_api_failed_check_is_listed_and_can_be_retried(tmp_store, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    fail = {"on": True}

    class Flaky(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            if step == "detect_order" and fail["on"]:
                raise RuntimeError("the model is down")
            return super().__call__(run_id, step, prompt, schema)
    monkeypatch.setattr(llm, "call", Flaky(fl_spans, delgado_spans))
    c = TestClient(main.app)
    with open(SAMPLES / "fl_varicose_veins_guideline.pdf", "rb") as g:
        gid = c.post("/api/guidelines", files={"file": ("fl.pdf", g, "application/pdf")}).json()["id"]
    with open(SAMPLES / "synthetic" / "maria_delgado_chart.pdf", "rb") as f:
        resp = c.post("/api/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid})
    assert resp.status_code == 500 and "the model is down" in resp.json()["detail"]
    rows = c.get("/api/orders").json()
    assert len(rows) == 1 and rows[0]["queue"] == "failed" and rows[0]["status"]["stage"] == "order"
    cid = rows[0]["chart_id"]
    det = c.get(f"/api/orders/{cid}").json()
    assert det["pending"] and det["status"]["state"] == "failed" and det["result"] is None
    fail["on"] = False
    d = c.post(f"/api/orders/{cid}/retry").json()
    assert d["result"]["determination"] == "MET" and d["status"]["state"] == "done"
    assert c.get("/api/orders").json()[0]["queue"] == "ready"


def test_each_stage_says_what_it_is_doing_then_clears_it(setup, fl_spans, delgado_spans, monkeypatch):
    """`doing` as the page polls it: read from status.json while each model step is in its call (a stub hook) and
    while J verifies, and empty on every stage once the check is done. Coordinator words only."""
    from app.evidence import judge
    seen: dict[str, str] = {}
    inner = Stub(fl_spans, delgado_spans)
    verify = judge.verify

    def spy(*a, **k):
        cur = status.load_status("delgado")
        seen["verify"] = by_id(cur)[cur["current"]]["doing"]
        return verify(*a, **k)
    monkeypatch.setattr(judge, "verify", spy)

    def hook(run_id, step, prompt, schema, **k):
        cur = status.load_status("delgado")
        if cur and cur.get("current"):
            seen[step] = by_id(cur)[cur["current"]]["doing"]
        return inner(run_id, step, prompt, schema, **k)

    r, st, _ = setup(stub=hook)
    assert r.determination == "MET"
    assert seen["criteria_guideline"] == "Building the checklist from the whole guideline"
    assert seen["criteria_audit"] == "Checking for gaps (9 conditions)"
    assert seen["verify"] == "Checking quotes and dates"
    assert seen["chart_sections"] == f"Reading {len({s.page for s in delgado_spans})} pages of the case"
    assert seen["judge_chart"].startswith("Checking 9 requirements against ") and seen["judge_chart"].endswith(" lines of the record")
    assert all(not x.get("doing") for x in st["stages"])
    words = " ".join(seen.values()).lower()
    assert not any(w in words for w in ("criterion", "criteria", "verdict", "span"))
