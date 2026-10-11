"""The Tree view's outline (app/review/tree.outline): the case's logic after strikes and additions, each group's status
compiled from its children by code (met · ask · open · contradicted), options made unneeded dimmed, the root's
status and what it waits on. Offline: the stub model and tmp_path stores, never data/."""
from __future__ import annotations

from app.decide.evaluate import compile_expr
from app.core.models import Verdict
from app.review.tree import outline, outline_case
from tests.test_strikes import world  # noqa: F401  (the review-flow fixture)

ST = {"y": "MET", "n": "NOT_MET", "?": "INSUFFICIENT"}


def run(expr, marks: dict[str, str], reqs: dict[str, dict] | None = None) -> dict:
    v = {k: Verdict(criterion=k, status=ST[s], confidence=0.9) for k, s in marks.items()}
    return outline(expr, compile_expr(expr, v), reqs or {})


def req(proof: bool, in_ask: bool = False, mark: str = "documented", counted: bool = True) -> dict:
    return {"proof": proof, "in_ask": {"id": "a1"} if in_ask else None, "mark": mark, "counted": counted}


def test_all_any_compile_from_children():
    e = {"all": ["a", {"any": ["b", "c"]}]}
    t = run(e, {"a": "y", "b": "y", "c": "?"})
    assert t["op"] == "all" and t["status"] == "met"
    alt = t["kids"][1]
    assert alt["op"] == "any" and alt["status"] == "met"
    assert alt["kids"][0]["dim"] is None and alt["kids"][1]["dim"] == "not_needed"   # another option is met
    t = run(e, {"a": "?", "b": "n", "c": "n"})
    assert t["kids"][1]["status"] == "contradicted" and t["status"] == "contradicted"
    t = run(e, {"a": "y", "b": "?", "c": "n"})
    assert t["status"] == "open" and t["kids"][1]["status"] == "open"
    # nothing documented yet: no option is dimmed; the one off the deciding path is its own route to verify
    assert [k["dim"] for k in t["kids"][1]["kids"]] == [None, None]
    assert not t["kids"][1]["kids"][0].get("route") and t["kids"][1]["kids"][1]["route"]


def test_waiting_on_the_ask_only_when_everything_open_is_in_it():
    e = {"all": ["a", "b", "c"]}
    marks = {"a": "y", "b": "?", "c": "?"}
    reqs = {"a": req(True), "b": req(False, in_ask=True, mark="missing"), "c": req(False, mark="missing")}
    assert run(e, marks, reqs)["status"] == "open"                    # c is not in the ask yet
    reqs["c"] = req(False, in_ask=True, mark="missing")
    t = run(e, marks, reqs)
    assert t["status"] == "ask" and [k["status"] for k in t["kids"]] == ["met", "ask", "ask"]


def test_exclusions_read_from_the_requirement_side():
    # none of these may apply: each item ruled out is met; one shown applies is contradicted; nothing dimmed
    e = {"all": ["a", {"not": {"any": ["x", "y"]}}]}
    t = run(e, {"a": "y", "x": "n", "y": "n"})
    none = t["kids"][1]
    assert none["op"] == "none" and none["status"] == "met" and t["status"] == "met"
    assert [k["status"] for k in none["kids"]] == ["met", "met"] and all(k["dim"] is None for k in none["kids"])
    t = run(e, {"a": "y", "x": "y", "y": "n"})
    none = t["kids"][1]
    assert none["status"] == "contradicted" and [k["status"] for k in none["kids"]] == ["contradicted", "met"]
    assert all(k["dim"] is None for k in none["kids"])               # under a "not", every item is read
    t = run(e, {"a": "y", "x": "?", "y": "n"})
    assert t["kids"][1]["status"] == "open" and t["status"] == "open"
    # a single exclusion and a compound one ("X without Y": not all of these together)
    t = run({"not": "x"}, {"x": "n"})
    assert t["op"] == "none" and t["status"] == "met" and t["kids"][0]["criterion"] == "x"
    t = run({"not": {"all": ["x", "y"]}}, {"x": "y", "y": "n"})
    assert t["op"] == "not_all" and t["status"] == "met"
    t = run({"not": {"all": ["x", "y"]}}, {"x": "y", "y": "y"})
    assert t["status"] == "contradicted"


def test_at_least_k_of_n():
    e = {"at_least": {"k": 2, "of": ["a", "b", "c"]}}
    t = run(e, {"a": "y", "b": "y", "c": "?"})
    assert t["op"] == "at_least" and t["k"] == 2 and t["n"] == 3 and t["status"] == "met"
    assert [k["dim"] for k in t["kids"]] == [None, None, "not_needed"]
    t = run(e, {"a": "y", "b": "?", "c": "n"})
    assert t["status"] == "open" and t["kids"][1]["dim"] is None and t["kids"][2]["dim"] is None and t["kids"][2]["route"]
    t = run(e, {"a": "y", "b": "n", "c": "n"})
    assert t["status"] == "contradicted"


