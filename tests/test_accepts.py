"""Accept a requirement for one case: the coordinator approves its ruling and evidence. Sign-off needs every
requirement accepted or struck and nothing left to ask; the packet and the message to the surgeon assemble from
accepted items; Undo withdraws a sign-off; a re-run makes accepts stale. Offline: the stub model, the store and the
feedback folder in tmp_path. Never touches data/."""
from __future__ import annotations

from tests.conftest import accept_all  # noqa: F401
from tests.test_pipeline import assert_no_denial
from tests.test_strikes import world  # noqa: F401  (the review-flow fixture)


def test_accept_builds_the_case_and_gates_sign_off(world):
    cid = world.case()
    c = world.client
    d = world.doc(cid)
    p = d["case"]["progress"]
    assert p["total"] == 6 and p["accepted"] == 0 and p["to_ask"] == 0 and not p["can_sign"] and not d["signoff"]["can_sign"]
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 409        # nothing accepted yet
    assert c.get(f"/api/orders/{cid}").json()["signoff"] == "needed"     # the / flow reads "Ready for sign-off" from this
    reqs = {x["criterion"]: x for x in d["case"]["requirements"]}
    assert not reqs["ulcer"]["counted"] and reqs["size"]["counted"]                           # an unneeded option
    assert c.post(f"/api/review/{cid}/accepts", json={"criterion": "ulcer", "by": "Dana"}).status_code == 400
    assert c.post(f"/api/review/{cid}/accepts", json={"criterion": "size"}).status_code == 400      # a name is required
    r = c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "by": "Dana"})
    assert r.status_code == 201
    d = r.json()
    size = next(x for x in d["case"]["requirements"] if x["criterion"] == "size")
    assert size["accepted"]["by"] == "Dana" and d["case"]["progress"]["accepted"] == 1
    assert [x["criterion"] for x in d["case"]["packet_accepted"]] == ["size"]                 # packet from accepts
    assert c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "by": "Dana"}).status_code == 409
    d = accept_all(c, cid)
    assert d["case"]["progress"]["can_sign"] and len(d["case"]["packet_accepted"]) == 6
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 201
    # Undo one accept: the sign-off no longer counts, sign-off is blocked again
    aid = next(x for x in d["case"]["requirements"] if x["criterion"] == "size")["accepted"]["id"]
    d = c.delete(f"/api/review/{cid}/accepts/{aid}?by=Dana").json()
    assert d["signoff"]["state"] == "needed" and d["signoff"]["record"]["withdrawn"]["why"] == "accept undone"
    assert not d["case"]["progress"]["can_sign"] and d["case"]["progress"]["open"] == ["size"]
    assert c.delete(f"/api/review/{cid}/accepts/{aid}").status_code == 404


def test_a_strike_counts_and_accepts_survive_it_but_not_a_rerun(world, monkeypatch):
    cid = world.case()
    c = world.client
    accept_all(c, cid)
    d = world.strike(cid, "size")
    p = d["case"]["progress"]
    assert p["struck"] == 1 and p["total"] == 5 and p["accepted"] == 5 and p["can_sign"]
    # a re-run (a new run id): every accept is stale, nothing counts, the records stay
    r = c.post(f"/api/orders/{cid}/retry")
    assert r.status_code == 200, r.text
    d = world.doc(cid)
    assert d["case"]["progress"]["accepted"] == 0 and len([x for x in d["accepts"] if not x["undone"]]) == 6


