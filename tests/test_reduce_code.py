"""v1.2-code step H, offline: the sandbox helpers' checks, the host re-check, both modes with a fake model, the
add-only audit, and unanswerable conditions never deciding (policy B)."""
from __future__ import annotations

import json

import pytest

from app import llm, narrow, reduce_code
from app.evaluate import compile_expr
from app.models import Order, Procedure, Verdict
from app.pipeline import negated_leaves
from app.sandbox import helpers
from app.select import select
from tests.fake import narrow_answer

REFLUX = "There is demonstrated saphenous reflux"
SIZE = "The varicosities are at least 3 millimeters in size"
ADL = "the symptoms significantly interfere with activities of daily living"


@pytest.fixture
def text(fl_spans):
    return reduce_code.guideline_text(fl_spans)


@pytest.fixture
def T(text, monkeypatch):
    monkeypatch.setattr(helpers, "T", text)
    return text


def tree(**kw):
    t = {"indication": None, "not_covered": None,
         "conditions": [{"id": "reflux", "quote": REFLUX, "question": "Reflux?", "threshold": None, "answerable": True},
                        {"id": "size", "quote": SIZE, "question": "3 mm?", "threshold": {"op": ">=", "value": 3, "unit": "mm"},
                         "answerable": True}],
         "blocks": [], "expression": {"all": ["reflux", "size"]}, "notes": ""}
    t.update(kw)
    return t


# ---------------------------------------------------------------- helpers.py


def test_find_forgives_whitespace_and_broken_lines_only(T):
    assert helpers.find(ADL) is not None                      # wraps over a line in the PDF
    assert helpers.find("There  is demonstrated\nsaphenous reflux") is not None
    assert helpers.find("There is clearly demonstrated saphenous reflux") is None
    with pytest.raises(helpers.QuoteNotFound):
        helpers.fq("at least 4 millimeters")


def test_problems_are_citation_and_form_only(T):
    assert helpers.problems(tree()) == []
    bad = tree(expression={"all": ["reflux", "nope"]})
    assert any("'nope' is neither" in p for p in helpers.problems(bad))
    assert any("not used" in p for p in helpers.problems(tree(expression="reflux")))
    dup = tree()
    dup["conditions"].append(dict(dup["conditions"][0]))
    assert any("used twice" in p for p in helpers.problems(dup))
    assert any("QUOTE NOT FOUND" in p for p in helpers.problems(tree(conditions=[
        {"id": "reflux", "quote": "made up words", "question": "q"}], expression="reflux")))
    assert any("threshold" in p for p in helpers.problems(tree(conditions=[
        {"id": "reflux", "quote": REFLUX, "question": "q", "threshold": {"op": "at least", "value": 3}}], expression="reflux")))
    assert any("at_least" in p for p in helpers.problems(tree(expression={"at_least": {"k": 3, "of": ["reflux", "size"]}})))


def test_blocks_expand_and_write(T, tmp_path):
    r = helpers.C("reflux", REFLUX, "Reflux?")
    s = helpers.C("size", SIZE, "3 mm?", helpers.th(">=", 3, "mm"))
    b = helpers.block("vein", [r, s], {"all": ["reflux", "size"]})
    out = helpers.write(None, None, [], {"any": ["vein"]}, blocks=[b], path=str(tmp_path / "tree.json"))
    assert {c["id"] for c in out["conditions"]} == {"reflux", "size"}
    assert helpers.expand(out["expression"], {"vein": b["expr"]}) == {"any": [{"all": ["reflux", "size"]}]}
    with pytest.raises(helpers.TreeError):
        helpers.write(None, None, [r], {"all": ["reflux", "ghost"]}, path=str(tmp_path / "t2.json"))


# ---------------------------------------------------------------- host re-check


def test_host_never_trusts_the_sandbox(fl_spans, text):
    t = tree()
    t["conditions"][0]["quote"] = "There is demonstrated venous reflux"     # the sandbox said OK; the host does not
    problems, crit, exprs = reduce_code.verify(t, text, fl_spans, "gsv")
    assert any("QUOTE NOT FOUND" in p for p in problems)
    ok, crit, exprs = reduce_code.verify(tree(), text, fl_spans, "gsv")
    assert ok == [] and exprs[0].expr == {"all": ["reflux", "size"]}
    assert all(c.refs and c.refs[0].startswith("g") for c in crit)            # refs located by the host
    nc = reduce_code.verify(tree(not_covered=REFLUX), text, fl_spans, "gsv")[0]
    assert not any("not covered" in p for p in nc)                          # an indication is declared: notes only
    nc = reduce_code.verify(tree(not_covered=REFLUX, expression=None), text, fl_spans, "gsv")[0]
    assert any("not covered" in p for p in nc)


