"""Admin leaves (app/admin.py): step H's `admin` flag prunes billing / paperwork / heading lines from a case's logic
before strikes, with guards; the case page lists them as `set_aside`; "Ask it anyway" restores one with one judge
call; ADMIN_PRUNE=0 is today's behaviour. Offline: the stub model, the store and feedback in tmp_path."""
from __future__ import annotations

import json

from app import admin, feedback, store
from app.evaluate import leaf_ids
from app.models import CriteriaSet, Criterion, Expression
from tests.conftest import accept_all
from tests.fake import reimburse_line
from tests.test_strikes import world  # noqa: F401  (the review-flow fixture)


def _cs(expr, admin_ids):
    ids = sorted({*admin_ids, *leaf_ids(expr)})
    crit = [Criterion(id=i, refs=[], question=i, admin=i in admin_ids,
                      admin_why="billing or coding" if i in admin_ids else None) for i in ids]
    return CriteriaSet(key="k", criteria=crit, expressions=[Expression(pathway="p", expr=expr)])


def test_prune_and_its_guards(tmp_store):
    # an admin leaf under an all goes; the others stay
    cs, why = admin.split("c", _cs({"all": ["a", "bill", "b"]}, {"bill"}), ["p"])
    assert cs.expressions[0].expr == {"all": ["a", "b"]} and why == {"bill": "billing or coding"}
    # never the only leaf of an alternative of an any / at_least, never the whole expression
    assert admin.split("c", _cs({"all": ["a", {"any": ["bill", "b"]}]}, {"bill"}), ["p"])[1] == {}
    cs, why = admin.split("c", _cs({"any": ["b", {"all": ["bill", "doc"]}]}, {"bill", "doc"}), ["p"])
    assert cs.expressions[0].expr == {"any": ["b", "doc"]} and set(why) == {"bill"}   # the alternative keeps one
    assert admin.split("c", _cs({"at_least": {"k": 1, "of": ["bill", "b"]}}, {"bill"}), ["p"])[1] == {}
    assert admin.split("c", _cs({"all": ["bill", "doc"]}, {"bill", "doc"}), ["p"])[1] == {"bill": "billing or coding"}
    # every judged section keeps a requirement: a leaf shared by two sections goes only if both keep one
    two = _cs({"all": ["a", "bill"]}, {"bill"}).model_copy(update={"expressions": [
        Expression(pathway="p", expr={"all": ["a", "bill"]}), Expression(pathway="q", expr="bill")]})
    assert admin.split("c", two, ["p", "q"])[1] == {} and set(admin.split("c", two, ["p"])[1]) == {"bill"}
    assert admin.split("c", _cs("bill", {"bill"}), ["p"])[1] == {}
    # inside an alternative with other leaves it may go
    cs, why = admin.split("c", _cs({"any": ["b", {"all": ["c", "bill"]}]}, {"bill"}), ["p"])
    assert cs.expressions[0].expr == {"any": ["b", "c"]} and set(why) == {"bill"}
    # never under a NOT: exclusions are always asked
    assert admin.split("c", _cs({"all": ["a", {"not": "bill"}]}, {"bill"}), ["p"])[1] == {}
    # a reason outside the three reads as the default
    c = Criterion(id="x", refs=[], question="x", admin=True, admin_why="something")
    assert admin.why_of(c) == admin.DEFAULT_WHY


def test_off_is_exactly_today(tmp_store, monkeypatch):
    cs0 = _cs({"all": ["a", "bill"]}, {"bill"})
    monkeypatch.setenv("ADMIN_PRUNE", "0")
    cs, why = admin.split("c", cs0, ["p"])
    assert cs is cs0 and why == {}


BILL = lambda g: {"id": "bill", "refs": [reimburse_line(g)], "quote": "Reimburse according to operative report.",
                  "question": "Billed per operative report?", "admin": True, "admin_why": "billing or coding"}


def _case(world, fl_spans, **kw):
    return world.case(extra_criteria=[BILL(fl_spans)], **kw)


