"""The coordinator review flow end to end, through the API: upload pauses at the indication gate, a person confirms
the section, the check finishes into the case (the guideline with the chart's evidence attached to each
requirement), feedback is filed on guideline lines and on evidence quotes. Offline: the stub model
(tests/fake.Stub), the store and the feedback folder in tmp_path. Never touches data/."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline
from app.core import llm, store
from app.review import feedback
from tests.conftest import SAMPLES
from tests.fake import Stub

GSV = {"code": "36475", "pathway": "gsv"}
CHART = SAMPLES / "synthetic" / "maria_delgado_chart.pdf"
GL_KINDS = ("should_be_requirement", "not_a_requirement", "logic_wrong", "edit")
EV_KINDS = ("wrong_evidence", "evidence_elsewhere", "is_evidence")       # on an evidence quote; is_evidence kept for older pages
KINDS = GL_KINDS + EV_KINDS
ITEM_FIELDS = {"id", "chart_id", "kind", "side", "text", "proposal", "spans", "requirements", "guideline_id",
               "guideline_sha", "pathway", "h_key", "run_id", "by", "at"}


@pytest.fixture
def world(tmp_store, tmp_path, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    monkeypatch.setattr(feedback, "FEEDBACK", tmp_path / "feedback")
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    c = TestClient(main.app)

    class W:
        client, guideline, sha256 = c, gid, sha

        @staticmethod
        def stub(**kw) -> Stub:
            s = Stub(fl_spans, delgado_spans, **kw)

            def call(run_id, step, prompt, schema, **k):     # the stub, logging the run the way llm.call does
                out = s(run_id, step, prompt, schema, **k)
                llm._log(run_id, step, {"step": step, "model": "stub", "parsed": out.model_dump()})
                return out
            monkeypatch.setattr(llm, "call", call)
            return s

        @staticmethod
        def upload(**kw):
            """Upload the Delgado chart through the review flow; returns (chart_id, stub)."""
            s = W.stub(**kw)
            with open(CHART, "rb") as f:
                r = c.post("/api/review/charts", files={"file": ("delgado.pdf", f, "application/pdf")},
                           data={"guideline_id": gid})
            assert r.status_code == 200, r.text
            return r.json()["chart_id"], s

        @staticmethod
        def doc(cid: str) -> dict:
            r = c.get(f"/api/review/{cid}")
            assert r.status_code == 200, r.text
            return r.json()

        @staticmethod
        def confirm(cid: str, picks: list[dict], by: str | None = "Dana", expect: int = 200) -> dict:
            body = {"picks": picks}
            if by:
                body["by"] = by
            r = c.post(f"/api/review/{cid}/pathways", json=body)
            assert r.status_code == expect, r.text
            return r.json()

    return W


def stages(doc: dict) -> dict:
    return {s["id"]: s for s in doc["status"]["stages"]}


def keep_codes(monkeypatch, codes: list[str]) -> None:
    """The Delgado chart only prints 36475, and detect_order drops codes not written in the chart; for the
    two-code and the stopped-code cases, put the stub's codes back after detection."""
    real = pipeline.detect_order

    def detect(rspans, chart_id, run_id):
        o = real(rspans, chart_id, run_id)
        o.procedure.cpt = list(codes)
        return o
    monkeypatch.setattr(pipeline, "detect_order", detect)


# ---------------------------------------------------------------- the pause