def _sel(fl_spans):
    n = narrow.resolve(narrow.COut.model_validate(narrow_answer(fl_spans, {"target": "great saphenous vein", "cpt": ["36475"]})),
                       fl_spans, "g", "s", "k", [])
    return n, select(n, Order(procedure=Procedure(cpt=["36475"], target="great saphenous vein")), fl_spans)


# ---------------------------------------------------------------- form mode (no sandbox)


def test_form_mode_fixes_then_audit_only_adds(fl_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    n, sel = _sel(fl_spans)
    first = tree()
    first["conditions"][1]["quote"] = "at least 4 millimeters"
    answers = {"criteria_form": [first, tree()], "criteria_form_sweep": [tree()],
               "criteria_audit": [{"loopholes": ["a 2 mm vein passes"],
                                   "criteria": [{"id": "adl", "quote": ADL, "question": "ADL?"}],
                                   "logic": [{"pathway": "gsv", "logic": "reflux AND adl"}]}]}   # drops size
    calls = []

    def fake(run_id, step, prompt, schema, **_):
        calls.append(step)
        return schema.model_validate(answers[step].pop(0))
    monkeypatch.setattr(llm, "call", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="form")
    assert calls == ["criteria_form", "criteria_form", "criteria_form_sweep", "criteria_audit"]
    from app.evaluate import leaf_ids
    assert set(leaf_ids(cs.expressions[0].expr)) == {"reflux", "adl", "size"}     # size put back
    assert cs.loopholes == ["a 2 mm vein passes"] and any("put back" in p for p in cs.problems)
    assert next(c for c in cs.criteria if c.id == "size").threshold.op == "gte"


# ---------------------------------------------------------------- code mode, with a fake sandbox


class FakeSession:
    def __init__(self, trees, said=("none found", "DONE")):
        self.trees, self.said, self.turns, self.closed = list(trees), list(said), [], False
        self.usage = {"input_tokens": 100, "output_tokens": 50, "turns": 0, "containers": 1, "cells": 3}

    def __call__(self, run_id, step, files, model=None, **_):
        assert {"guideline.txt", "order.json", "codes.json", "helpers.py", "BRIEF.md"} <= set(files)
        self.files = files
        return self

    def turn(self, text, instructions=None):
        self.turns.append(text)
        return "\n".join(self.said) if "check yourself" in text else "DONE"

    def fetch(self, name):
        t = self.trees.pop(0) if len(self.trees) > 1 else self.trees[0]
        return json.dumps(t).encode()

    def close(self):
        self.closed = True

    def cost(self):
        return 0.01


def test_code_mode_rounds_until_clean_then_audits(fl_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    n, sel = _sel(fl_spans)
    bad = tree(expression={"all": ["reflux", "ghost"]})
    audited = tree(conditions=tree()["conditions"] + [{"id": "adl", "quote": ADL, "question": "ADL?"}],
                   expression={"all": ["reflux", "size", "adl"]})
    fake = FakeSession([bad, tree(), audited], said=("A patient with no daily-living impact passes.", "DONE"))
    monkeypatch.setattr(llm, "CodeSession", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"], diagnosis="Varicose veins (I83.12)"),
                           extra={"age": 52}, mode="code")
    assert len(fake.turns) == 4 and "ghost" in fake.turns[1] and fake.closed     # task, fix, sweep, audit
    assert "full-policy sweep" in fake.turns[2] and "Sweep added: adl" in cs.notes
    assert json.loads(fake.files["order.json"])["age"] == 52
    assert cs.status == "ok" and {c.id for c in cs.criteria} == {"reflux", "size", "adl"}
    assert cs.loopholes == ["A patient with no daily-living impact passes."]


def test_code_mode_gives_up_after_rounds(fl_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    n, sel = _sel(fl_spans)
    fake = FakeSession([tree(expression={"all": ["reflux", "ghost"]})])
    monkeypatch.setattr(llm, "CodeSession", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="code")
    assert cs.status == "needs_review" and len(fake.turns) == reduce_code.ROUNDS + 1


def test_policy_flags_drop_bullets(monkeypatch):
    assert "[E]" in reduce_code.policies()
    monkeypatch.setenv("REDUCE_POLICY_E", "0")
    p = reduce_code.policies()
    assert "[E]" not in p and "[A]" in p and "impossible" not in p


# ---------------------------------------------------------------- policy B


def test_unanswerable_under_not_never_blocks():
    e = {"all": ["reflux", {"not": "contract_excludes"}]}
    assert negated_leaves(e) == {"contract_excludes"}
    v = {"reflux": Verdict(criterion="reflux", status="MET", confidence=0.9),
         "contract_excludes": Verdict(criterion="contract_excludes", status="NOT_MET", confidence=1.0)}
    assert compile_expr(e, v).status == "MET"


def test_find_arm_gives_no_indication_lines(fl_spans, monkeypatch):
    """The default reduce-only arm: no pathway lines, the model finds the indication and quotes it."""
    from app.models import Narrowed, Pathway, Pick, Selection, Guideline, Payer
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    n = Narrowed(key="k", guideline=Guideline(id="g", sha256="s", payer=Payer(name="FB")),
                 pathways=[Pathway(id="indication", spans=[])], chosen=["indication"])
    sel = Selection(applies=True, pathways=[Pick(code="36475", pathway="indication", how="code")])
    t = tree(indication=["Great or Small Saphenous Veins"])
    fake = FakeSession([t])
    monkeypatch.setattr(llm, "CodeSession", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="code")
    assert reduce_code.FIND in fake.turns[0] and "First find which coverage indication" in fake.files["BRIEF.md"].decode()
    assert "A person has confirmed" not in fake.files["BRIEF.md"].decode()
    assert "Indication used: Great or Small Saphenous Veins" in cs.notes and cs.status == "ok"
    assert any("QUOTE NOT FOUND" in p for p in helpers.problems(tree(indication=["not in the text at all"]),
                                                                 reduce_code.guideline_text(fl_spans)))


def test_runner_uploads_no_answer_material(fl_spans, monkeypatch):
    """Exactly five files go in, and order.json carries only the order: no pathway name, no scenario id."""
    import scripts.reduce_code as R
    row = {"guideline": "g", "pathway": "Great or Small Saphenous Veins (surgery)", "scenario_id": "gsv_sec",
           "cpt": ["36475"], "cpt_line": "36475 — Endovenous ablation", "as_written": "RFA left GSV",
           "target": None, "diagnosis": "Varicose veins with pain (I83.812)", "age": 58, "sex": "F"}
    extra = {k: row.get(k) for k in R.ORDER_FIELDS if k not in ("cpt", "as_written", "diagnosis")}
    o = json.loads(reduce_code.order_json(Procedure(cpt=row["cpt"], as_written=row["as_written"],
                                                    diagnosis=row["diagnosis"]), extra))
    assert set(o) <= {"procedure", "cpt", "cpt_line", "diagnosis", "age", "sex"}
    assert "Saphenous Veins (surgery)" not in json.dumps(o) and "gsv_sec" not in json.dumps(o)
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    n, sel = _sel(fl_spans)
    fake = FakeSession([tree()])
    monkeypatch.setattr(llm, "CodeSession", fake)
    reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), extra=extra, mode="code")
    assert sorted(fake.files) == ["BRIEF.md", "codes.json", "guideline.txt", "helpers.py", "order.json"]


def test_concurrent_rows_keep_their_own_indication(fl_spans, monkeypatch):
    """The runner builds rows in threads: each row's confirmed indication must reach its own session only."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    seen: dict[str, str] = {}
    lock = threading.Lock()

    class Slow(FakeSession):
        def turn(self, text, instructions=None):
            time.sleep(0.05)
            with lock:
                seen.setdefault(self.run_id, text)
            return super().turn(text, instructions)

    def make(run_id, *a, **k):
        s = Slow([tree()])(run_id, *a, **k)
        s.run_id = run_id
        return s

    monkeypatch.setattr(llm, "CodeSession", make)
    n, sel = _sel(fl_spans)
    heads = [REFLUX, SIZE, ADL, "Great or Small Saphenous Veins"]

    def one(i):
        reduce_code.build(fl_spans, n, sel, "k", f"r{i}", Procedure(cpt=["36475"]), mode="code", indication=heads[i])

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, range(4)))
    for i, h in enumerate(heads):
        assert h in seen[f"r{i}"] and not any(o in seen[f"r{i}"] for o in heads if o != h)
