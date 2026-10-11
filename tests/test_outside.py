"""Things the chart can't show: requirements the checklist builder marked unanswerable (`answerable: false`) read
"Confirm outside the chart" with one sentence of why; "Confirmed outside the chart" records who and when like an
accept and counts toward sign-off, and a documented case whose only review reasons are these can be signed off once
each is confirmed (signoff.ready). Offline: the stub with `unanswerable=True` (tests/fake.unanswerable_criteria)."""
from __future__ import annotations

import pytest

from app import review, signoff
from tests.test_strikes import reqs, world  # noqa: F401  (the review-flow fixture)


def test_unanswerable_requirements_read_confirm_outside_the_chart(world):
    d = world.doc(world.case(unanswerable=True))
    res = d["case"]["result"]
    assert res["determination"] == "MET" and res["queue"] == "review"
    assert len(res["confirm_reasons"]) == 2 and res["review_reasons"] == res["confirm_reasons"]
    r = reqs(d)
    for cid in ("necessity", "op_report"):
        assert r[cid]["mark"] == "confirm" and r[cid]["say"] == "Confirm outside the case" and r[cid]["proof"]
        assert r[cid]["counted"] and r[cid]["evidence"] == []
    assert r["necessity"]["why_outside"] == "This is the plan's judgement, not something a case records."
    assert "claim" in r["op_report"]["why_outside"]
    assert r["necessity"]["source"]["say"].startswith("Cited: Great or Small Saphenous Veins, p. ") and not r["necessity"]["source"]["other"]
    assert r["op_report"]["source"]["other"] and r["op_report"]["source"]["say"] == "Cited: Reimbursement information, p. 7"   # v1.2: no always_on; the line is outside the section
    assert all(x["why_outside"] is None for k, x in r.items() if k not in ("necessity", "op_report"))
    # nothing but these to look at: it waits for sign-off, and the rail puts it there
    assert d["signoff"]["state"] == "needed" and d["signoff"]["ready"] and not d["signoff"]["can_sign"]
    assert world.row(d["chart_id"])["signoff"] == "needed"


def test_confirmed_outside_the_chart_counts_toward_sign_off(world):
    cid = world.case(unanswerable=True)
    c = world.client
    others = [k for k, x in reqs(world.doc(cid)).items() if x["counted"] and x["mark"] not in ("confirm", "struck")]
    for k in others:
        assert c.post(f"/api/review/{cid}/accepts", json={"criterion": k, "by": "Dana"}).status_code == 201
    d = world.doc(cid)
    assert set(d["case"]["progress"]["open"]) == {"necessity", "op_report"}
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"})
    assert r.status_code == 409 and "still open" in r.json()["detail"]
    # confirm both: who and when, like an accept
    c.post(f"/api/review/{cid}/accepts", json={"criterion": "necessity", "by": "Lee"})
    d = c.post(f"/api/review/{cid}/accepts", json={"criterion": "op_report", "by": "Dana"}).json()
    nec = reqs(d)["necessity"]
    assert nec["accepted"]["by"] == "Lee" and nec["accepted"]["at"] and nec["in_ask"] is None
    assert d["case"]["progress"]["can_sign"] and d["signoff"]["can_sign"]
    assert {x["criterion"] for x in d["case"]["packet_accepted"]} >= {"necessity", "op_report"}
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"})
    assert r.status_code == 201, r.text
    assert r.json()["signoff"]["state"] == "signed"
    # taking a confirmation back withdraws the sign-off and the case cannot be signed until it is confirmed again
    d = c.delete(f"/api/review/{cid}/accepts/{nec['accepted']['id']}?by=Lee").json()
    assert d["signoff"]["state"] == "needed" and not d["case"]["progress"]["can_sign"]


def test_a_gap_beside_them_still_keeps_the_case_from_sign_off(world):
    d = world.doc(world.case(unanswerable=True, verdicts={"size": {"status": "INSUFFICIENT"}}))
    assert d["case"]["result"]["determination"] == "INSUFFICIENT" and d["signoff"]["state"] == "not_ready"


@pytest.mark.parametrize("r, ok", [
    ({"queue": "ready", "determination": "MET"}, True),
    ({"queue": "review", "determination": "MET", "review_reasons": ["a"], "confirm_reasons": ["a"]}, True),
    ({"queue": "review", "determination": "MET", "review_reasons": ["a", "b"], "confirm_reasons": ["a"]}, False),
    ({"queue": "review", "determination": "MET", "review_reasons": ["a"]}, False),               # saved before the field
    ({"queue": "review", "determination": "INSUFFICIENT", "review_reasons": ["a"], "confirm_reasons": ["a"]}, False),
    ({"queue": "review", "determination": "MET", "review_reasons": []}, False),
    (None, False),
])
def test_ready_to_sign_off(r, ok):
    assert signoff.ready(r) is ok


def test_why_a_chart_cannot_show_it():
    w = review.outside_why
    assert w("meets the definition of medical necessity") == "This is the plan's judgement, not something a case records."
    assert "device" in w("using a U.S. FDA-approved/cleared device")
    assert "provider or the facility" in w("The surgeon is board certified in vascular surgery")
    assert "member's plan" in w("subject to the member's benefit terms, limitations and maximums")
    assert "claim" in w("Reimburse according to operative report")
    assert "claim" in w("Something odd", {"part": "Reimbursement information"})
    assert w("Something odd") == "A case doesn't record this; confirm it with the plan or the practice."