def test_admin_leaf_is_set_aside_not_asked(world, fl_spans):
    cid = _case(world, fl_spans, verdicts={"bill": {"status": "INSUFFICIENT"}})
    d = world.doc(cid)
    reqs = {x["criterion"] for x in d["case"]["requirements"]}
    assert "bill" not in reqs and "reflux" in reqs
    (sa,) = d["case"]["set_aside"]
    assert sa["criterion"] == "bill" and sa["why"] == "billing or coding" and "Reimburse" in sa["words"]
    assert sa["source"] and sa["source"]["page"]
    rec = store.load_result(cid)
    assert "bill" not in rec["verdicts"] and rec["result"]["queue"] == "ready"
    crit = json.loads((store.RESULTS / cid / "criteria.json").read_text())       # the pinned set keeps the flag
    assert next(c for c in crit["criteria"] if c["id"] == "bill")["admin"] is True


def test_the_judge_is_not_asked_about_it(world, fl_spans, monkeypatch):
    from app import llm
    cid = _case(world, fl_spans)
    stub = llm.call
    assert any(s == "judge_chart" for s, _ in stub.prompts)
    seen = [p for s, p in stub.prompts if s == "judge_chart"]
    assert seen and all('"bill"' not in p for p in seen)
    assert cid


def test_admin_prune_off_restores_today(world, fl_spans, monkeypatch):
    plain = dict(BILL(fl_spans), admin=False)
    a = world.case(extra_criteria=[plain], verdicts={"bill": {"status": "INSUFFICIENT"}})
    da = world.doc(a)
    monkeypatch.setenv("ADMIN_PRUNE", "0")
    b = _case(world, fl_spans, verdicts={"bill": {"status": "INSUFFICIENT"}})
    db = world.doc(b)
    assert db["case"]["set_aside"] == [] and "bill" in {x["criterion"] for x in db["case"]["requirements"]}
    ra, rb = store.load_result(a), store.load_result(b)
    for k in ("determination", "queue", "misses", "review_reasons"):
        assert ra["result"].get(k) == rb["result"].get(k), k
    assert ra["verdicts"] == rb["verdicts"]
    assert [x["criterion"] for x in da["case"]["requirements"]] == [x["criterion"] for x in db["case"]["requirements"]]


def test_ask_it_anyway_and_set_it_aside_again(world, fl_spans):
    from app import llm
    cid = _case(world, fl_spans, verdicts={"bill": {"status": "INSUFFICIENT"}})
    accept_all(world.client, cid)
    assert world.client.post(f"/api/review/{cid}/signoff", json={"by": "Dana"}).status_code in (200, 201)
    n = llm.call.calls.count("judge_chart")
    c = world.client
    assert c.post(f"/api/review/{cid}/unprune", json={"criterion": "reflux", "by": "Dana"}).status_code == 400
    r = c.post(f"/api/review/{cid}/unprune", json={"criterion": "bill", "by": "Dana"})
    assert r.status_code == 201, r.text
    assert llm.call.calls.count("judge_chart") == n + 1                              # one judge call for that leaf
    (one,) = [p for s, p in llm.call.prompts if s == "judge_chart"][n:]
    assert '"bill"' in one and '"reflux"' not in one
    d = r.json()
    bill = next(x for x in d["case"]["requirements"] if x["criterion"] == "bill")
    assert bill["bad"] and d["case"]["set_aside"] == []
    assert d["case"]["result"]["queue"] != "ready" and d["signoff"]["state"] != "signed"
    assert d["signoff"]["record"]["withdrawn"]["why"] == "asked anyway"
    rec = json.loads((store.RESULTS / cid / "unpruned.json").read_text())["unpruned"][0]
    assert rec["by"] == "Dana" and rec["at"] and rec["verdict"]["status"] == "INSUFFICIENT"
    assert any(f["kind"] == "should_be_requirement" and f.get("unprune") == rec["id"] for f in feedback.list_for(cid))
    r = c.delete(f"/api/review/{cid}/unprune/bill", params={"by": "Dana"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert [x["criterion"] for x in d["case"]["set_aside"]] == ["bill"] and d["case"]["result"]["queue"] == "ready"
    assert not any(f.get("unprune") == rec["id"] for f in feedback.list_for(cid))
    assert c.delete(f"/api/review/{cid}/unprune/bill").status_code == 404