def test_upload_pauses_at_the_pathway_gate(world):
    cid, stub = world.upload()
    d = world.doc(cid)
    assert d["chart_id"] == cid and d["state"] == "paused"
    assert d["case"] is None and d["confirmation"] is None and d["feedback"] == []
    assert d["order"]["patient_name"] == "Maria Elena Delgado" and d["order"]["cpt"] == ["36475"]
    assert d["guideline"]["id"] == world.guideline and d["guideline"]["sha"] == world.sha256
    # the status: the section stage stopped at the gate, nothing after it ran
    st = d["status"]
    assert st["state"] == "paused" and st["resume"]["stage"] == "checklist" and st["resume"]["needs"] == "pathways"
    assert st["resume"]["endpoint"] == f"/api/review/{cid}/pathways" and st["resume"]["key"]
    s = stages(d)
    assert s["section"]["status"] == "needs_person"
    g = s["section"]["gate"]
    assert g["kind"] == "confirm_pathways" and g["blocking"] is True
    assert g["options"] == ["Great or Small Saphenous Veins"]
    assert g["action"] == {"confirm": {"endpoint": f"/api/review/{cid}/pathways"}}
    assert "Confirm which indication" in g["needs"]
    assert [s[x]["status"] for x in ("checklist", "record", "read", "verify", "decide")] == ["waiting"] * 5
    assert stub.calls == ["detect_order", "narrow_guideline"]
    # on disk: the selection, no result
    assert (store.RESULTS / cid / "selection.json").exists()
    assert not (store.RESULTS / cid / "result.json").exists()
    # the gate document
    gate = d["gate"]
    assert gate["none_chosen"] is False and gate["suggested"] == [GSV]
    assert gate["order"]["cpt"] == ["36475"] and gate["order"]["target"] == "left great saphenous vein"
    assert gate["order"]["lines"] and all(x["id"].startswith("r") and x["text"] for x in gate["order"]["lines"])
    assert len(gate["pathways"]) == 4
    for p in gate["pathways"]:
        assert {"id", "name", "codes", "targets", "suggested", "for_codes", "pages", "lines", "n_lines"} <= set(p), p["id"]
        assert p["name"] and p["lines"] and p["n_lines"] >= len(p["lines"])
        assert all({"id", "text", "page", "blank_before"} <= set(ln) for ln in p["lines"])
    byid = {p["id"]: p for p in gate["pathways"]}
    assert byid["gsv"]["suggested"] is True and byid["gsv"]["name"] == "Great or Small Saphenous Veins"
    assert "36475" in byid["gsv"]["codes"] and byid["gsv"]["for_codes"] == ["36475"]
    assert byid["gsv"]["targets"] == ["great saphenous vein", "small saphenous vein"]
    assert byid["accessory"]["suggested"] is False and byid["tributaries"]["for_codes"] == []
    assert [x["code"] for x in gate["codes"]] == ["36475"] and gate["codes"][0]["outcome"] == "judge"
    assert gate["codes"][0]["lines"] and gate["stopped"] == []
    # the queue lists it as waiting for a person
    rows = world.client.get("/api/orders").json()
    assert [x["queue"] for x in rows if x["chart_id"] == cid] == ["paused"]
    assert rows[0]["status"]["state"] == "paused" and rows[0]["status"]["stage"] == "section"
    # a paused check cannot be retried the old way
    assert world.client.post(f"/api/orders/{cid}/retry").status_code == 409


