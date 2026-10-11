"""Strike a requirement for one case, and sign-off before Ready, in the review flow. The prune rules per operator,
the strike endpoints (no reason needed, per case only, reversible, K-L again with no model call, filed as feedback),
the sign-off (only a ready case, who and when, withdrawn by any later change). Offline: the stub model, the store
and the feedback folder in tmp_path. Never touches data/."""
from __future__ import annotations

import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import main, pipeline
from app.core import llm, store
from app.review import feedback, signoff, strikes
from app.core.models import CriteriaSet, Criterion, Expression
from tests.conftest import SAMPLES
from tests.fake import Stub
from tests.conftest import accept_all
from tests.test_pipeline import assert_no_denial

GSV = {"code": "36475", "pathway": "gsv"}
CHART = SAMPLES / "synthetic" / "maria_delgado_chart.pdf"


# ---------------------------------------------------------------- prune, per operator


def test_prune_all_any_drop_the_leaf():
    assert strikes.prune({"all": ["a", "b", "c"]}, {"b"}) == {"all": ["a", "c"]}
    assert strikes.prune({"all": ["a", "b"]}, {"b"}) == "a"                       # one child left replaces the all
    assert strikes.prune({"any": ["a", "b", "c"]}, {"a"}) == {"any": ["b", "c"]}  # that alternative is dropped
    assert strikes.prune({"any": ["a", "b"]}, {"a", "b"}) is None
    assert strikes.prune("a", {"a"}) is None and strikes.prune("a", {"b"}) == "a"
    e = {"all": ["reflux", {"any": ["ulcer", {"all": ["symptoms", "adl"]}]}]}
    assert strikes.prune(e, {"ulcer"}) == {"all": ["reflux", {"all": ["symptoms", "adl"]}]}
    assert strikes.prune(e, {"adl"}) == {"all": ["reflux", {"any": ["ulcer", "symptoms"]}]}
    assert strikes.prune(e, {"ulcer", "symptoms", "adl"}) == "reflux"             # an emptied any leaves its parent


def test_prune_at_least_k_of_n_minus_one_clamped():
    e = {"at_least": {"k": 2, "of": ["a", "b", "c"]}}
    assert strikes.prune(e, {"c"}) == {"at_least": {"k": 2, "of": ["a", "b"]}}
    assert strikes.prune({"at_least": {"k": 3, "of": ["a", "b", "c"]}}, {"a"}) == {"at_least": {"k": 2, "of": ["b", "c"]}}
    assert strikes.prune(e, {"b", "c"}) == "a"
    assert strikes.prune(e, {"a", "b", "c"}) is None


def test_prune_under_not_drops_the_exclusion():
    assert strikes.prune({"all": ["a", {"not": "x"}]}, {"x"}) == "a"
    # "none of the following": the struck item goes, the others still exclude
    assert strikes.prune({"not": {"any": ["x", "y", "z"]}}, {"y"}) == {"not": {"any": ["x", "z"]}}
    assert strikes.prune({"not": {"any": ["x", "y"]}}, {"y"}) == {"not": "x"}
    # a compound exclusion ("X without Y"): the whole exclusion goes, never a wider one made of its other part
    e = {"all": ["a", {"not": {"all": ["x", "y"]}}]}
    assert strikes.prune(e, {"x"}) == "a" and strikes.prune(e, {"y"}) == "a"
    # an item of "none of the following" that is itself compound: that item goes
    assert strikes.prune({"not": {"any": [{"all": ["x", "y"]}, "z"]}}, {"x"}) == {"not": "z"}
    # a not inside a not is positive again: an all there drops only the leaf
    assert strikes.prune({"not": {"not": {"all": ["x", "y"]}}}, {"x"}) == {"not": {"not": "y"}}


def test_split_lists_what_a_compound_strike_takes_with_it(tmp_store, fl_spans):
    from app.ingest.spans import table, wording
    g = fl_spans[:3]
    crit = [Criterion(id=i, refs=[g[k].id], question=i) for k, i in enumerate(("a", "x", "y"))]
    cs = CriteriaSet(key="k1", criteria=crit, expressions=[Expression(pathway="p", expr={"all": ["a", {"not": {"all": ["x", "y"]}}]})])
    gt = table(g)
    (store.RESULTS / "c1").mkdir(parents=True)
    rec = {"id": "s1", "criterion": "x", "words": wording(crit[1], gt), "criteria_key": "k1", "reason": "r", "undone": None}
    (store.RESULTS / "c1" / "strikes.json").write_text(json.dumps({"strikes": [rec]}))
    pruned, removed = strikes.split("c1", cs, g, ["p"])
    assert pruned.expressions[0].expr == "a" and cs.expressions[0].expr != "a"          # the cached set is untouched
    assert removed["x"]["removed_with"] is None and removed["y"]["removed_with"] == "x"
    # another checklist (a different key, or different words) is not touched by the strike
    assert strikes.split("c1", cs.model_copy(update={"key": "k2"}), g, ["p"])[1] == {}


