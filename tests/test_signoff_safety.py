"""The sweep's safety fixes on the review flow: a gap strike needs no reason (the human is the judge),
sign-off is tied to the version of the case the signer saw and refused when one already stands, removals made while
a requirement was not in the chart need an explicit check at sign-off, and the payer packet carries nothing about
removals (they go into a separate internal audit note). Offline: the stub model and tmp_path; never touches data/."""
from __future__ import annotations

from tests.conftest import accept_all
from tests.test_strikes import world  # noqa: F401  (the review-flow fixture)


def test_a_gap_strike_needs_no_reason(world):
    # the human is the judge: a requirement the chart does not document drops with no reason and no note (the ⌘⌫
    # key sends {criterion, by}); who and when are still kept
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT", "for": []}})
    r = world.client.post(f"/api/review/{cid}/strikes", json={"criterion": "size", "by": "Dana"})
    assert r.status_code == 201, r.text
    (sk,) = r.json()["strikes"]
    assert sk["by"] == "Dana" and sk["at"] and sk["was"] == "missing" and sk["reason"] == ""


def test_sign_off_is_tied_to_the_version_the_signer_saw(world):
    cid = world.case()
    c = world.client
    d = accept_all(c, cid)
    v = d["version"]
    assert v and v == world.doc(cid)["version"]                                      # stable while nothing changes
    # another tab changes the case (undo one accept, accept it again): the old version no longer signs
    size = next(x for x in d["case"]["requirements"] if x["criterion"] == "size")
    c.delete(f"/api/review/{cid}/accepts/{size['accepted']['id']}?by=Ann")
    d2 = accept_all(c, cid)
    assert d2["version"] != v
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana", "version": v})
    assert r.status_code == 409 and "changed" in r.json()["detail"]
    assert world.doc(cid)["signoff"]["state"] == "needed"
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana", "version": d2["version"]})
    assert r.status_code == 201, r.text
    assert r.json()["signoff"]["record"]["by"] == "Dana"


def test_a_second_sign_off_is_refused_while_one_stands(world):
    cid = world.case()
    c = world.client
    accept_all(c, cid)
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code == 201
    v = world.doc(cid)["version"]
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Bob", "version": v})
    assert r.status_code == 409 and r.json()["detail"] == "Already signed off by Dana"
    assert world.doc(cid)["signoff"]["record"]["by"] == "Dana"
    # taken back: a new sign-off is possible again
    assert c.delete(f"/api/review/{cid}/signoff?by=Dana").status_code == 200
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Bob", "version": world.doc(cid)["version"]}).status_code == 201


def test_a_long_name_is_cut_to_sixty_characters(world):
    cid = world.case()
    c = world.client
    accept_all(c, cid)
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "D" * 200})
    assert r.status_code == 201 and len(r.json()["signoff"]["record"]["by"]) == 60


def test_removed_while_missing_needs_an_explicit_check_and_never_disappears(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT", "for": []}})
    c = world.client
    world.strike(cid, "size", reason="Measured in clinic, not needed for this vein.")
    d = accept_all(c, cid)
    assert d["signoff"]["can_sign"] and d["signoff"]["gaps"] == 1
    assert world.row(cid)["removed_missing"] == 1
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana", "version": d["version"]})
    assert r.status_code == 400 and "removed" in r.json()["detail"]                   # no explicit check: refused
    assert world.doc(cid)["signoff"]["state"] == "needed"
    r = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana", "version": d["version"], "gaps_checked": True})
    assert r.status_code == 201, r.text
    so = r.json()["signoff"]
    assert so["state"] == "signed" and so["gaps"] == 1 and so["record"]["gaps_checked"] and len(so["record"]["gaps"]) == 1
    # after sign-off the rail row and the document still say it
    assert world.row(cid)["removed_missing"] == 1 and world.row(cid)["signoff"] == "signed"
    assert world.doc(cid)["signoff"]["gaps"] == 1


def test_no_check_is_needed_when_nothing_missing_was_removed(world):
    cid = world.case()
    c = world.client
    world.strike(cid, "ulcer", reason="No ulcer pathway for this patient.")
    d = accept_all(c, cid)
    assert d["signoff"]["gaps"] == 0
    assert c.post(f"/api/review/{cid}/signoff", json={"by": "Dana", "version": d["version"]}).status_code == 201


def test_the_packet_holds_accepted_quotes_and_the_signer_and_nothing_about_removals(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT", "for": []}})
    c = world.client
    world.strike(cid, "size", reason="Measured in clinic, not needed for this vein.")
    world.strike(cid, "ulcer", reason="No ulcer pathway for this patient.")
    d = accept_all(c, cid)
    pk, audit = d["case"]["packet_text"], d["case"]["audit_note"]
    assert pk.startswith("Prior authorization — ") and "Supporting documentation:" in pk
    assert '"' in pk and "Signed off" not in pk                                        # quotes; not signed yet
    for word in ("Removed", "removed", "Measured in clinic", "not documented", "3 millimeters"):
        assert word not in pk, word
    # the audit note is apart: every removal, its reason and who, and that the chart did not document one of them
    assert audit.startswith("Audit note (internal, not for the payer)")
    assert "Measured in clinic, not needed for this vein." in audit and "No ulcer pathway for this patient." in audit
    assert audit.count("not documented in the case") == 1 and "(removed by Dana" in audit
    d = c.post(f"/api/review/{cid}/signoff", json={"by": "Dana", "version": d["version"], "gaps_checked": True}).json()
    pk, audit = d["case"]["packet_text"], d["case"]["audit_note"]
    assert pk.rstrip().splitlines()[-1].startswith("Signed off by Dana on ") and "removed" not in pk.lower()
    assert "Signed off by Dana" in audit and "checked the 1 requirement removed while not in the case" in audit


def test_no_audit_note_when_nothing_was_removed_or_added(world):
    cid = world.case()
    d = accept_all(world.client, cid)
    assert d["case"]["audit_note"] == "" and d["case"]["packet_text"].count("\n1. ") == 1


def test_pretty_heading_matches_the_page():
    from app.review.review import pretty_heading
    assert pretty_heading("Visit Date: September 30, 2025 | Attending: Dr. X | Type: Follow-Up") == "Follow-Up visit, September 30, 2025"
    assert pretty_heading("7. PHYSICAL EXAMINATION") == "Physical Examination"
    assert pretty_heading("") == ""


def test_a_bad_case_id_is_no_such_chart_not_a_500(world):
    c = world.client
    for bad in ("x" * 300, "a b", "abc$", "..%2Fetc"):
        assert c.get(f"/api/review/{bad}").status_code == 404, bad
        assert c.post(f"/api/review/{bad}/signoff", json={"by": "Dana"}).status_code == 404, bad
    assert c.get("/review/" + "x" * 300).status_code == 200           # the page itself says "No case with this id"