def test_confirming_the_suggested_section_finishes_the_check(world, delgado_spans):
    cid, stub = world.upload()
    run_id = world.doc(cid)["status"]["run_id"]
    before = len(stub.calls)
    # bad picks first: wrong pathway / wrong code / nothing
    assert world.confirm(cid, [{"code": "36475", "pathway": "nope"}], expect=400)
    assert world.confirm(cid, [{"code": "99999", "pathway": "gsv"}], expect=400)
    assert world.confirm(cid, [], expect=400)
    assert stub.calls[before:] == []
    out = world.confirm(cid, [GSV])
    assert out["chart_id"] == cid and not out.get("pending")
    assert stub.calls[before:] == ["criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"]        # A-C are not run again
    d = world.doc(cid)
    assert d["state"] == "done" and d["status"]["state"] == "done" and d["status"]["run_id"] == run_id
    assert d["status"]["resume"] is None and d["status"]["resumed_at"]
    s = stages(d)
    assert s["section"]["status"] == "done" and s["section"]["gate"]["answered"] is True
    ab = s["section"]["answered_by"]
    assert ab["by"] == "Dana" and ab["at"] and ab["confirmed"] == [GSV] and ab["suggested"] == [GSV]
    assert [s[x]["status"] for x in ("checklist", "record", "read", "verify", "decide")] == ["done"] * 5
    assert s["checklist"]["cached"] is False
    # the confirmation record
    conf = d["confirmation"]
    assert conf["chart_id"] == cid and conf["run_id"] == run_id and conf["guideline_id"] == world.guideline
    assert conf["guideline_sha"] == world.sha256 and conf["suggested"] == [GSV] and conf["confirmed"] == [GSV]
    assert conf["by"] == "Dana" and conf["at"] and conf["h_key"] and conf["narrowed_key"]
    assert (store.RESULTS / cid / "pathways.json").exists() and (store.RESULTS / cid / "result.json").exists()
    assert (store.CRITERIA / f"{conf['h_key']}.json").exists()
    # the case
    case = d["case"]
    assert case["result"]["determination"] == "MET" and case["result"]["pathway_used"] == ["gsv"]
    assert case["result"]["queue"] == "ready" and case["result"]["guideline_title"] == "fl.pdf"
    assert case["h_key"] == conf["h_key"] and case["confirmation"]["confirmed"] == [GSV]
    assert case["tree"]["sections"] and case["tree"]["sections"][0]["label"] == "Great or Small Saphenous Veins"
    reqs = case["requirements"]
    assert len(reqs) == 9 and [r["criterion"] for r in reqs][:3] == ["reflux", "ceap", "size"]   # guideline order
    for r in reqs:
        assert {"criterion", "words", "mark", "say", "bad", "role", "block", "refs", "highlights", "evidence"} <= set(r)
        assert r["refs"] and all(x.startswith("g") for x in r["refs"])
        assert r["highlights"] and all(h["id"].startswith("g") and 0 <= h["start"] < h["end"] for h in r["highlights"])
        assert r["words"]
    met = [r for r in reqs if r["mark"] == "documented"]
    assert len(met) == 6 and all(r["say"] == "Documented" and r["bad"] is False for r in met)
    for r in met:
        assert r["evidence"] and all(e["side"] == "for" and e["lines"] and e["text"] for e in r["evidence"])
        assert all({"span", "side", "lines", "text", "date", "heading", "page"} <= set(e) for e in r["evidence"])
    other = [r for r in reqs if r["criterion"] in ("ulcer", "thromb", "hem")]
    assert all(r["mark"] in ("not_needed", "other_option") for r in other)     # the other branch is documented
    assert all(e["side"] == "against" for r in other for e in r["evidence"])
    # the chart appears only as evidence: its name and page count, and the quotes under each requirement
    chart = case["chart"]
    assert chart == {"filename": "delgado.pdf", "pages": len({s.page for s in delgado_spans})}
    rt = {s.id: s for s in delgado_spans}
    cited = {r["criterion"] for r in reqs if r["evidence"]}
    assert cited >= {"reflux", "ceap", "size", "compression"}
    assert {e["side"] for r in reqs for e in r["evidence"]} == {"for", "against"}
    for r in reqs:
        for e in r["evidence"]:
            assert all(i in rt for i in e["lines"]) and e["page"] == rt[e["lines"][0]].page
            assert e["text"].split()[0] in rt[e["lines"][0]].text
    # the old detail still works and agrees; a second confirmation is refused
    assert world.client.get(f"/api/orders/{cid}").json()["result"]["determination"] == "MET"
    assert world.client.get("/api/orders").json()[0]["queue"] == "ready"
    world.confirm(cid, [GSV], expect=409)


def test_a_different_section_than_suggested(world):
    cid, stub = world.upload()
    before = len(stub.calls)
    world.confirm(cid, [{"code": "36475", "pathway": "accessory"}], by="Lee")
    assert stub.calls[before:] == ["criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"]
    d = world.doc(cid)
    assert d["state"] == "done"
    res = d["case"]["result"]
    assert res["pathway_used"] == ["accessory"] and res["determination"] == "INSUFFICIENT"
    assert any("chosen by Lee" in x for x in res["review_reasons"])
    conf = d["confirmation"]
    assert conf["suggested"] == [GSV] and conf["confirmed"] == [{"code": "36475", "pathway": "accessory"}]
    assert conf["suggested"] != conf["confirmed"] and conf["by"] == "Lee"
    reqs = d["case"]["requirements"]
    assert [r["criterion"] for r in reqs] == ["accessory_1", "accessory_2"]
    assert all(r["mark"] == "missing" and r["evidence"] == [] for r in reqs)
    assert d["case"]["tree"]["sections"][0]["label"] == "Accessory Saphenous Veins"
    s = stages(d)
    assert s["section"]["answered_by"]["confirmed"] == conf["confirmed"]