def test_cms_shape_exclusions_and_at_least_under_all():
    """The NCD's shape: requirements, an at_least, and a "none of these" exclusion, all under one all."""
    e = {"all": ["dx", {"at_least": {"k": 2, "of": ["s1", "s2", "s3"]}}, {"not": {"any": ["e1", "e2"]}}]}
    v = {"dx": "y", "s1": "y", "s2": "?", "s3": "?", "e1": "n", "e2": "?"}
    reqs = {"dx": req(True), "s1": req(True), "s2": req(False, mark="missing"), "s3": req(False, mark="other_option", counted=False),
            "e1": req(True, mark="clear"), "e2": req(False, in_ask=True, mark="unclear")}
    vv = {k: Verdict(criterion=k, status=ST[s], confidence=0.9) for k, s in v.items()}
    root = outline_case([("p", "Section", e)], vv, reqs)
    t = root["sections"][0]["tree"]
    assert [k["status"] for k in t["kids"]] == ["met", "open", "ask"]
    assert root["status"] == "open" and root["waiting"] == ["s2", "e2"]
    reqs["s2"] = req(False, in_ask=True, mark="missing")
    root = outline_case([("p", "Section", e)], vv, reqs)
    assert root["status"] == "ask" and root["sections"][0]["tree"]["status"] == "ask"


def test_the_case_carries_its_logic_and_it_follows_accepts(world):
    cid = world.case()
    lg = world.doc(cid)["case"]["logic"]
    assert lg["status"] == "met" and lg["waiting"] == []
    t = lg["sections"][0]["tree"]
    assert lg["sections"][0]["name"] and t["op"] == "all"
    alt = next(k for k in t["kids"] if k.get("op") == "any")
    # another option is documented, but nobody accepted it yet: nothing is set aside
    assert alt["status"] == "met" and {k["dim"] for k in alt["kids"]} == {None}
    reqs = {x["criterion"]: x for x in world.doc(cid)["case"]["requirements"]}
    unneeded = [k for k, x in reqs.items() if x["mark"] == "not_needed"]
    assert unneeded and all(reqs[k]["dim"] is None and not reqs[k]["counted"] for k in unneeded)
    for k in world.doc(cid)["case"]["progress"]["open"]:                                # a person accepts the documented ones
        d = world.client.post(f"/api/review/{cid}/accepts", json={"criterion": k, "by": "Dana"}).json()
    alt = next(k for k in d["case"]["logic"]["sections"][0]["tree"]["kids"] if k.get("op") == "any")
    assert {k["dim"] for k in alt["kids"]} == {None, "not_needed"}                     # accepted: the others step back
    assert all({x["criterion"]: x for x in d["case"]["requirements"]}[k]["dim"] == "not_needed" for k in unneeded)
    # a missing requirement: the root waits on it until it is in the ask, and agrees with progress
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT", "for": []}})
    d = world.doc(cid)
    lg = d["case"]["logic"]
    assert lg["status"] == "open" and lg["waiting"] == ["size"] == d["case"]["progress"]["asks"]
    d = world.client.post(f"/api/review/{cid}/accepts", json={"criterion": "size", "by": "Dana"}).json()
    assert d["case"]["logic"]["status"] == "ask" and d["case"]["logic"]["waiting"] == ["size"]


def test_a_struck_requirement_leaves_the_logic(world):
    cid = world.case(verdicts={"size": {"status": "INSUFFICIENT", "for": []}})
    d = world.strike(cid, "size", reason="Measured on the other leg; not needed here.")
    lg = d["case"]["logic"]
    leaves = []

    def walk(n):
        if "criterion" in n:
            leaves.append(n["criterion"])
        else:
            for k in n["kids"]:
                walk(k)
    walk(lg["sections"][0]["tree"])
    assert "size" not in leaves and lg["status"] == "met"


def test_an_exemption_route_is_never_dimmed_when_nothing_is_documented(world):
    """The main route missing and the other route (an exemption) without evidence either: both need attention, both
    counted; the other one carries `route` ("Or: another route; needs its own evidence"), never "another option"."""
    cid = world.case(verdicts={"symptoms": {"status": "INSUFFICIENT", "for": []}})
    d = world.doc(cid)
    reqs = {x["criterion"]: x for x in d["case"]["requirements"]}
    assert not any(x["mark"] == "other_option" for x in reqs.values())
    routes = [k for k, x in reqs.items() if x["route"]]
    assert routes and all(reqs[k]["counted"] and reqs[k]["mark"] in ("missing", "contradicted", "unclear") for k in routes)
    assert set(routes) <= set(d["case"]["progress"]["asks"]) and "symptoms" in d["case"]["progress"]["asks"]
    alt = next(k for k in d["case"]["logic"]["sections"][0]["tree"]["kids"] if k.get("op") == "any")
    assert all(k["dim"] is None for k in alt["kids"])


def test_a_review_reason_sits_on_its_requirement(world):
    """Step J's reasons (notes for and against one requirement) travel with that requirement, so the page can say
    them on its row and in its panel instead of a block under the header."""
    cid = world.case(verdicts={"ceap": {"status": "MET", "for": ["r0040"], "against": ["r0041"]}})
    d = world.doc(cid)
    reqs = {x["criterion"]: x for x in d["case"]["requirements"]}
    assert any("for and against" in t for t in reqs["ceap"]["reasons"])
    assert all(not x["reasons"] for k, x in reqs.items() if k != "ceap")
    assert any("for and against" in t for t in d["case"]["result"]["review_reasons"])   # still a review reason