# ---------------------------------------------------------------- the review flow


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
        calls: list[str] = []

        @staticmethod
        def case(**kw) -> str:
            """Upload the Delgado chart through the review flow and confirm the suggested section."""
            s = Stub(fl_spans, delgado_spans, **kw)
            W.calls = s.calls
            monkeypatch.setattr(llm, "call", s)
            with open(CHART, "rb") as f:
                r = c.post("/api/review/charts", files={"file": ("delgado.pdf", f, "application/pdf")}, data={"guideline_id": gid})
            assert r.status_code == 200, r.text
            cid = r.json()["chart_id"]
            assert c.post(f"/api/review/{cid}/pathways", json={"picks": [GSV], "by": "Dana"}).status_code == 200
            return cid

        @staticmethod
        def doc(cid: str) -> dict:
            r = c.get(f"/api/review/{cid}")
            assert r.status_code == 200, r.text
            return r.json()

        @staticmethod
        def strike(cid: str, criterion: str, reason: str = "Billing line, not for this patient.", by="Dana", expect=201) -> dict:
            r = c.post(f"/api/review/{cid}/strikes", json={"criterion": criterion, "reason": reason, "by": by})
            assert r.status_code == expect, r.text
            return r.json()

        @staticmethod
        def row(cid: str) -> dict:
            return next(x for x in c.get("/api/orders").json() if x["chart_id"] == cid)

    return W


def reqs(d: dict) -> dict:
    return {r["criterion"]: r for r in d["case"]["requirements"]}


def test_sign_off_before_ready(world):
    cid = world.case()
    d = world.doc(cid)
    assert d["case"]["result"]["queue"] == "ready"
    so = d["signoff"]
    assert so["state"] == "needed" and so["ready"] and not so["signed"] and so["record"] is None and so["strikes"] == []
    assert world.row(cid)["signoff"] == "needed" and world.row(cid)["queue"] == "ready"
    c = world.client
    assert c.post(f"/api/review/{cid}/signoff", json={}).status_code == 400              # a name is required
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "  "}).status_code == 400
    assert c.post("/api/review/nope/signoff", json={"by": "Dana"}).status_code == 404
    accept_all(c, cid)
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"})
    assert r.status_code == 201, r.text
    so = r.json()["signoff"]
    assert so["state"] == "signed" and so["signed"] and so["record"]["by"] == "Dana" and so["record"]["at"]
    assert so["record"]["determination"] == "MET" and so["record"]["packet"] and so["stale"] is False
    on_disk = json.loads((store.RESULTS / cid / "signoff.json").read_text())
    assert on_disk["by"] == "Dana" and on_disk["fingerprint"] == signoff.fingerprint(cid)
    assert world.row(cid)["signoff"] == "signed"
    # withdraw it; it is needed again
    assert c.delete(f"/api/review/{cid}/signoff?by=Dana").status_code == 200
    assert world.doc(cid)["signoff"]["state"] == "needed"
    assert c.delete(f"/api/review/{cid}/signoff").status_code == 404
    # a re-run invalidates it: the result is written again, the fingerprint no longer matches
    accept_all(c, cid)
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 201
    assert c.post(f"/api/orders/{cid}/recheck", json={}).status_code == 200
    so = world.doc(cid)["signoff"]
    assert so["state"] == "needed" and so["record"]["withdrawn"]["why"] == "re-check" and so["record"]["by"] == "Dana"