def test_two_codes_two_picks(world, monkeypatch):
    keep_codes(monkeypatch, ["36475", "36478"])
    # one code, one pathway: two codes stop at pick_code first; one picked, the section gate is that code's alone
    cid, stub = world.upload(order={"cpt": ("36475", "36478")})
    d = world.doc(cid)
    assert d["state"] == "paused" and d["gate"]["kind"] == "pick_code" and d["order"]["cpt"] == ["36475", "36478"]
    r = world.client.post(f"/api/review/{cid}/code", json={"code": "36478", "by": "Dana"})
    assert r.status_code == 200, r.text
    d = world.doc(cid)
    picks = [{"code": "36478", "pathway": "gsv"}]
    assert d["state"] == "paused" and d["gate"]["suggested"] == picks and d["order"]["cpt"] == ["36478"]
    assert [x["code"] for x in d["gate"]["codes"]] == ["36478"]
    byid = {p["id"]: p for p in d["gate"]["pathways"]}
    assert byid["gsv"]["for_codes"] == ["36478"] and byid["perforator"]["for_codes"] == ["36478"]
    assert byid["tributaries"]["for_codes"] == []
    world.confirm(cid, picks)
    d = world.doc(cid)
    assert d["state"] == "done" and d["case"]["result"]["determination"] == "MET"
    assert d["confirmation"]["confirmed"] == picks and d["confirmation"]["suggested"] == picks
    assert len(d["case"]["requirements"]) == 9 and d["code"] == d["case"]["code"] == "36478"


def test_one_code_two_sections(world):
    cid, stub = world.upload(order={"target": "left great saphenous vein and perforator veins"})
    d = world.doc(cid)
    picks = [{"code": "36475", "pathway": "gsv"}, {"code": "36475", "pathway": "perforator"}]
    assert d["state"] == "paused" and d["gate"]["suggested"] == picks
    assert stages(d)["section"]["gate"]["options"] == ["Great or Small Saphenous Veins", "Perforator Veins"]
    before = len(stub.calls)
    world.confirm(cid, picks)
    assert stub.calls[before:] == ["criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"]
    d = world.doc(cid)
    res = d["case"]["result"]
    assert sorted(res["pathway_used"]) == ["gsv", "perforator"] and res["determination"] == "INSUFFICIENT"
    ids = [r["criterion"] for r in d["case"]["requirements"]]
    assert len(ids) == 11 and {"perforator_1", "perforator_2"} <= set(ids)
    assert sorted(e.pathway for e in store.load_criteria(d["confirmation"]["h_key"])[1].expressions) == ["gsv", "perforator"]


def test_model_chose_nothing_a_person_picks(world):
    cid, stub = world.upload(order={"target": None})
    d = world.doc(cid)
    assert d["state"] == "paused"
    gate = d["gate"]
    assert gate["none_chosen"] is True and gate["suggested"] == []
    assert all(p["suggested"] is False for p in gate["pathways"])
    g = stages(d)["section"]["gate"]
    assert g["kind"] == "confirm_pathways" and g["options"] == [] and "pick one" in g["needs"]
    assert stub.calls == ["detect_order", "narrow_guideline"]
    world.confirm(cid, [GSV], by=None)
    d = world.doc(cid)
    assert d["state"] == "done" and d["case"]["result"]["determination"] == "MET"
    assert d["confirmation"]["suggested"] == [] and d["confirmation"]["confirmed"] == [GSV] and d["confirmation"]["by"] is None
    assert any("chosen by a person" in x for x in d["case"]["result"]["review_reasons"])


