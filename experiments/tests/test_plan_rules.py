"""The member's plan reaches every step-H arm (and prunes nothing by itself), the host's not-covered rule in every arm,
and form's range feedback. Pure: fake models, tmp_path run logs."""
from __future__ import annotations

import json

import pytest

from app.checklist import keys
from app.checklist import criteria
from app.core import llm
from experiments.stepH import reduce_code, reduce_script, reduce_tools
from app.core.models import Procedure
from experiments.stepH.sandbox import helpers
from app.ingest.spans import split_guideline
from experiments.tests.test_reduce_code import _sel, tree
from experiments.tests.test_reduce_tools import WIDGET, FakeClient, sel_for

PLAN = "Florida Blue commercial (not a Federal Employee Program (FEP) member; not a State Account Organization (SAO) member)"
RULE = "The order states the member's plan."


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "RUNS", tmp_path / "runs")
    return tmp_path


def proc(**kw):
    return Procedure(cpt=["99999"], plan=PLAN, **kw)


# ---------------------------------------------------------------- the plan reaches every arm


def test_plan_in_order_and_cache_key():
    assert json.loads(reduce_code.order_json(proc()))["plan"] == PLAN
    assert "plan: " + PLAN in criteria.request_line(proc())
    a, b = keys.cache_key("s" * 64, Procedure(cpt=["99999"])), keys.cache_key("s" * 64, proc())
    assert a != b and b.startswith(a.split("-mgpt")[0] + "-p")    # a plan never reuses a tree built without one


@pytest.mark.parametrize("mod", [reduce_tools, reduce_script])
def test_tools_and_script_send_plan_and_rule(offline, monkeypatch, mod):
    fake = FakeClient([[("show", {})]], [[("show", {})]])
    monkeypatch.setattr(llm, "client", lambda: fake)
    n, sel = sel_for()
    mod.build(split_guideline(WIDGET), n, sel, "k", "run1", proc())
    order = json.loads(fake.sent[0]["input"].split("## The order\n", 1)[1].split("## Codes")[0])
    assert order["plan"] == PLAN and RULE in fake.sent[0]["instructions"]


def test_code_form_and_loose_send_plan_and_rule(fl_spans, offline, monkeypatch):
    from experiments.tests.test_reduce_code import FakeSession
    n, sel = _sel(fl_spans)
    s = FakeSession([tree()])
    monkeypatch.setattr(llm, "CodeSession", s)
    reduce_code.build(fl_spans, n, sel, "k", "r", proc(), mode="code")
    assert json.loads(s.files["order.json"])["plan"] == PLAN and RULE in s.files["BRIEF.md"].decode()

    sent = []

    def fake(run_id, step, prompt, schema, **_):
        sent.append((step, prompt))
        if step == "criteria_form":
            return schema.model_validate(tree())
        if step == "criteria_guideline":
            return schema.model_validate({"notes": "", "criteria": [{"id": "reflux", "quote": "There is demonstrated "
                                          "saphenous reflux", "refs": [], "question": "?"}],
                                          "logic": [{"pathway": p, "logic": "reflux"} for p in criteria.picked(sel)]})
        return schema.model_validate({})
    monkeypatch.setattr(llm, "call", fake)
    reduce_code.build(fl_spans, n, sel, "k", "r", proc(), mode="form")
    criteria.build(fl_spans, n, sel, "k", "r", proc())
    for step in ("criteria_form", "criteria_guideline"):
        p = next(x for s_, x in sent if s_ == step)
        assert PLAN in p and RULE in p, step


# ---------------------------------------------------------------- the not-covered rule (host, every arm)


def test_not_covered_rule():
    q = "experimental or investigational for members who do not meet the criteria"
    problem, note = reduce_code.not_covered(q, declared=True)
    assert problem is None and q in note
    problem, note = reduce_code.not_covered(q, declared=False)
    assert "not covered" in problem and note is None
    assert reduce_code.not_covered(None, False) == (None, None)


