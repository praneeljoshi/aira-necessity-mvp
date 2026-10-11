"""The pause at the section gate and the resume from a person's picks (pipeline.run(pause_at_pathways=True),
pipeline.resume). Offline: stub model, store in tmp_path. The stub answers criteria for the pathways the prompt asks
for, so a different pick is tested at the data level (selection, confirmation, status), not by the checklist content."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline
from app.checklist import keys
from app.core import llm, status, store
from app.core.models import Selection
from tests.conftest import SAMPLES
from tests.fake import Stub

GSV = {"code": "36475", "pathway": "gsv"}


@pytest.fixture
def world(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    class W:
        guideline, sha256, client = gid, sha, TestClient(main.app)

        @staticmethod
        def model(stub=None, **kw):
            """Puts a stub in place of the model (writing run logs the way llm.call does) and returns it."""
            stub = stub or Stub(fl_spans, delgado_spans, **kw)

            def call(run_id, step, prompt, schema, **k):
                out = stub(run_id, step, prompt, schema, **k)
                llm._log(run_id, step, {"step": step, "model": "stub", "parsed": out.model_dump()})
                return out
            monkeypatch.setattr(llm, "call", call)
            return stub

        @staticmethod
        def start(chart_id, override=None, pause=True, **kw):
            stub = W.model(**kw)
            r = pipeline.run("", chart_id, gid, rspans=delgado_spans, override=override, pause_at_pathways=pause)
            return r, stub

        @staticmethod
        def resume(chart_id, picks, by=None, **kw):
            stub = W.model(**kw)
            return pipeline.resume(chart_id, picks, by=by), stub

        @staticmethod
        def stages(chart_id):
            return {s["id"]: s for s in status.load_status(chart_id)["stages"]}
    return W


def test_pause_at_the_section_gate(world):
    r, stub = world.start("c1")
    assert r is None
    assert stub.calls == ["detect_order", "narrow_guideline"]
    st = status.load_status("c1")
    assert st["state"] == "paused" and st["ended_at"] and st["current"] is None and st["run_id"]
    key = keys.cache_key(world.sha256, store.load_order("c1").procedure)
    assert st["resume"] == {"stage": "checklist", "needs": "pathways", "key": key, "endpoint": "/api/review/c1/pathways"}
    s = world.stages("c1")
    assert [s[x]["status"] for x in ("chart", "order", "guideline")] == ["done"] * 3
    assert s["section"]["status"] == "needs_person" and s["section"]["ended_at"]
    g = s["section"]["gate"]
    assert g["kind"] == "confirm_pathways" and g["blocking"] is True and g["title"] == "Confirm the indication of the guideline"
    assert g["options"] == ["Great or Small Saphenous Veins"]
    assert g["action"] == {"confirm": {"endpoint": "/api/review/c1/pathways"}}
    assert g["needs"] == "Confirm which indication of the guideline this order is checked under."
    assert [s[x]["status"] for x in ("checklist", "record", "read", "verify", "decide")] == ["waiting"] * 5
    # the section stage's output is on disk, nothing is decided
    sel = Selection.model_validate_json((store.RESULTS / "c1" / "selection.json").read_text())
    assert [p.model_dump() for p in sel.pathways] == [{**GSV, "how": "code"}]
    assert not (store.RESULTS / "c1" / "result.json").exists()
    assert store.load_confirmation("c1") is None
    with pytest.raises(FileNotFoundError):
        store.load_result("c1")
    # the queue lists it as waiting for a person; the detail is the pending status
    assert status.summary_row(st) == {**status.summary_row(st), "state": "paused", "stage": "section"}
    rows = world.client.get("/api/orders").json()
    assert [(x["chart_id"], x["queue"]) for x in rows] == [("c1", "paused")]
    assert rows[0]["status"]["state"] == "paused" and rows[0]["status"]["stage"] == "section"
    assert rows[0]["patient_name"] == "Maria Elena Delgado"
    det = world.client.get("/api/orders/c1").json()
    assert det["pending"] is True and det["status"]["state"] == "paused" and det["result"] is None
    # retry refuses a paused check; the review endpoint owns the answer
    resp = world.client.post("/api/orders/c1/retry")
    assert resp.status_code == 409 and "confirm the indication" in resp.json()["detail"]


def test_start_passes_the_pause_through(world, delgado_spans):
    world.model()
    out = main._start("c2", "", world.guideline, "delgado.pdf", rspans=delgado_spans, pause_at_pathways=True)
    assert out["pending"] is True and out["status"]["state"] == "paused" and out["chart_id"] == "c2"
    assert world.client.get("/api/orders").json()[0]["queue"] == "paused"


def test_resume_with_the_suggested_section(world):
    world.start("c1")
    run_id = status.load_status("c1")["run_id"]
    r, stub = world.resume("c1", [GSV], by="Dana")
    assert stub.calls == ["criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"]          # A-C are not run again
    assert r.determination == "MET" and r.queue == "ready" and r.pathway_used == ["gsv"] and r.run_id == run_id
    assert store.load_result("c1")["result"]["determination"] == "MET"
    # the confirmation record
    conf = store.load_confirmation("c1")
    assert set(conf) == {"chart_id", "run_id", "guideline_id", "guideline_sha", "narrowed_key", "suggested", "confirmed",
                         "by", "at", "h_key"}
    assert conf["chart_id"] == "c1" and conf["run_id"] == run_id and conf["guideline_id"] == world.guideline
    assert conf["guideline_sha"] == world.sha256 and conf["narrowed_key"] == keys.cache_key(world.sha256, store.load_order("c1").procedure)
    assert conf["suggested"] == [GSV] and conf["confirmed"] == [GSV] and conf["by"] == "Dana" and conf["at"]
    n = store.load_criteria(conf["narrowed_key"])[0]
    assert conf["h_key"] == keys.h_cache_key(world.sha256, n, ["gsv"], store.load_order("c1").procedure)
    assert conf["h_key"].startswith(f"h-{world.sha256[:16]}-gsv-") and len(conf["h_key"].split("-")[3]) == 8
    assert conf["h_key"].endswith(f"-mm-v{keys.prompt_version(with_c=False)}")      # the model ("m") and the prompts
    assert store.load_hcache(conf["h_key"]).expressions[0].pathway == "gsv"
    assert store.load_criteria(conf["h_key"])[0] is None                  # the H-only file has no narrowed
    assert json.loads((store.CRITERIA / f"{conf['h_key']}.json").read_text())["narrowed"] is None
    # the status: the gate answered, the same run, every stage done
    st = status.load_status("c1")
    assert st["state"] == "done" and st["run_id"] == run_id and st["resume"] is None and st["resumed_at"]
    s = world.stages("c1")
    assert s["section"]["status"] == "done" and s["section"]["gate"]["kind"] == "confirm_pathways"
    assert s["section"]["gate"]["answered"] is True
    ab = s["section"]["answered_by"]
    assert ab["by"] == "Dana" and ab["at"] and ab["confirmed"] == [GSV] and ab["suggested"] == [GSV]
    assert [s[x]["status"] for x in ("checklist", "record", "read", "verify", "decide")] == ["done"] * 5
    assert s["checklist"]["cached"] is False
    assert s["checklist"]["logs"][0]["url"].endswith(f"/api/runs/{run_id}/criteria_guideline")
    assert s["order"]["logs"][0]["url"].endswith(f"/api/runs/{run_id}/detect_order")   # kept from before the pause
    sel = Selection.model_validate(store.load_result("c1")["selection"])
    assert [p.model_dump() for p in sel.pathways] == [{**GSV, "how": "code"}] and sel.candidates == {}
    assert not any("chosen by a person" in x for x in sel.reasons)
    assert world.client.get("/api/orders").json()[0]["queue"] == "ready"


def test_resume_with_a_different_section(world):
    world.start("c1")
    r, stub = world.resume("c1", [{"code": "36475", "pathway": "accessory"}], by="Dana")
    assert stub.calls[0] == "criteria_guideline" and "detect_order" not in stub.calls and "narrow_guideline" not in stub.calls
    conf = store.load_confirmation("c1")
    assert conf["suggested"] == [GSV] and conf["confirmed"] == [{"code": "36475", "pathway": "accessory"}]
    n = store.load_criteria(conf["narrowed_key"])[0]
    assert conf["h_key"] == keys.h_cache_key(world.sha256, n, ["accessory"], store.load_order("c1").procedure) != keys.h_cache_key(world.sha256, n, ["gsv"], store.load_order("c1").procedure)
    sel = Selection.model_validate(store.load_result("c1")["selection"])
    assert [(p.code, p.pathway, p.how) for p in sel.pathways] == [("36475", "accessory", "code")]
    acc = next(p for p in n.pathways if p.id == "accessory")
    assert [(x.first, x.last) for x in sel.ranges] == [(x.first, x.last) for x in acc.spans]
    assert any(x.startswith("The indication was chosen by Dana: “Accessory Saphenous Veins” (the guideline reader suggested "
                            "“Great or Small Saphenous Veins”)") for x in sel.reasons)
    assert r.review_reasons and any("chosen by Dana" in x for x in r.review_reasons) and r.queue == "review"
    s = world.stages("c1")
    assert s["section"]["answered_by"]["confirmed"] == conf["confirmed"] and status.load_status("c1")["state"] in ("done", "needs_person")


def test_two_codes_pick_one_then_the_section(world):
    # one code, one pathway: 2+ codes pause at pick_code before C; the picked code alone goes on to the section gate.
    # 36478 is not written in the Delgado chart, so the order step would drop it: the second code comes as an override
    from app.understand import onecode
    r, stub = world.start("c1", override={"cpt": ["36475", "36478"]})
    assert r is None and stub.calls == ["detect_order"]
    st = status.load_status("c1")
    assert st["state"] == "paused" and st["resume"] == {"stage": "guideline", "needs": "code",
                                                        "endpoint": "/api/review/c1/code"}
    s = world.stages("c1")
    assert s["order"]["gate"]["kind"] == "pick_code" and s["order"]["gate"]["options"] == ["36475", "36478"]
    assert s["guideline"]["status"] == "waiting"
    stub = world.model()
    assert onecode.pick("c1", "36478", by="Dana") is None
    assert stub.calls == ["narrow_guideline"]
    assert Stub._procedure(stub.prompts[0][1])["cpt"] == ["36478"]          # C's request carries the one code
    s = world.stages("c1")
    assert s["order"]["answered_by"]["confirmed"] == ["36478"] and s["order"]["answered_by"]["by"] == "Dana"
    assert s["section"]["gate"]["kind"] == "confirm_pathways"
    sel0 = Selection.model_validate_json((store.RESULTS / "c1" / "selection.json").read_text())
    assert [g.code for g in sel0.code_gate] == ["36478"]
    r, stub = world.resume("c1", [{"code": "36478", "pathway": "gsv"}], by="Dana")
    assert r.determination == "MET" and r.pathway_used == ["gsv"]
    assert store.load_result("c1")["meta"]["override"]["cpt"] == ["36478"]
    assert [c["code"] for c in store.load_result("c1")["selection"]["code_gate"]] == ["36478"]


def test_none_chosen_by_the_model(world):
    r, stub = world.start("c1", order={"target": None})
    assert r is None and stub.calls == ["detect_order", "narrow_guideline"]
    s = world.stages("c1")
    g = s["section"]["gate"]
    assert g["kind"] == "confirm_pathways" and g["options"] == []
    assert g["needs"].endswith("The guideline reader chose none; pick one.")
    sel0 = Selection.model_validate_json((store.RESULTS / "c1" / "selection.json").read_text())
    assert sel0.pathways == [] and "36475" in sel0.candidates
    assert any(x.startswith("Which indication covers CPT 36475") for x in sel0.reasons)
    r, stub = world.resume("c1", [GSV], by="Dana")
    assert stub.calls == ["criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"]
    assert r.determination == "MET" and r.pathway_used == ["gsv"]
    conf = store.load_confirmation("c1")
    assert conf["suggested"] == [] and conf["confirmed"] == [GSV]
    sel = Selection.model_validate(store.load_result("c1")["selection"])
    assert not any(x.startswith("Which indication covers CPT") for x in sel.reasons)
    assert any(x == "The indication was chosen by Dana: “Great or Small Saphenous Veins” (the guideline reader suggested nothing)."
               for x in sel.reasons)
    assert world.stages("c1")["section"]["answered_by"]["suggested"] == []


def test_h_is_cached_by_the_confirmed_section(world):
    world.start("c1")
    world.resume("c1", [GSV], by="Dana")
    k1 = store.load_confirmation("c1")["h_key"]
    r, stub = world.start("c2")
    assert r is None and stub.calls == ["detect_order"]            # C is cached by the order
    r, stub = world.resume("c2", [GSV], by="Lee")
    assert stub.calls == ["chart_sections", "judge_chart"]                          # H is cached by the confirmed section
    assert r.determination == "MET"
    assert store.load_confirmation("c2")["h_key"] == k1
    s = world.stages("c2")
    assert s["checklist"]["cached"] is True and s["checklist"]["status"] == "done" and s["checklist"]["logs"] == []
    assert s["read"]["cached"] is False


def test_a_stopped_code_does_not_pause(world):
    r, stub = world.start("c1", override={"cpt": ["36468"], "target": "spider veins"})
    assert r is not None and r.determination == "NOT_COVERED" and r.queue == "cant_check"
    assert stub.calls == ["detect_order", "narrow_guideline"]
    st = status.load_status("c1")
    assert st["state"] == "needs_person" and st["resume"] is None
    s = world.stages("c1")
    assert s["section"]["status"] == "done" and s["section"]["gate"] is None
    assert [s[x]["status"] for x in ("checklist", "record", "read", "verify")] == ["skipped"] * 4
    assert s["decide"]["gate"]["kind"] == "review"
    assert (store.RESULTS / "c1" / "result.json").exists() and store.load_confirmation("c1") is None
    assert world.client.get("/api/orders").json()[0]["queue"] == "cant_check"
    with pytest.raises(ValueError, match="not paused"):
        pipeline.resume("c1", [GSV])


def test_without_the_flag_nothing_changes(world):
    r, stub = world.start("c1", pause=False)
    assert r.determination == "MET" and stub.calls == ["detect_order", "narrow_guideline", "criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"]
    assert status.load_status("c1")["state"] == "done" and status.load_status("c1")["resume"] is None
    r, stub = world.start("c2", pause=False, order={"target": None})
    assert r.determination == "INSUFFICIENT" and world.stages("c2")["section"]["gate"]["kind"] == "which_section"


def test_resume_refuses_what_is_not_paused(world):
    world.start("c1", pause=False)
    with pytest.raises(ValueError, match="not paused"):
        pipeline.resume("c1", [GSV])
    with pytest.raises(ValueError, match="not paused"):
        pipeline.resume("nobody", [GSV])
    world.start("c3")
    world.resume("c3", [GSV])
    with pytest.raises(ValueError, match="not paused"):                 # answered already, and done
        pipeline.resume("c3", [GSV])


def test_bad_picks_raise_and_leave_the_pause(world):
    world.start("c1")
    with pytest.raises(ValueError, match="pick at least one section"):
        pipeline.resume("c1", [])
    with pytest.raises(ValueError, match="unknown section\\(s\\): nope"):
        pipeline.resume("c1", [{"code": "36475", "pathway": "nope"}])
    with pytest.raises(ValueError, match="code\\(s\\) not in this order: 99999"):
        pipeline.resume("c1", [{"code": "99999", "pathway": "gsv"}])
    with pytest.raises(ValueError, match="unknown section\\(s\\): nope; code\\(s\\) not in this order: 99999"):
        pipeline.resume("c1", [{"code": "99999", "pathway": "nope"}])
    st = status.load_status("c1")
    assert st["state"] == "paused" and st["resume"]["stage"] == "checklist"
    assert store.load_confirmation("c1") is None and not (store.RESULTS / "c1" / "result.json").exists()


def test_a_failed_resume_is_retried_from_the_stored_picks(world, fl_spans, delgado_spans):
    world.start("c1")
    run_id = status.load_status("c1")["run_id"]

    class Boom(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            if step == "judge_chart":
                raise RuntimeError("judge_chart: the model is down")
            return super().__call__(run_id, step, prompt, schema)
    with pytest.raises(RuntimeError, match="the model is down"):
        world.resume("c1", [GSV], by="Dana", stub=Boom(fl_spans, delgado_spans))
    st = status.load_status("c1")
    assert st["state"] == "failed" and st["run_id"] == run_id
    s = world.stages("c1")
    assert s["read"]["status"] == "failed" and s["section"]["answered_by"]["by"] == "Dana"
    assert store.load_confirmation("c1")["confirmed"] == [GSV] and not (store.RESULTS / "c1" / "result.json").exists()
    assert world.client.get("/api/orders").json()[0]["queue"] == "failed"
    # retry: no picks given, the stored confirmation drives it; H is already cached, only the chart is read again
    r, stub = world.resume("c1", None)
    assert stub.calls == ["judge_chart"] and r.determination == "MET" and r.run_id == run_id   # A2 cached per chart
    st = status.load_status("c1")
    assert st["state"] == "done" and st["error"] is None and st["run_id"] == run_id
    s = world.stages("c1")
    assert s["read"]["status"] == "done" and s["read"]["error"] is None and s["checklist"]["cached"] is True
    assert s["section"]["answered_by"]["by"] == "Dana"
    assert store.load_confirmation("c1")["by"] == "Dana"


def test_from_doc_restores_the_recorder(world):
    world.start("c1")
    doc = status.load_status("c1")
    rec = status.Recorder.from_doc(doc, persist=False)
    assert rec.chart_id == "c1" and rec.doc is doc and rec.state == "paused"
    assert rec.steps == {"order": "detect_order", "guideline": "narrow_guideline"}