def test_checklist_is_cached_by_the_confirmed_section(world):
    cid1, _ = world.upload()
    world.confirm(cid1, [GSV])
    key = world.doc(cid1)["confirmation"]["h_key"]
    cid2, stub2 = world.upload()
    assert world.doc(cid2)["state"] == "paused"
    world.confirm(cid2, [GSV])
    assert "criteria_guideline" not in stub2.calls and stub2.calls == ["detect_order", "chart_sections", "judge_chart"]
    d = world.doc(cid2)
    assert d["state"] == "done" and d["case"]["result"]["determination"] == "MET"
    assert stages(d)["checklist"]["cached"] is True and stages(d)["checklist"]["status"] == "done"
    assert d["confirmation"]["h_key"] == key and d["case"]["h_key"] == key
    # a different section builds its own checklist under its own key
    cid3, stub3 = world.upload()
    world.confirm(cid3, [{"code": "36475", "pathway": "accessory"}])
    assert "criteria_guideline" in stub3.calls
    assert world.doc(cid3)["confirmation"]["h_key"] != key


def test_a_stopped_code_does_not_pause(world, monkeypatch):
    keep_codes(monkeypatch, ["36468"])
    cid, stub = world.upload(order={"cpt": ("36468",), "target": "spider veins"})
    d = world.doc(cid)
    assert d["state"] == "done" and d["gate"] is None and d["confirmation"] is None
    assert stub.calls == ["detect_order", "narrow_guideline"]
    res = d["case"]["result"]
    assert res["determination"] == "NOT_COVERED" and res["pathway_used"] == []
    assert d["case"]["tree"]["codes"][0]["code"] == "36468" and not d["case"]["tree"]["sections"]
    assert d["case"]["requirements"] == []
    assert stages(d)["section"]["status"] == "done" and stages(d)["checklist"]["status"] == "skipped"
    assert world.client.get("/api/orders").json()[0]["queue"] == res["queue"] != "ready"


def test_running_and_failed_states_and_unknown_ids(world, monkeypatch):
    c = world.client
    assert c.get("/api/review/nope").status_code == 404
    assert c.get("/api/review/nope").json() == {"detail": "No case with this id"}
    assert c.post("/api/review/nope/pathways", json={"picks": [GSV]}).status_code == 404
    # a failure before the gate: state failed, no gate, no case
    class Boom(Stub):
        def __call__(self, run_id, step, prompt, schema, **_):
            if step == "narrow_guideline":
                raise RuntimeError("the model is down")
            return super().__call__(run_id, step, prompt, schema)
    base = world.stub()
    monkeypatch.setattr(llm, "call", Boom(base.g, base.r))
    with open(CHART, "rb") as f:
        r = c.post("/api/review/charts", files={"file": ("delgado.pdf", f, "application/pdf")},
                   data={"guideline_id": world.guideline})
    assert r.status_code == 500
    cid = [x for x in c.get("/api/orders").json() if x["queue"] == "failed"][0]["chart_id"]
    d = world.doc(cid)
    assert d["state"] == "failed" and d["case"] is None and "the model is down" in d["status"]["error"]
    # confirming a check that is not paused is refused
    assert c.post(f"/api/review/{cid}/pathways", json={"picks": [GSV]}).status_code == 409
    # retry starts over and pauses at the gate
    world.stub()
    r = c.post(f"/api/review/{cid}/retry")
    assert r.status_code == 200, r.text
    assert world.doc(cid)["state"] == "paused"


def test_pages_are_served(world):
    c = world.client
    cid, _ = world.upload()
    for path in ("/review", f"/review/{cid}", "/review/nope"):
        r = c.get(path)
        assert r.status_code == 200 and "Prior auth" in r.text, path
    assert c.get("/static/review.js").status_code == 200 and c.get("/static/review.css").status_code == 200
    page = c.get("/review").text
    assert "review.js" in page and "review.css" in page
    # the old screen is untouched
    assert "<title>Prior auth</title>" in c.get("/").text and c.get(f"/patients/{cid}").status_code == 200


# ---------------------------------------------------------------- feedback


def _done_case(world, **kw) -> tuple[str, dict]:
    cid, _ = world.upload(**kw)
    world.confirm(cid, [GSV])
    return cid, world.doc(cid)


