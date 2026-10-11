"""Requirements whose quoted guideline words are identical are ONE item, decided together (accepted, added to the ask,
struck, undone: never split by evidence); ones that overlap or sit back to back are one run (`near`). We don't judge,
the human does. Offline: the stub model and the store in tmp_path; Delgado against the FL guideline."""
from __future__ import annotations

from tests.fake import ps
from tests.test_strikes import world, reqs  # noqa: F401  (the review-flow fixture)


def dup(fl_spans):
    """"size" cited twice: a second criterion with exactly the same words."""
    return {"id": "size2", "refs": [ps(fl_spans, "The varicosities are at least 3 millimeters")],
            "quote": "The varicosities are at least 3 millimeters in size", "question": "Varicosities >= 3 mm, again?"}


def test_adjacent_requirements_group_as_a_run_and_size_stays_alone(world):
    d = world.doc(world.case())
    r = reqs(d)
    assert r["reflux"]["near"] == r["ceap"]["near"] and {"reflux", "ceap"} <= set(r["reflux"]["near"])        # back to back: " and "
    assert r["reflux"]["near"] == ["reflux", "ceap"] and r["adl"]["near"] == ["symptoms", "adl", "compression"]
    assert "same" not in r["size"] and "near" not in r["size"]                                                  # a new bullet starts another item
    assert all("near" not in r[k] for k in ("ulcer", "thromb", "hem"))                                          # "2. " is not a joiner
    assert d["case"]["progress"]["total"] == 6                                                                  # near ones still count one by one


def test_identical_requirements_are_one_item_decided_together(world, fl_spans):
    cid = world.case(extra_criteria=[dup(fl_spans)])
    c = world.client
    d = world.doc(cid)
    r = reqs(d)
    assert r["size"]["same"] == r["size2"]["same"] == ["size", "size2"]
    assert d["case"]["progress"]["total"] == 6 and d["case"]["progress"]["of"] == 6          # counted once, as without the twin
    # accepted together, one action; the twin is recorded with whom it was decided
    d = c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "together": ["size2"], "by": "Dana"}).json()
    r = reqs(d)
    assert r["size"]["accepted"] and r["size2"]["accepted"] and d["case"]["progress"]["accepted"] == 1
    twin = next(a for a in d["accepts"] if a["criterion"] == "size2" and not a["undone"])
    assert twin["note"] == "accepted together with size"
    assert c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "together": ["size2"], "by": "Dana"}).status_code == 409
    for a in (r["size"]["accepted"], r["size2"]["accepted"]):                                  # undone (the page undoes each id)
        d = c.delete(f"/api/review/{cid}/accepts/{a['id']}?by=Dana").json()
    r = reqs(d)
    assert not r["size"]["accepted"] and not r["size2"]["accepted"] and d["case"]["progress"]["accepted"] == 0
    # struck together
    for k in ("size", "size2"):
        d = world.strike(cid, k, reason="Not for this vein.")
    r = reqs(d)
    assert r["size"]["mark"] == r["size2"]["mark"] == "struck" and d["case"]["progress"]["struck"] == 1
    # a twin that is not on the same words is refused
    assert c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "together": ["reflux"], "by": "Dana"}).status_code == 400


def test_a_pair_with_mixed_evidence_is_accepted_or_asked_together(world, fl_spans):
    c = world.client
    v = {"size2": {"status": "INSUFFICIENT", "for": []}}
    cid = world.case(extra_criteria=[dup(fl_spans)], verdicts=v)
    r = reqs(world.doc(cid))
    assert r["size"]["proof"] and not r["size2"]["proof"] and r["size"]["same"] == ["size", "size2"]
    # Accept: both accepted, though the chart shows nothing for one of them: the person decided
    d = c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "together": ["size2"], "by": "Dana"}).json()
    r = reqs(d)
    assert r["size"]["accepted"] and r["size2"]["accepted"] and not r["size2"]["in_ask"] and d["case"]["progress"]["accepted"] == 1
    assert "accepted together with size" in [a["note"] for a in d["accepts"]]
    for k in ("size", "size2"):
        d = c.delete(f"/api/review/{cid}/accepts/{reqs(d)[k]['accepted']['id']}?by=Dana").json()
    # Add to the ask: both in the ask, though the chart documents one of them
    d = c.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "together": ["size2"], "ask": True, "by": "Dana"}).json()
    r = reqs(d)
    assert r["size"]["in_ask"] and r["size2"]["in_ask"] and not r["size"]["accepted"] and d["case"]["progress"]["in_ask"] == 1
    for k in ("size", "size2"):
        d = c.delete(f"/api/review/{cid}/accepts/{reqs(d)[k]['in_ask']['id']}?by=Dana").json()
    r = reqs(d)
    assert not r["size"]["in_ask"] and not r["size2"]["in_ask"] and r["size"]["proof"] and not r["size2"]["proof"]