def test_a_result_that_is_not_ready_cannot_be_signed_off(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT"}})
    d = world.doc(cid)
    assert d["case"]["result"]["queue"] == "review" and d["signoff"]["state"] == "not_ready"
    accept_all(world.client, cid)
    r = world.client.post(f"/api/review/{cid}/signoff", json={"by": "Dana"})
    assert r.status_code == 409 and "ready" in r.json()["detail"]
    assert not (store.RESULTS / cid / "signoff.json").exists()
    assert world.row(cid)["signoff"] == "not_ready"


def test_strike_reruns_the_decision_per_case_and_is_reversible(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT"}})
    other = world.case(verdicts={"size": {"status": "INSUFFICIENT"}})
    d = world.doc(cid)
    assert d["case"]["result"]["determination"] == "INSUFFICIENT" and reqs(d)["size"]["mark"] == "missing"
    h_key = d["confirmation"]["h_key"]
    cache = (store.CRITERIA / f"{h_key}.json").read_bytes()
    calls = len(world.calls)
    # refused: not a requirement of this case, a paused or unknown case (no reason is needed)
    world.strike(cid, "nope", expect=400)
    world.strike("nope", "size", expect=404)
    # struck: K-L again, no model call; the result is now ready, waiting for sign-off
    d = world.strike(cid, "size", reason="The size is not required for this vein.", by="Dana")
    assert len(world.calls) == calls
    res = d["case"]["result"]
    assert res["determination"] == "MET" and res["queue"] == "ready" and res["ask"].startswith("Nothing to ask")
    assert all(p["criterion"] != "size" for p in res["packet"]) and all(m["criterion"] != "size" for m in res["misses"])
    assert d["signoff"]["state"] == "needed"
    size = reqs(d)["size"]
    assert size["mark"] == "struck" and size["say"] == "Removed for this case" and size["evidence"] == []
    assert size["struck"]["reason"] == "The size is not required for this vein." and size["struck"]["by"] == "Dana"
    assert size["highlights"] and size["block"]
    assert d["case"]["tree"]["misses"] == [] and "size" not in [m["criterion"] for m in d["case"]["tree"]["misses"]]
    (sk,) = d["strikes"]
    assert sk["criterion"] == "size" and sk["undone"] is None and sk["criteria_key"] and sk["refs"]
    assert d["signoff"]["strikes"][0]["id"] == sk["id"]
    assert d["status"]["redecided"]["why"] == "strike"
    # filed as feedback, visible across cases
    fb = [x for x in d["feedback"] if x.get("strike") == sk["id"]]
    assert len(fb) == 1 and fb[0]["kind"] == "not_a_requirement" and fb[0]["text"] == sk["reason"]
    assert fb[0]["requirements"] == ["size"] and fb[0]["spans"] == sk["refs"]
    across = world.client.get(f"/api/feedback?guideline={world.guideline}&pathway=gsv").json()
    assert any(x.get("strike") == sk["id"] for x in across)
    # per case only: the cached checklist and the other case are untouched
    assert (store.CRITERIA / f"{h_key}.json").read_bytes() == cache
    o = world.doc(other)
    assert o["case"]["result"]["determination"] == "INSUFFICIENT" and reqs(o)["size"]["mark"] == "missing" and o["strikes"] == []
    # once only; sign it off, then un-strike: back to the first result, the sign-off withdrawn, the feedback gone
    world.strike(cid, "size", expect=409)
    accept_all(world.client, cid)
    assert world.client.post(f"/api/review/{cid}/signoff", json={"by": "Dana", "gaps_checked": True}).status_code == 201
    r = world.client.delete(f"/api/review/{cid}/strikes/{sk['id']}?by=Lee")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["case"]["result"]["determination"] == "INSUFFICIENT" and reqs(d)["size"]["mark"] == "missing"
    assert d["signoff"]["state"] == "not_ready" and d["signoff"]["record"]["withdrawn"]["why"] == "un-strike"
    assert d["strikes"][0]["undone"]["by"] == "Lee"
    assert not any(x.get("strike") == sk["id"] for x in d["feedback"])
    assert world.client.delete(f"/api/review/{cid}/strikes/{sk['id']}").status_code == 404
    assert len(world.calls) == calls
    assert_no_denial(d["case"]["ask"])


def test_strike_withdraws_a_sign_off(world):
    cid = world.case()
    accept_all(world.client, cid)
    assert world.client.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 201
    d = world.strike(cid, "ulcer", reason="No ulcer pathway for this patient.")
    so = d["signoff"]
    assert so["state"] == "needed" and so["record"]["withdrawn"]["why"] == "strike"
    assert d["case"]["result"]["determination"] == "MET"
    assert reqs(d)["ulcer"]["mark"] == "struck" and reqs(d)["thromb"]["mark"] in ("not_needed", "other_option")


def test_a_struck_alternative_that_was_the_documented_one(world):
    # the symptoms branch is the one documented; striking an item of it drops it from that all, the rest decide
    cid = world.case(verdicts={"compression": {"status": "INSUFFICIENT"}})
    d = world.doc(cid)
    assert d["case"]["result"]["determination"] == "INSUFFICIENT"
    d = world.strike(cid, "compression", reason="Compression is not required by this payer for this case.")
    assert d["case"]["result"]["determination"] == "MET" and d["case"]["result"]["queue"] == "ready"


def test_the_last_requirement_cannot_be_struck(world):
    cid = world.case()
    leaves = ["reflux", "ceap", "size", "ulcer", "thromb", "hem", "symptoms", "adl"]
    for x in leaves:
        world.strike(cid, x, reason=f"{x} not needed")
    r = world.strike(cid, "compression", expect=400)
    assert "last requirement" in r["detail"]
    d = world.doc(cid)
    assert len(d["strikes"]) == 8 and d["case"]["result"]["determination"] == "MET"
    assert {k for k, v in reqs(d).items() if v["mark"] == "struck"} == set(leaves)


def test_strike_only_on_a_finished_case(world, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "call", Stub(fl_spans, delgado_spans))
    with open(CHART, "rb") as f:
        r = world.client.post("/api/review/charts", files={"file": ("delgado.pdf", f, "application/pdf")},
                              data={"guideline_id": world.guideline})
    cid = r.json()["chart_id"]
    assert world.doc(cid)["state"] == "paused" and world.doc(cid)["signoff"]["state"] == "not_ready"
    world.strike(cid, "size", expect=409)
    assert world.client.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 409


def test_a_strike_survives_a_re_run_of_the_same_checklist(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT"}})
    world.strike(cid, "size", reason="Not needed here for this vein.")
    assert world.client.post(f"/api/orders/{cid}/recheck", json={}).status_code == 200
    d = world.doc(cid)
    assert d["case"]["result"]["determination"] == "MET" and reqs(d)["size"]["mark"] == "struck"
    assert (store.RESULTS / cid / "jreasons.json").exists()


def test_a_result_saved_before_jreasons_is_decided_again_from_its_verdicts(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT"}})
    (store.RESULTS / cid / "jreasons.json").unlink()
    d = world.strike(cid, "size", reason="Not needed here for this vein.")
    assert d["case"]["result"]["determination"] == "MET" and (store.RESULTS / cid / "jreasons.json").exists()


# ---------------------------------------------------------------- reason codes: one tap, a note when it helps


def test_a_strike_carries_its_reason_code_to_the_record_and_the_feedback(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT"}})
    c = world.client
    post = lambda body, expect: (lambda r: (r.status_code == expect or pytest.fail(r.text), r.json())[1])(
        c.post(f"/api/review/{cid}/strikes", json={"by": "Dana", **body}))
    d = world.doc(cid)
    assert [x["code"] for x in d["strike_reasons"]] == [x[0] for x in strikes.REASONS] and len(d["strike_reasons"]) == 6
    post({"criterion": "ceap", "code": "nope"}, 400)                          # not one of the chips
    # no note is needed for any chip, nor for a requirement the chart does not document (the human is the judge)
    # a documented requirement: the chip alone is enough; the label stands in for the reason
    d = post({"criterion": "ceap", "code": "paperwork"}, 201)
    (k,) = [x for x in d["strikes"] if x["criterion"] == "ceap"]
    assert k["code"] == "paperwork" and k["reason"] == "Paperwork the payer collects"
    assert reqs(d)["ceap"]["struck"]["code"] == "paperwork"
    # a chip and a note on a gap
    d = post({"criterion": "size", "code": "other_section", "reason": "The size rule is the tributaries section's."}, 201)
    (k2,) = [x for x in d["strikes"] if x["criterion"] == "size"]
    assert k2["code"] == "other_section" and k2["reason"] == "The size rule is the tributaries section's." and k2["was"] == "missing"
    assert {x["criterion"]: x["code"] for x in d["signoff"]["strikes"]} == {"ceap": "paperwork", "size": "other_section"}
    # filed as feedback with the code; across cases too, filtered by guideline and section
    fb = {x["strike"]: x for x in d["feedback"] if x.get("strike")}
    assert fb[k["id"]]["code"] == "paperwork" and fb[k2["id"]]["code"] == "other_section"
    assert fb[k2["id"]]["text"] == k2["reason"]
    across = c.get(f"/api/feedback?guideline={world.guideline}&pathway=gsv").json()
    assert {x["code"] for x in across if x.get("strike")} == {"paperwork", "other_section"}
    # an older page that sends a reason only still works; its record has no code
    d = post({"criterion": "reflux", "reason": "Not needed here."}, 201)
    (k3,) = [x for x in d["strikes"] if x["criterion"] == "reflux"]
    assert k3["code"] is None and k3["reason"] == "Not needed here."


def test_older_feedback_and_strike_records_without_a_code_still_read(world):
    cid = world.case()
    world.strike(cid, "ulcer", reason="No ulcer pathway for this patient.")
    # rewrite both files as an older page left them: no `code` anywhere
    f = feedback._chart_file(cid)
    f.write_text("".join(json.dumps({k: v for k, v in json.loads(ln).items() if k != "code"}) + "\n" for ln in f.read_text().splitlines()))
    p = store.RESULTS / cid / "strikes.json"
    p.write_text(json.dumps({"strikes": [{k: v for k, v in x.items() if k != "code"} for x in json.loads(p.read_text())["strikes"]]}))
    d = world.doc(cid)
    assert [x["code"] for x in d["feedback"]] == [None] and "code" not in d["strikes"][0]
    assert reqs(d)["ulcer"]["mark"] == "struck" and reqs(d)["ulcer"]["struck"]["code"] is None
    across = world.client.get(f"/api/feedback?guideline={world.guideline}").json()
    assert across and across[0]["code"] is None