def test_feedback_every_kind_list_and_remove(world):
    c = world.client
    cid, d = _done_case(world)
    case = d["case"]
    reqs = {r["criterion"]: r for r in case["requirements"]}
    g_refs = reqs["compression"]["refs"]                      # guideline lines of one requirement
    quote = reqs["compression"]["evidence"][0]                # one evidence quote under it: its lines are the spans
    assert g_refs and quote["lines"] and all(x.startswith("r") for x in quote["lines"])
    assert KINDS == feedback.KINDS
    url = f"/api/review/{cid}/feedback"
    assert c.get(url).json() == []
    made = {}
    for kind in KINDS:
        guideline_side = kind in GL_KINDS
        body = {"kind": kind, "side": "guideline" if guideline_side else "chart",
                "text": f"note for {kind}", "spans": g_refs if guideline_side else quote["lines"],
                "requirements": ["compression"], "by": "Dana"}
        if kind == "edit":
            body["proposal"] = "compression therapy for at least 3 months, with the dates"
        r = c.post(url, json=body)
        assert r.status_code == 201, (kind, r.text)
        item = r.json()
        made[kind] = item
        assert ITEM_FIELDS <= set(item), kind
        assert len(item["id"]) == 12 and int(item["id"], 16) >= 0
        assert item["chart_id"] == cid and item["kind"] == kind and item["side"] == body["side"]
        assert item["text"] == body["text"] and item["requirements"] == ["compression"]
        assert item["proposal"] == (body.get("proposal") if kind == "edit" else None)
        assert item["guideline_id"] == world.guideline and item["guideline_sha"] == world.sha256
        assert item["pathway"] == ["gsv"] and item["h_key"] == d["confirmation"]["h_key"]
        assert item["run_id"] == d["status"]["run_id"] and item["by"] == "Dana" and item["at"]
        assert set(item["spans"]) >= set(body["spans"]) and all(x[0] == ("g" if guideline_side else "r") for x in item["spans"])
        if not guideline_side:
            assert item["spans"] == quote["lines"]           # the quote's own lines, so the page can match the chip to it
    listed = c.get(url).json()
    assert [x["kind"] for x in listed] == list(KINDS) and [x["id"] for x in listed] == [made[k]["id"] for k in KINDS]
    assert all(ITEM_FIELDS <= set(x) for x in listed)
    assert world.doc(cid)["feedback"] == listed
    # a range of guideline lines is expanded to ids
    first, last = reqs["reflux"]["refs"][0].split("-")[0], reqs["size"]["refs"][0]
    r = c.post(url, json={"kind": "logic_wrong", "side": "guideline", "text": "all, not any", "spans": [f"{first}-{last}"]})
    assert r.status_code == 201 and len(r.json()["spans"]) >= 3 and r.json()["by"] is None
    rid = r.json()["id"]
    # bad requests
    assert c.post(url, json={"kind": "praise", "side": "guideline", "text": "x", "spans": g_refs}).status_code == 400
    assert c.post(url, json={"kind": "edit", "side": "guideline", "text": "x", "spans": []}).status_code == 400
    assert c.post("/api/review/nope/feedback", json={"kind": "edit", "side": "guideline", "text": "x", "spans": g_refs}).status_code == 404
    # remove one
    assert c.delete(f"{url}/{made['edit']['id']}").json() == {"ok": True}
    assert c.delete(f"{url}/{made['edit']['id']}").status_code == 404
    assert c.delete(f"{url}/deadbeefcafe").status_code == 404
    ids = [x["id"] for x in c.get(url).json()]
    assert made["edit"]["id"] not in ids and len(ids) == len(KINDS)      # seven made, one range item added, one removed
    assert rid in ids
    # on disk, append-only under the feedback folder, never under data/
    folder = feedback.FEEDBACK
    assert (folder / f"{cid}.jsonl").exists()
    lines = [json.loads(x) for x in (folder / f"{cid}.jsonl").read_text().splitlines()]
    assert len(lines) == len(KINDS) + 2 and lines[-1] == {"op": "remove", "id": made["edit"]["id"]}
    assert not (store.DATA / "feedback" / f"{cid}.jsonl").exists()


