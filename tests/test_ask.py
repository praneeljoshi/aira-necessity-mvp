"""Highlight to ask and adding lines to one case's checklist, in the review flow. The ask: free when the lines are
already requirements (stored verdicts, the case's own logic restricted to them), one stubbed model call otherwise,
cached by (chart, guideline sha, lines), every quote resolved and verified by code, where the lines come from. The
addition: per case only, one more AND term, K-L again with no model call, reversible, a sign-off withdrawn, filed as
feedback. Offline: the stub model, the store and the feedback folder in tmp_path. Never touches data/."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline
from app.core import llm, store
from app.review import ask, feedback
from tests.conftest import SAMPLES, idx, rng, sid
from tests.fake import Stub, ask_answer, selected_lines
from tests.conftest import accept_all
from tests.test_pipeline import assert_no_denial

GSV = {"code": "36475", "pathway": "gsv"}
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
        client, g, r = c, fl_spans, delgado_spans
        stub: Stub = None

        @staticmethod
        def case(**kw) -> str:
            W.stub = Stub(fl_spans, delgado_spans, **kw)
            monkeypatch.setattr(llm, "call", W.stub)
            with open(CHART, "rb") as f:
                r = c.post("/api/review/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid})
            assert r.status_code == 200, r.text
            cid = r.json()["chart_id"]
            assert c.post(f"/api/review/{cid}/pathways", json={"picks": [GSV], "by": "Dana"}).status_code == 200
            return cid

        @staticmethod
        def ask(cid: str, ids: list[str], expect=200) -> dict:
            r = c.post(f"/api/review/{cid}/ask", json={"span_ids": ids, "by": "Dana"})
            assert r.status_code == expect, r.text
            return r.json()

        @staticmethod
        def doc(cid: str) -> dict:
            return c.get(f"/api/review/{cid}").json()

    return W


def lines(g, first: str, last: str, start: int = 0) -> list[str]:
    a, b = rng(g, first, last, start).split("-")
    return [s.id for s in g[idx(g, a): idx(g, b) + 1]]


def P(g) -> int:
    return idx(g, sid(g, "POSITION STATEMENT"))


def asks(w) -> int:
    return w.stub.calls.count("ask_guideline")


# ---------------------------------------------------------------- known lines: no model call


def test_a_requirement_line_is_answered_from_the_stored_verdicts(world):
    cid = world.case()
    g = world.g
    size = sid(g, "The varicosities are at least 3 millimeters", P(g))
    n0 = len(world.stub.calls)
    a = world.ask(cid, [size])
    assert len(world.stub.calls) == n0                               # no model call
    assert a["source"] == "known" and a["requirements"] == ["size"]
    assert a["ruling"] == {"mark": "documented", "say": "Documented", "status": "MET"}
    assert a["lead"] and a["lead"]["side"] == "for" and a["lead"]["page"] and a["lead"]["text"]
    assert a["where"]["inside"] and not a["can_add"] and a["spans"] == [size]


def test_a_mixed_condition_keeps_the_case_logic_with_the_other_options(world):
    """"The varicosities are at least 3 mm AND one or more of: ulceration; thrombophlebitis; hemorrhage" selected:
    the lead-in sits between cited lines of one paragraph of the confirmed section, so the lines are known. The
    case's any() lost its fourth option (the symptoms, documented), which stays as "another option" and carries it:
    the selection reads as the case reads it."""
    cid = world.case()
    g = world.g
    ids = lines(g, "The varicosities are at least 3 millimeters", "3. Hemorrhage", P(g))
    n0 = len(world.stub.calls)
    a = world.ask(cid, ids)
    assert len(world.stub.calls) == n0 and a["source"] == "known"
    assert sid(g, "one or more of the following indications", P(g)) in a["set_aside"]
    t = a["logic"]
    assert t["op"] == "all" and [k.get("criterion") or k["op"] for k in t["kids"]] == ["size", "any"]
    alts = t["kids"][1]["kids"]
    assert [x["criterion"] for x in alts[:3]] == ["ulcer", "thromb", "hem"] and alts[3]["other"]
    assert alts[3]["mark"] == "documented" and alts[0]["mark"] == "not_needed"
    assert a["ruling"]["mark"] == "documented" and a["parts"] == 5


def test_a_gap_across_paragraphs_still_asks(world):
    """"criteria have been met:" sits between the cited "meets the definition of medical necessity" (its paragraph)
    and the cited reflux bullet (the next paragraph, after a blank line): across blocks, so the selection is asked."""
    cid = world.case(unanswerable=True)
    g = world.g
    ids = lines(g, "definition of medical necessity for symptomatic", "There is demonstrated saphenous reflux", P(g))
    a = world.ask(cid, ids)
    assert asks(world) == 1 and a["source"] == "asked"


def test_a_gap_outside_the_confirmed_section_is_never_known(fl_spans):
    """between_cited: only a paragraph's inner uncited lines, only inside the section's ranges."""
    from app.core.models import Range
    g = fl_spans
    size, lead, ulcer = (sid(g, n, P(g)) for n in ("at least 3 millimeters", "one or more of the following", "1. Ulceration"))
    gsv = Range(first=sid(g, "Great or Small Saphenous Veins", P(g)), last=sid(g, "considered cosmetic and does not", P(g)))
    acc = Range(first=sid(g, "Accessory Saphenous Veins", P(g)), last=sid(g, "of anatomy showing", P(g)))
    assert ask.between_cited(g, {size, ulcer}, [gsv]) == {lead}
    assert ask.between_cited(g, {size, ulcer}, [acc]) == set()                 # the cited lines are another section
    crit = sid(g, "criteria have been met:", P(g))
    necessity, reflux = sid(g, "definition of medical necessity for symptomatic", P(g)), sid(g, "demonstrated saphenous reflux", P(g))
    assert crit not in ask.between_cited(g, {necessity, reflux}, [gsv])        # across a blank line


# ---------------------------------------------------------------- new lines: one model call, cached, verified


def test_new_lines_take_one_call_then_come_from_the_cache(world):
    cid = world.case()
    g = world.g
    ids = lines(g, "Treatment of the great or small saphenous veins by surgery (ligation", "criteria have been met:", P(g))
    a = world.ask(cid, ids)
    assert asks(world) == 1 and a["source"] == "asked" and a["can_add"]
    assert a["ruling"]["mark"] in ("documented", "missing", "contradicted")
    rt = {s.id: s for s in world.r}
    if a["lead"]:                                                    # the quote is the chart's own lines, by code
        assert a["lead"]["text"] == " ".join(rt[i].text.strip() for i in a["lead"]["lines"])
    b = world.ask(cid, list(reversed(ids)))                          # same lines, any order: the cache
    assert asks(world) == 1 and b["source"] == "cached" and b["ruling"] == a["ruling"]
    raw = json.loads((store.RESULTS / cid / "asks.json").read_text())["asks"]
    assert list(raw) == [a["key"]] and a["key"].endswith("+".join(sorted(ids)))


def test_the_model_never_types_the_evidence(world):
    """Citations outside the selection are dropped, a chart span that does not exist is dropped with a reason, a
    quote not in its lines is dropped (the whole lines show), logic that does not parse makes every part required."""
    g = world.g
    cosmetic = lines(g, "Treatment of great or small saphenous veins by surgery, endovenous", "considered cosmetic", P(g))
    bad = {"chart_can_show": True, "kind": "requirement",
           "parts": [{"id": "a", "refs": [cosmetic[0]], "quote": "words that are not there"},
                     {"id": "b", "refs": [cosmetic[2]], "quote": "considered cosmetic"},
                     {"id": "c", "refs": ["g0001"], "quote": "outside"}],
           "logic": {"both": ["a", "b"]},
           "verdicts": [{"criterion": "a", "status": "MET", "confidence": 0.9, "for": ["r9999"]},
                        {"criterion": "b", "status": "NOT_MET", "confidence": 0.9, "against": []}]}
    cid = world.case(ask=bad)
    a = world.ask(cid, cosmetic)
    raw = ask.cached(cid, a["key"])
    assert [c["id"] for c in raw["criteria"]] == ["a", "b"]
    assert "quote" not in raw["criteria"][0] and raw["criteria"][1]["quote"] == "considered cosmetic"
    assert raw["logic"] == {"all": ["a", "b"]}
    assert raw["verdicts"]["a"]["for"] == [] and raw["verdicts"]["b"]["status"] == "INSUFFICIENT"   # NOT_MET, no against
    assert any("outside the selected lines" in p for p in a["problems"])
    assert any("could not be found in the case" in p for p in a["problems"])
    assert a["ruling"]["mark"] == "missing" and a["lead"] is None


def test_headings_and_billing_are_not_something_the_chart_can_show(world):
    cid = world.case()
    g = world.g
    a = world.ask(cid, [sid(g, "BILLING/CODING INFORMATION")])
    assert a["ruling"]["mark"] == "not_chart" and a["ruling"]["say"] == "This isn't something the case can show"
    assert a["why_not"] and not a["can_add"] and a["logic"] is None
    assert not a["where"]["inside"] and "Billing/coding information" in a["where"]["say"]
    other = world.ask(cid, [sid(g, "Incompetence of the accessory saphenous vein is isolated")])
    assert "another indication" in other["where"]["say"] and "Accessory" in other["where"]["say"]
    assert world.client.post(f"/api/review/{cid}/ask", json={"span_ids": []}).status_code == 400
    assert world.client.post(f"/api/review/{cid}/ask", json={"span_ids": [s.id for s in g[:41]]}).status_code == 400


def test_probes_are_kept_per_case(world):
    cid = world.case()
    g = world.g
    size = sid(g, "The varicosities are at least 3 millimeters", P(g))
    world.ask(cid, [size])
    world.ask(cid, [sid(g, "BILLING/CODING INFORMATION")])
    pr = world.doc(cid)["probes"]
    assert [p["spans"] for p in pr] == [[size], [sid(g, "BILLING/CODING INFORMATION")]]
    assert pr[0]["source"] == "known" and pr[0]["by"] == "Dana" and pr[0]["mark"] == "documented"


def test_the_stub_reads_a_and_either_b_or_c():
    prompt = ("## The selected guideline lines\n\n[g0041]     •   The varicosities are at least 3 millimeters in size AND\n"
              "[g0042]     •   There is documentation of one or more of the following indications:\n"
              "[g0043]         1. Ulceration secondary to venous stasis; OR\n[g0044]         2. Recurrent superficial thrombophlebitis; OR\n\n## The lines")
    assert [i for i, _ in selected_lines(prompt)] == ["g0041", "g0042", "g0043", "g0044"]
    from app.core.models import Span
    a = ask_answer([Span(id="r0001", text="No ulceration.")], prompt)
    assert a["logic"] == {"all": ["p1", {"any": ["p2", "p3"]}]}


# ---------------------------------------------------------------- adding the lines to this case's checklist


def test_add_joins_the_logic_for_this_case_only(world):
    g = world.g
    cosmetic = lines(g, "Treatment of great or small saphenous veins by surgery, endovenous", "considered cosmetic", P(g))
    other = world.case()
    cid = world.case(ask=lambda prompt: {
        "chart_can_show": True, "kind": "requirement",
        "parts": [{"id": "cosmetic", "refs": [f"{cosmetic[0]}-{cosmetic[-1]}"], "quote": "considered cosmetic"}],
        "logic": "cosmetic", "verdicts": [{"criterion": "cosmetic", "status": "INSUFFICIENT", "confidence": 0.6}]})
    c = world.client
    crit_files = {p.name: p.read_bytes() for p in store.CRITERIA.glob("*.json")}
    assert world.doc(cid)["case"]["result"]["queue"] == "ready"
    accept_all(c, cid)
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 201
    assert c.post(f"/api/review/{cid}/additions", json={"span_ids": cosmetic, "by": "Dana"}).status_code == 409  # ask first
    a = world.ask(cid, cosmetic)
    assert a["can_add"] and a["ruling"]["mark"] == "missing"
    calls = len(world.stub.calls)
    r = c.post(f"/api/review/{cid}/additions", json={"span_ids": cosmetic, "by": "Dana"})
    assert r.status_code == 201, r.text
    d = r.json()
    assert len(world.stub.calls) == calls                           # K-L again, no model call
    res = d["case"]["result"]
    assert res["determination"] == "INSUFFICIENT" and res["queue"] == "review"
    assert_no_denial(res["ask"]) and assert_no_denial(d["case"]["ask"])
    added = [x for x in d["case"]["requirements"] if x.get("added")]
    assert len(added) == 1 and added[0]["mark"] == "missing" and added[0]["added"]["by"] == "Dana"
    assert set(cosmetic) <= {ln["id"] for s in d["case"]["tree"]["sections"] for ln in s["lines"]}
    assert d["signoff"]["state"] == "not_ready" and d["signoff"]["record"]["withdrawn"]["why"] == "addition"
    rec = json.loads((store.RESULTS / cid / "additions.json").read_text())["additions"]
    assert len(rec) == 1 and rec[0]["by"] == "Dana" and rec[0]["at"] and rec[0]["spans"] == cosmetic
    fb = [x for x in d["feedback"] if x.get("addition")]
    assert len(fb) == 1 and fb[0]["kind"] == "should_be_requirement" and fb[0]["spans"] == cosmetic
    assert {p.name: p.read_bytes() for p in store.CRITERIA.glob("*.json")} == crit_files      # the cache untouched
    assert world.doc(other)["case"]["result"]["queue"] == "ready"   # another case untouched
    again = world.ask(cid, cosmetic)                                 # now known: on the checklist
    assert again["source"] == "added" and again["added"]["id"] == rec[0]["id"] and not again["can_add"]
    assert c.post(f"/api/review/{cid}/additions", json={"span_ids": cosmetic}).status_code == 409
    # take it off: back to ready, the sign-off stays withdrawn, the feedback item goes
    r = c.delete(f"/api/review/{cid}/additions/{rec[0]['id']}?by=Dana")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["case"]["result"]["queue"] == "ready" and d["signoff"]["state"] == "needed"
    assert not [x for x in d["case"]["requirements"] if x.get("added")] and not [x for x in d["feedback"] if x.get("addition")]
    assert d["additions"][0]["undone"]["by"] == "Dana"
    assert c.delete(f"/api/review/{cid}/additions/{rec[0]['id']}").status_code == 404


def test_a_documented_addition_keeps_the_case_ready_and_the_signer_sees_it(world):
    g = world.g
    ids = lines(g, "Treatment of the great or small saphenous veins by surgery (ligation", "criteria have been met:", P(g))
    cid = world.case()
    a = world.ask(cid, ids)
    assert a["ruling"]["mark"] == "documented", a
    d = world.client.post(f"/api/review/{cid}/additions", json={"span_ids": ids, "by": "Dana"}).json()
    assert d["case"]["result"]["queue"] == "ready", d["case"]["result"]["review_reasons"]
    assert d["signoff"]["state"] == "needed"
    assert [x["spans"] for x in d["signoff"]["additions"]] == [ids]
    accept_all(world.client, cid)
    r = world.client.post(f"/api/review/{cid}/signoff", json={"by": "Dana"})
    assert r.status_code == 201 and r.json()["signoff"]["record"]["additions"][0]["spans"] == ids


def test_lines_a_chart_cannot_show_cannot_be_added(world):
    cid = world.case()
    head = [sid(world.g, "BILLING/CODING INFORMATION")]
    world.ask(cid, head)
    assert world.client.post(f"/api/review/{cid}/additions", json={"span_ids": head}).status_code == 400
    size = [sid(world.g, "The varicosities are at least 3 millimeters", P(world.g))]
    world.ask(cid, size)
    assert world.client.post(f"/api/review/{cid}/additions", json={"span_ids": size}).status_code == 409


def test_ask_needs_a_finished_case(world, monkeypatch):
    s = Stub(world.g, world.r)
    monkeypatch.setattr(llm, "call", s)
    with open(CHART, "rb") as f:
        r = world.client.post("/api/review/charts", files={"file": ("d.pdf", f, "application/pdf")},
                              data={"guideline_id": "bcbsfl-02-33000-31"})
    cid = r.json()["chart_id"]
    assert world.client.post(f"/api/review/{cid}/ask", json={"span_ids": ["g0040"]}).status_code == 409
    assert world.client.post("/api/review/nope/ask", json={"span_ids": ["g0040"]}).status_code == 404


def test_a_model_error_comes_back_as_a_502_with_its_message(world, monkeypatch):
    """The ask's model call failing (a refused key, a model that answers in the wrong shape twice) is a 502 whose
    detail is the error's first line, "Type: message", which the page shows; never a bare 500."""
    import httpx2
    import openai
    cid = world.case()
    ids = lines(world.g, "Treatment of the great or small saphenous veins by surgery (ligation", "criteria have been met:", P(world.g))
    req = httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")
    body = {"message": "Incorrect API key provided: sk-abc***xyz.", "type": "invalid_request_error", "code": "invalid_api_key"}
    for err, want in [
        (openai.AuthenticationError(f"Error code: 401 - {{'error': {body}}}", response=httpx2.Response(401, request=req), body=body),
         "AuthenticationError: Error code: 401 - {'error': {'message': 'Incorrect API key provided: sk-abc***xyz.'"),
        (RuntimeError("ask_guideline: model output failed validation twice: 1 validation error for AskOut\nruling\n  Field required"),
         "RuntimeError: ask_guideline: model output failed validation twice: 1 validation error for AskOut"),
        (openai.APIConnectionError(request=req), "APIConnectionError: Connection error."),
    ]:
        def boom(*a, err=err, **k):
            raise err
        monkeypatch.setattr(llm, "call", boom)
        r = world.client.post(f"/api/review/{cid}/ask", json={"span_ids": ids, "by": "Dana"})
        assert r.status_code == 502, r.text
        d = r.json()["detail"]
        assert d.startswith(want) and "\n" not in d and len(d) <= 400