def test_code_arm_keeps_indications_over_a_not_covered_quote(fl_spans, offline, monkeypatch):
    from experiments.tests.test_reduce_code import FakeSession
    n, sel = _sel(fl_spans)
    nc = "There is demonstrated saphenous reflux"          # any printed sentence; only the flag is under test
    monkeypatch.setattr(llm, "CodeSession", FakeSession([tree(not_covered=nc)]))
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", proc(), mode="code")
    assert not any("not covered" in p for p in cs.problems) and "Not-covered sentence quoted" in cs.notes
    monkeypatch.setattr(llm, "CodeSession", FakeSession([tree(not_covered=nc, expression=None, conditions=[])]))
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", proc(), mode="code")
    assert any("reads this order as not covered" in p for p in cs.problems)


def test_tools_and_script_not_covered_rule(offline, monkeypatch):
    from experiments.tests.test_reduce_script import example
    _, r2, _ = example()
    nc = 'not_covered("investigational")\n'
    fake = FakeClient([[("submit", {"script": r2 + nc})]], [[("submit", {"script": r2 + nc})]])
    monkeypatch.setattr(llm, "client", lambda: fake)
    n, sel = sel_for()
    cs = reduce_script.build(split_guideline(WIDGET), n, sel, "k", "run1", proc())
    assert not any("not covered" in p for p in cs.problems) and "Not-covered sentence quoted" in cs.notes
    st = reduce_tools.State(split_guideline(WIDGET))
    st.not_covered = "investigational"
    assert reduce_code.not_covered(st.not_covered, bool(st.logic or st.quotes))[0]   # nothing declared: flagged


# ---------------------------------------------------------------- form: a range is two conditions


def test_range_threshold_feedback(fl_spans, monkeypatch):
    t = tree()
    t["conditions"][1]["threshold"] = {"op": ">= and <", "value": [3, 10], "unit": "mm"}
    monkeypatch.setattr(helpers, "T", reduce_code.guideline_text(fl_spans))
    msgs = helpers.problems(t, reduce_code.guideline_text(fl_spans))
    assert any("a range is two conditions, one per bound" in m for m in msgs)
    n, sel = _sel(fl_spans)
    answers = [t, tree()]
    sent = []
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))

    def fake(run_id, step, prompt, schema, **_):
        sent.append(prompt)
        return schema.model_validate(answers.pop(0) if step == "criteria_form" else {})
    monkeypatch.setattr(llm, "call", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", proc(), mode="form")
    assert "a range is two conditions" in sent[1] and cs.status == "ok", cs.problems


def test_form_writes_spend(fl_spans, offline, monkeypatch):
    """llm.call adds every call's tokens to the tally; form prices it like the other arms."""
    class U:
        prompt_tokens, completion_tokens, total_tokens = 1000, 100, 1100

        def model_dump(self):
            return {}

    class R:
        def __init__(self, body):
            self.usage = U()
            self.choices = [type("C", (), {"message": type("M", (), {"content": json.dumps(body)})()})()]
    bodies = [tree(), tree(), {}]           # form, sweep, audit
    monkeypatch.setattr(llm, "_complete", lambda model, messages, effort: (R(bodies.pop(0)), {"params_used": {},
                                                                                              "params_dropped": []}))
    n, sel = _sel(fl_spans)
    reduce_code.build(fl_spans, n, sel, "k", "r", proc(), mode="form")
    spend = json.loads((offline / "runs" / "r" / "criteria_code-cost.json").read_text())
    (v,) = spend.values()
    assert v["calls"] == 3 and v["dollars"] == round(3 * (1000 * 5e-6 + 100 * 30e-6), 4)


def test_runner_guideline_globs():
    import experiments.scripts.reduce_code as R
    rows = [{"guideline": g} for g in ("florida-blue-02-33000-31", "florida-blue-02-33000-34", "florida-blue-09-e0000-21")]
    assert [r["guideline"] for r in R.pick(rows, "florida-blue-02-33000-*")] == [g["guideline"] for g in rows[:2]]
    assert R.pick(rows, "florida-blue-09-e0000-21,nope") == rows[2:]
    assert R.pick(rows, "florida-blue-02-33000") == rows[:2]                     # a prefix
    with pytest.raises(SystemExit):
        R.pick(rows, "florida-blue-03-*")