def test_feedback_on_an_evidence_quote(world):
    """Wrong evidence / evidence about something else: filed from the quote under a requirement, stored on the
    chart side with the quote's own lines, so the page can match the chip back to that quote."""
    c = world.client
    cid, d = _done_case(world)
    reqs = {r["criterion"]: r for r in d["case"]["requirements"]}
    against = next(e for e in reqs["ulcer"]["evidence"] if e["side"] == "against")
    url = f"/api/review/{cid}/feedback"
    made = []
    for kind, text in (("wrong_evidence", "This line is about the other leg."),
                       ("evidence_elsewhere", "This describes the skin, not an ulcer.")):
        r = c.post(url, json={"kind": kind, "side": "chart", "text": text, "spans": against["lines"],
                              "requirements": ["ulcer"], "by": "Dana"})
        assert r.status_code == 201, (kind, r.text)
        item = r.json()
        assert item["kind"] == kind and item["side"] == "chart" and item["text"] == text
        assert item["spans"] == against["lines"] and item["requirements"] == ["ulcer"]
        assert item["pathway"] == ["gsv"] and item["proposal"] is None
        made.append(item)
    listed = c.get(url).json()
    assert [x["kind"] for x in listed] == ["wrong_evidence", "evidence_elsewhere"]
    # a chip belongs to the quote whose lines its spans intersect, and to no other quote
    others = [e for r in reqs.values() for e in r["evidence"] if not set(e["lines"]) & set(against["lines"])]
    assert others and all(not set(x["spans"]) & set(e["lines"]) for x in listed for e in others)
    # a quote citing one line and a range both store expanded r ids
    wide = next(e for r in reqs.values() for e in r["evidence"] if len(e["lines"]) > 1)
    r = c.post(url, json={"kind": "evidence_elsewhere", "side": "chart", "text": "", "spans": [wide["span"]],
                          "requirements": ["compression"]})
    assert r.status_code == 201 and r.json()["spans"] == wide["lines"]
    # and the cross-case list carries them under the confirmed section
    kinds = sorted(x["kind"] for x in c.get(f"/api/feedback?guideline={world.guideline}&pathway=gsv").json())
    assert kinds == ["evidence_elsewhere", "evidence_elsewhere", "wrong_evidence"]


def test_feedback_across_cases_by_guideline_and_section(world):
    c = world.client
    cid1, d1 = _done_case(world)
    cid2, d2 = _done_case(world)
    ref = d1["case"]["requirements"][0]["refs"]
    for cid in (cid1, cid2):
        r = c.post(f"/api/review/{cid}/feedback", json={"kind": "not_a_requirement", "side": "guideline",
                                                          "text": f"from {cid}", "spans": ref})
        assert r.status_code == 201
    # a case under another section
    cid3, _ = world.upload()
    world.confirm(cid3, [{"code": "36475", "pathway": "accessory"}])
    ref3 = world.doc(cid3)["case"]["requirements"][0]["refs"]
    assert c.post(f"/api/review/{cid3}/feedback", json={"kind": "should_be_requirement", "side": "guideline",
                                                          "text": "from acc", "spans": ref3}).status_code == 201
    gid = world.guideline
    both = c.get(f"/api/feedback?guideline={gid}&pathway=gsv").json()
    assert sorted(x["chart_id"] for x in both) == sorted([cid1, cid2])
    assert all(x["pathway"] == ["gsv"] and ITEM_FIELDS <= set(x) for x in both)
    acc = c.get(f"/api/feedback?guideline={gid}&pathway=accessory").json()
    assert [x["chart_id"] for x in acc] == [cid3] and acc[0]["pathway"] == ["accessory"]
    every = c.get(f"/api/feedback?guideline={gid}").json()
    assert sorted(x["chart_id"] for x in every) == sorted([cid1, cid2, cid3])
    assert c.get(f"/api/feedback?guideline={world.sha256[:16]}&pathway=gsv").json() == both
    assert [x["chart_id"] for x in c.get(f"/api/feedback?chart_id={cid2}").json()] == [cid2]
    assert c.get("/api/feedback?guideline=unknown").json() == []
    # removed items leave the cross-case list too
    c.delete(f"/api/review/{cid1}/feedback/{both[0]['id'] if both[0]['chart_id'] == cid1 else both[1]['id']}")
    assert [x["chart_id"] for x in c.get(f"/api/feedback?guideline={gid}&pathway=gsv").json()] == [cid2]
