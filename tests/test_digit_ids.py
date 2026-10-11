"""Criterion ids that start with a digit ("37765_with_37766") parse in every arm, and an unreadable logic never loses
the tree: the first-pass criteria stand (all required, for review), and an audit whose logic cannot be read keeps the
first logic. Pure: fake models."""
from __future__ import annotations

import pytest

from app import criteria, llm, reduce_code, reduce_script
from app.criteria import HOut
from app.evaluate import from_logic, leaf_ids
from app.models import Procedure
from app.reduce_tools import State
from app.spans import split_guideline
from tests.test_reduce_code import ADL, REFLUX, SIZE, _sel, tree
from tests.test_reduce_tools import WIDGET

DIGIT = "37765_with_37766"


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "RUNS", tmp_path / "runs")
    return tmp_path


def test_from_logic_accepts_digit_leading_ids():
    p: list[str] = []
    e = from_logic(f"{DIGIT} AND NOT 2nd_opinion AND AT_LEAST 2 OF (a, 3b, c)", p)
    assert p == [] and e == {"all": [DIGIT, {"not": "2nd_opinion"}, {"at_least": {"k": 2, "of": ["a", "3b", "c"]}}]}


def test_check_with_digit_id_and_unreadable_logic(fl_spans):
    n, sel = _sel(fl_spans)
    want = criteria.picked(sel)
    h = HOut.model_validate({"criteria": [{"id": DIGIT, "quote": REFLUX, "refs": [], "question": "?"},
                                          {"id": "size", "quote": SIZE, "refs": [], "question": "?"}],
                             "logic": [{"pathway": want[0], "logic": f"{DIGIT} AND size"}]})
    problems, crit, exprs = criteria.check(h, fl_spans, want)
    assert problems == [] and leaf_ids(exprs[0].expr) == [DIGIT, "size"]
    h.logic[0].logic = "size AND AND ("                                     # unreadable: every criterion required
    problems, crit, exprs = criteria.check(h, fl_spans, want)
    assert any("could not be read" in p for p in problems) and exprs[0].expr == {"all": sorted([DIGIT, "size"])}


def test_loose_audit_with_unreadable_logic_keeps_first_tree(fl_spans, offline, monkeypatch):
    """The fixture run's form row: the audit's logic string could not be parsed, so every leaf counted as dropped and
    the row ended with 0 criteria. The first logic must stand."""
    n, sel = _sel(fl_spans)
    want = criteria.picked(sel)
    answers = {"criteria_guideline": [{"criteria": [{"id": DIGIT, "quote": REFLUX, "refs": [], "question": "?"},
                                                    {"id": "size", "quote": SIZE, "refs": [], "question": "?"}],
                                       "logic": [{"pathway": want[0], "logic": f"{DIGIT} AND size"}]}],
               "criteria_audit": [{"loopholes": ["x"], "criteria": [{"id": "adl", "quote": ADL, "question": "?"}],
                                   "logic": [{"pathway": want[0], "logic": "size AND AND ("}]}]}
    monkeypatch.setattr(llm, "call", lambda run_id, step, prompt, schema, **_: schema.model_validate(answers[step].pop(0)))
    cs = criteria.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]))
    ids = {c.id for c in cs.criteria}
    assert {DIGIT, "size"} <= ids and cs.status == "needs_review"          # the first tree is never lost
    assert any("could not be read" in p for p in cs.problems)
    # an audit whose logic names no pathway at all: the first logic stands as is
    p3: list[str] = []
    kept = criteria.keep_missing(cs.expressions, [], p3)
    assert kept == cs.expressions and "the first logic stands" in p3[0]


def test_form_audit_with_unreadable_logic_keeps_first_tree(fl_spans, offline, monkeypatch):
    n, sel = _sel(fl_spans)
    t = tree()
    t["conditions"][0]["id"] = DIGIT
    t["expression"] = {"all": [DIGIT, "size"]}
    answers = {"criteria_form": [t], "criteria_form_sweep": [t],
               "criteria_audit": [{"loopholes": [], "criteria": [], "logic": [{"pathway": criteria.picked(sel)[0],
                                                                               "logic": f"{DIGIT} AND size AND"}]}]}
    monkeypatch.setattr(llm, "call", lambda run_id, step, prompt, schema, **_: schema.model_validate(answers[step].pop(0)))
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="form")
    assert {c.id for c in cs.criteria} == {DIGIT, "size"} and len(cs.criteria) == 2


def test_tools_and_script_accept_digit_ids():
    st = State(split_guideline(WIDGET))
    assert st.handle("add_condition", {"id": DIGIT, "quote": "in adults", "question": "?"})["ok"]
    assert st.handle("add_condition", {"id": "pt", "quote": "Physical therapy", "question": "?"})["ok"]
    r = st.handle("set_logic", {"indication": "i", "logic": f"{DIGIT} AND pt"})
    assert r["ok"], r
    assert sorted(leaf_ids(st.expand(st.logic["i"]))) == sorted([DIGIT, "pt"])
    errors, t = reduce_script.parse(f'a = C("{DIGIT}", "in adults", "q")\n'
                                    'indication("i", grant="medical necessity in adults", logic=a)\n',
                                    State(split_guideline(WIDGET)))
    assert errors == [] and DIGIT in t.conds