def test_a_missing_requirement_goes_into_the_ask_not_the_accepted(world):
    """Accept means proof: "Not in the chart yet" is added to the ask (the message to the surgeon), shows as in the
    ask, never counts as accepted, and the case cannot be signed while anything is in the ask."""
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT", "for": []}})
    c = world.client
    d = world.doc(cid)
    p = d["case"]["progress"]
    assert p["to_ask"] == 1 and p["in_ask"] == 0 and p["asks"] == ["size"] and p["total"] == 5 and d["case"]["message"] == ""
    d = c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "by": "Dana"}).json()
    size = next(x for x in d["case"]["requirements"] if x["criterion"] == "size")
    assert size["in_ask"]["by"] == "Dana" and size["accepted"] is None
    p = d["case"]["progress"]
    assert p["in_ask"] == 1 and p["to_ask"] == 0 and p["accepted"] == 0
    msg = d["case"]["message"]
    assert "3 millimeters" in msg and msg.startswith("Dr. Vasquez")
    assert_no_denial(msg)
    assert "size" not in [x["criterion"] for x in d["case"]["packet_accepted"]]
    assert c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "by": "Dana"}).status_code == 409
    d = accept_all(c, cid)
    assert d["case"]["progress"]["accepted"] == 5 and not d["case"]["progress"]["can_sign"]   # still something in the ask
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 409


def test_packet_quotes_are_whole_sentences(world):
    import re
    from tests.conftest import accept_all
    cid = world.case()
    d = accept_all(world.client, cid)
    qs = [q["quote"] for p in d["case"]["packet_accepted"] for q in p["quotes"]]
    assert qs and all(re.search(r"([.!?][\"”’)]*|…)$", q) for q in qs), qs
    assert not any("   " in q or q.endswith(" No") for q in qs)


def test_striking_a_gap_needs_a_real_reason_and_is_recorded(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT", "for": []}})
    c = world.client
    assert c.post(f"/api/review/{cid}/strikes", json={"criterion": "size", "reason": "billing", "by": "Dana"}).status_code == 400
    d = world.strike(cid, "size", reason="The surgeon measured it in clinic; not needed here.")
    sk = [x for x in d["strikes"] if not x["undone"]]
    assert sk[0]["was"] == "missing" and d["case"]["result"]["queue"] == "ready"
    # a documented requirement can still be struck with a short reason
    assert c.post(f"/api/review/{cid}/strikes", json={"criterion": "reflux", "reason": "dup", "by": "Dana"}).status_code == 201


def test_a_recheck_withdraws_the_sign_off_as_it_starts(world):
    from tests.conftest import accept_all
    cid = world.case()
    c = world.client
    accept_all(c, cid)
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 201
    assert world.row(cid)["signoff"] == "signed"
    r = c.post(f"/api/review/{cid}/recheck", json={"guideline_id": world.guideline, "by": "Dana"})
    assert r.status_code == 200, r.text
    d = world.doc(cid)
    assert d["state"] == "paused" and world.row(cid)["signoff"] != "signed"
    rec = d["signoff"]["record"] if d["signoff"].get("record") else __import__("app.signoff", fromlist=["x"]).load(cid)
    assert rec["withdrawn"]["why"] == "re-check"


def test_new_accepts_and_sign_offs_name_the_tree_they_were_made_on(world):
    """status.json's tree {criteria_key, step_h, model, run_id} is stamped on each new accept and sign-off record;
    a case with no tree on its status reads nulls. Fingerprints are untouched."""
    import json
    from app import accepts, signoff, status, store
    cid = world.case()
    c = world.client
    t = status.load_status(cid)["tree"]
    want = {k: t[k] for k in ("criteria_key", "step_h", "model", "run_id")}
    assert want["criteria_key"] and want["run_id"]
    fp = signoff.fingerprint(cid)
    accept_all(c, cid)
    assert all(x["tree"] == want for x in accepts.active(cid))
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 201
    rec = json.loads((store.RESULTS / cid / "signoff.json").read_text())
    assert rec["tree"] == want and rec["fingerprint"] == signoff.fingerprint(cid) != fp
    doc = status.load_status(cid)
    doc.pop("tree")
    status.status_path(cid).write_text(json.dumps(doc))
    assert accepts.tree_of(cid) == {"criteria_key": None, "step_h": None, "model": None, "run_id": None}
