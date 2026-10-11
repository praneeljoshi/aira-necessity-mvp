"""v1.2-tools step H, offline: every tool's checks, revising (update / remove / show), the add-only audit, the caps,
isolation, and a scripted model that replays the few-shot transcript of experiments/stepH/prompts/reduce/tools.md."""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core import llm
from experiments.stepH import reduce_tools
from app.core.models import Guideline, Narrowed, Pathway, Payer, Pick, Procedure, Selection
from experiments.stepH.reduce_tools import State
from app.ingest.spans import split_guideline

WIDGET = """POSITION STATEMENT:
Endoscopic widget repair (EWR) meets the definition of medical necessity in adults when ALL of the
following are met:
  • Symptomatic widget stenosis of 50% or greater on imaging; AND
  • Failure of at least 6 weeks of conservative therapy that includes at least 2 of the following:
      o Physical therapy
      o Anti-inflammatory medication (unless contraindicated)
      o Activity modification
  • Use of an FDA-approved widget device.
Repeat EWR meets the definition of medical necessity when the criteria above are met and the prior repair
has failed.
EWR is considered experimental or investigational for all other indications, including widget dissection
and prophylactic repair.

REIMBURSEMENT INFORMATION:
EWR is limited to one procedure per side per 12 months.
"""

ORDER = {"procedure": "Endoscopic widget repair, left", "cpt_line": "99999 — Endoscopic widget repair, unilateral",
         "diagnosis": "Widget stenosis, left (Z99.1)", "age": 58, "sex": "F"}


@pytest.fixture
def spans():
    return split_guideline(WIDGET)


@pytest.fixture
def st(spans):
    return State(spans)


def add(st, id, quote, q="?", **kw):
    return st.handle("add_condition", {"id": id, "quote": quote, "question": q, **kw})


# ---------------------------------------------------------------- the tools


def test_find_and_read(st, spans):
    r = st.handle("find", {"text": "MEDICAL   necessity"})
    assert r["ok"] and len(r["hits"]) == 2 and "in adults" in r["hits"][0]["text"]
    assert "-" in st.handle("find", {"text": "the following are met"})["hits"][0]["lines"]    # wraps over two lines
    w = st.handle("find", {"text": "dissection widget nowhere"})
    assert w["matched"] and "widget dissection" in w["hits"][0]["text"]
    ids = [s.id for s in spans]
    r = st.handle("read", {"first": ids[0], "last": ids[3]})
    assert r["ok"] and len(r["lines"]) == 4 and r["lines"][0].startswith(ids[0] + " POSITION")
    assert not st.handle("read", {"first": "g9999", "last": ids[0]})["ok"]


def test_add_condition_checks_quote_id_and_threshold(st):
    assert add(st, "adult", "in adults")["ok"]
    r = add(st, "stenosis", "widget stenosis of 50 percent or greater")
    assert r["problems"] == ["quote not found"] and "50% or greater" in r["nearest"][0]["text"]
    assert add(st, "adult", "in adults")["problems"] == ["id already used"]
    assert "threshold" in add(st, "s50", "of 50% or greater", threshold={"op": "at least", "value": 50})["problems"][0]
    ok = add(st, "wrapped", "medical necessity in adults when ALL of the following")    # over a line break
    assert ok["ok"] and "-" in ok["lines"]


def test_logic_blocks_and_cycles(st):
    for i, q in (("a", "in adults"), ("b", "Physical therapy"), ("c", "Activity modification")):
        add(st, i, q)
    assert "unknown id 'zz'" in st.handle("define_block", {"name": "k", "logic": "a AND zz"})["problems"][0]
    assert not st.handle("define_block", {"name": "k", "logic": "a AND (b"})["ok"]
    r = st.handle("define_block", {"name": "k", "logic": "a AND AT_LEAST 1 OF (b, c)"})
    assert r["ok"] and r["expanded"] == "a AND AT_LEAST 1 OF (b, c)"
    st.handle("define_block", {"name": "j", "logic": "k OR b"})
    assert "refers to itself" in st.handle("define_block", {"name": "k", "logic": "j"})["problems"][0]
    r = st.handle("set_logic", {"indication": "first", "logic": "k AND NOT b"})
    assert r["ok"] and r["unused_conditions"] == []
    assert st.expand(st.logic["first"]) == {"all": [{"all": ["a", {"at_least": {"k": 1, "of": ["b", "c"]}}]}, {"not": "b"}]}
    st.handle("set_logic", {"indication": "first", "logic": "a"})                    # replaces, and is logged
    assert st.changes[-1]["old"] == "k AND NOT b" and st.handle("show", {})["unused_conditions"] == ["b", "c"]


def test_submit_final_checks(st):
    add(st, "adult", "in adults")
    add(st, "pt", "Physical therapy")
    r = st.handle("submit", {"indication_quotes": ["EWR is approved for everyone"]})
    assert not r["ok"] and any("not found" in p for p in r["problems"]) and any("no indication" in p for p in r["problems"])
    st.handle("set_logic", {"indication": "first", "logic": "adult"})
    r = st.handle("submit", {"indication_quotes": ["meets the definition of medical necessity in adults"]})
    assert r["problems"] == ["conditions not used in any logic: pt"]
    st.handle("set_logic", {"indication": "first", "logic": "adult AND pt"})
    r = st.handle("submit", {"indication_quotes": ["meets the definition of medical necessity in adults"]})
    assert r["ok"] and r["accepted"] is False and "full-policy sweep" in r["next"] and not st.done   # the sweep
    assert st.handle("submit", {"indication_quotes": ["meets the definition of medical necessity in adults"]}) == {"ok": True}
    assert st.done and st.submits == 4


def test_update_remove_show(st):
    add(st, "c6", "Failure of at least 6 weeks of conservative therapy", threshold={"op": ">=", "value": 1.5, "unit": "months"})
    add(st, "pt", "Physical therapy")
    add(st, "oops", "prophylactic repair")
    r = st.handle("update_condition", {"id": "c6", "threshold": {"op": ">=", "value": 6, "unit": "weeks"}})
    assert r["ok"] and st.conds["c6"]["threshold"]["value"] == 6
    assert st.conds["c6"]["question"] == "?"                                             # only what was passed changed
    assert st.changes[-1] == {"tool": "update_condition", "id": "c6",
                              "old": {"threshold": {"op": ">=", "value": 1.5, "unit": "months"}},
                              "new": {"threshold": {"op": ">=", "value": 6, "unit": "weeks"}}}
    bad = st.handle("update_condition", {"id": "c6", "quote": "six weeks of conservative care"})
    assert bad["problems"] == ["quote not found"] and bad["nearest"] and st.conds["c6"]["threshold"]["value"] == 6
    assert st.handle("update_condition", {"id": "pt", "quote": "Activity modification"})["ok"]
    assert st.conds["pt"]["quote"] == "Activity modification"
    st.handle("set_logic", {"indication": "first", "logic": "c6 AND NOT oops"})
    assert st.handle("remove_condition", {"id": "oops", "why": ""})["problems"][0].startswith("why is required")
    assert st.handle("remove_condition", {"id": "oops", "why": "x"})["problems"] == ["still used in: set_logic first"]
    st.handle("set_logic", {"indication": "first", "logic": "c6 AND pt"})
    assert st.handle("remove_condition", {"id": "oops", "why": "an exclusion, not this route"})["ok"]
    assert st.removed == [{"id": "oops", "quote": "prophylactic repair", "why": "an exclusion, not this route"}]
    sh = st.handle("show", {})
    assert [c["id"] for c in sh["conditions"]] == ["c6", "pt"] and sh["logic"] == {"first": "c6 AND pt"}


def test_audit_is_add_only(st):
    add(st, "adult", "in adults")
    add(st, "pt", "Physical therapy")
    st.handle("set_logic", {"indication": "first", "logic": "adult AND pt"})
    st.audit = True
    st.locked = {"first": {"adult", "pt"}}
    assert "drops pt" in st.handle("set_logic", {"indication": "first", "logic": "adult"})["problems"][0]
    assert "new indication" in st.handle("set_logic", {"indication": "other", "logic": "adult"})["problems"][0]
    for tool in ("update_condition", "remove_condition", "define_block"):
        assert "no tool" in st.handle(tool, {"id": "pt", "why": "x", "name": "b", "logic": "pt"})["problems"][0]
    add(st, "diss", "widget dissection")
    assert st.handle("set_logic", {"indication": "first", "logic": "adult AND pt AND NOT diss"})["ok"]
    assert st.handle("show", {})["ok"]


# ---------------------------------------------------------------- the session, with a scripted model


class FakeClient:
    """Replays scripted turns: each turn is a list of (tool, args). Records everything sent."""

    def __init__(self, *scripts):
        self.scripts = [list(s) for s in scripts]       # one script per session (main, audit)
        self.sent: list[dict] = []
        self.responses = SimpleNamespace(create=self.create)
        self.n = 0

    def create(self, **kw):
        self.sent.append(kw)
        if "previous_response_id" not in kw:             # a new session starts the next script
            self.cur = self.scripts.pop(0) if self.scripts else []
        turn = self.cur.pop(0) if self.cur else []
        self.n += 1
        out = [SimpleNamespace(type="function_call", name=n, arguments=json.dumps(a), call_id=f"c{self.n}-{i}")
               for i, (n, a) in enumerate(turn)]
        return SimpleNamespace(id=f"r{self.n}", output=out, usage=None, output_text="" if out else "DONE")


def few_shot(spans) -> list[list]:
    ids = [s.id for s in spans]
    t = [[("find", {"text": "medical necessity"})], [("read", {"first": ids[0], "last": ids[-1]})]]
    t.append([("add_condition", a) for a in (
        {"id": "adult", "quote": "in adults", "question": "Is the patient an adult?"},
        {"id": "stenosis_50", "quote": "Symptomatic widget stenosis of 50% or greater on imaging",
         "question": "Does imaging show symptomatic widget stenosis of 50% or more?",
         "threshold": {"op": ">=", "value": 50, "unit": "%"}},
        {"id": "conservative_6wk", "quote": "Failure of at least 6 weeks of conservative therapy",
         "question": "Did at least 6 weeks of conservative therapy fail (dated notes)?",
         "threshold": {"op": ">=", "value": 1.5, "unit": "months"}},
        {"id": "pt", "quote": "Physical therapy", "question": "Was physical therapy tried?"},
        {"id": "nsaid", "quote": "Anti-inflammatory medication", "question": "Was anti-inflammatory medication tried?"},
        {"id": "nsaid_contraindicated", "quote": "unless contraindicated",
         "question": "Is anti-inflammatory medication documented as contraindicated?"},
        {"id": "activity_mod", "quote": "Activity modification", "question": "Was activity modification tried?"},
        {"id": "fda_device", "quote": "Use of an FDA-approved widget device", "question": "Is the planned device FDA-approved?"},
        {"id": "prior_repair_failed", "quote": "the prior repair has failed", "question": "Has a prior EWR on this side failed?"},
        {"id": "dissection", "quote": "widget dissection", "question": "Is there a widget dissection?"},
        {"id": "prophylactic", "quote": "prophylactic repair", "question": "Is the repair prophylactic (no current stenosis)?"},
        {"id": "once_per_12mo", "quote": "one procedure per side every 12 months",
         "question": "Has this side had EWR in the past 12 months?"})])
    t.append([("add_condition", {"id": "once_per_12mo", "quote": "limited to one procedure per side per 12 months",
                                 "question": "Has this side had EWR in the past 12 months?"})])
    t.append([("define_block", {"name": "ewr_criteria", "logic": "adult AND stenosis_50 AND conservative_6wk AND AT_LEAST 2 OF "
                                "(pt, (nsaid OR nsaid_contraindicated), activity_mod) AND fda_device"}),
              ("define_block", {"name": "ewr_exclusions", "logic": "dissection OR prophylactic"}),
              ("update_condition", {"id": "conservative_6wk", "threshold": {"op": ">=", "value": 6, "unit": "weeks"}})])
    t.append([("set_logic", {"indication": "ewr_first", "logic": "ewr_criteria AND NOT ewr_exclusions AND NOT once_per_12mo"}),
              ("set_logic", {"indication": "ewr_repeat",
                             "logic": "ewr_criteria AND prior_repair_failed AND NOT ewr_exclusions AND NOT once_per_12mo"})])
    t.append([("submit", {"indication_quotes": [
        "Endoscopic widget repair (EWR) meets the definition of medical necessity in adults",
        "Repeat EWR meets the definition of medical necessity when the criteria above are met"],
        "notes": "Both routes kept: the order does not say whether a prior repair exists."})])
    t.append(t[-1])         # the first passing submit starts the sweep; the full pass adds nothing: submit again
    return t


def sel_for():
    n = Narrowed(key="k", guideline=Guideline(id="g", sha256="s", payer=Payer(name="Widget Health")),
                 pathways=[Pathway(id="indication", spans=[], codes=["99999"])], chosen=["indication"])
    return n, Selection(applies=True, pathways=[Pick(code="99999", pathway="indication", how="code")])


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "RUNS", tmp_path / "runs")
    return tmp_path


def run(spans, fake, monkeypatch, **kw):
    monkeypatch.setattr(llm, "client", lambda: fake)
    n, sel = sel_for()
    proc = Procedure(cpt=["99999"], as_written=ORDER["procedure"], diagnosis=ORDER["diagnosis"])
    return reduce_tools.build(spans, n, sel, "k", "run1", proc,
                              extra={"cpt_line": ORDER["cpt_line"], "age": 58, "sex": "F"}, **kw)


def test_few_shot_replay_builds_the_expected_set(spans, offline, monkeypatch):
    audit = [[("find", {"text": "investigational"})],
             [("submit", {"indication_quotes": [], "notes": "none found"})]]
    fake = FakeClient(few_shot(spans), audit)
    cs = run(spans, fake, monkeypatch)
    assert cs.status == "ok", cs.problems
    assert {c.id for c in cs.criteria} == {"adult", "stenosis_50", "conservative_6wk", "pt", "nsaid",
                                           "nsaid_contraindicated", "activity_mod", "fda_device",
                                           "prior_repair_failed", "dissection", "prophylactic", "once_per_12mo"}
    crit = {"all": ["adult", "stenosis_50", "conservative_6wk",
                    {"at_least": {"k": 2, "of": ["pt", {"any": ["nsaid", "nsaid_contraindicated"]}, "activity_mod"]}},
                    "fda_device"]}
    excl = {"any": ["dissection", "prophylactic"]}
    assert cs.expressions[0].pathway == "indication"
    assert cs.expressions[0].expr == {"any": [
        {"all": [crit, {"not": excl}, {"not": "once_per_12mo"}]},
        {"all": [crit, "prior_repair_failed", {"not": excl}, {"not": "once_per_12mo"}]}]}
    c6 = next(c for c in cs.criteria if c.id == "conservative_6wk")
    assert c6.threshold.value == 6 and c6.threshold.unit == "weeks"
    assert next(c for c in cs.criteria if c.id == "once_per_12mo").quote == "limited to one procedure per side per 12 months"
    assert "Indication used: Endoscopic widget repair (EWR)" in cs.notes and "Routes (ORed)" in cs.notes
    assert "Sweep added: nothing" in cs.notes          # the second submit (after the sweep) is the accepted one
    assert cs.loopholes == [] and cs.removed_conditions == []
    log = json.loads((offline / "runs" / "run1" / "criteria_tools.json").read_text())
    assert log["usage"]["calls"] == 22 and log["turns"][2]["calls"][-1]["result"]["problems"] == ["quote not found"]
    assert (offline / "runs" / "run1" / "criteria_tools-changes.json").exists()
    assert (offline / "runs" / "run1" / "criteria_tools_audit.json").exists()


def test_audit_adds_and_cannot_drop(spans, offline, monkeypatch):
    audit = [[("set_logic", {"indication": "ewr_first", "logic": "adult"})],             # refused: drops leaves
             [("add_condition", {"id": "symptomatic", "quote": "Symptomatic", "question": "Symptoms?"})],
             [("set_logic", {"indication": "ewr_first", "logic": "ewr_criteria AND symptomatic AND NOT ewr_exclusions "
                                                                  "AND NOT once_per_12mo"})],
             [("submit", {"indication_quotes": [], "notes": "- A patient with no symptoms passes."})]]
    fake = FakeClient(few_shot(spans), audit)
    cs = run(spans, fake, monkeypatch)
    assert cs.status == "ok" and "symptomatic" in {c.id for c in cs.criteria}
    assert cs.loopholes == ["A patient with no symptoms passes."]
    assert "adult" in json.dumps(cs.expressions[0].expr)


def test_cap_and_stop_give_needs_review(spans, offline, monkeypatch):
    monkeypatch.setattr(reduce_tools, "MAX_CALLS", 5)
    loop = [[("find", {"text": "EWR"})] * 3] * 5
    cs = run(spans, FakeClient(loop), monkeypatch)
    assert cs.status == "needs_review" and "tool-call cap" in cs.problems[0] and cs.expressions == []
    cs = run(spans, FakeClient([[("find", {"text": "EWR"})]]), monkeypatch)            # stops talking, never submits
    assert cs.status == "needs_review" and "without a successful submit" in cs.problems[0]


def test_isolation_only_order_codes_guideline(spans, offline, monkeypatch):
    """What reaches the model: the instructions, the allow-listed order, the code rows, the guideline; tool results
    from the guideline and the tree only. No pathway name, scenario id or key material."""
    fake = FakeClient(few_shot(spans), [[("submit", {"indication_quotes": []})]])
    run(spans, fake, monkeypatch)
    first = fake.sent[0]
    body = first["input"]
    assert body.startswith("## The order\n") and "## Codes on the order" in body and "## The guideline" in body
    order = json.loads(body.split("## The order\n", 1)[1].split("## Codes")[0])
    assert set(order) <= {"procedure", "cpt", "cpt_line", "diagnosis", "age", "sex"}
    sent = json.dumps([k.get("input") for k in fake.sent]) + first["instructions"]
    for leak in ("scenario", "Great or Small", "tests/fixtures", '"indication"'):
        assert leak not in sent, leak
    assert {t["name"] for t in first["tools"]} == set(reduce_tools.TOOLS)
    audit_first = next(k for k in fake.sent[1:] if "previous_response_id" not in k)
    assert {t["name"] for t in audit_first["tools"]} == set(reduce_tools.AUDIT_TOOLS)


def test_pitfalls_flag(monkeypatch):
    assert "Common mistakes" not in reduce_tools.instructions("P")
    monkeypatch.setenv("PITFALLS", "1")
    assert "Common mistakes" in reduce_tools.instructions("P")
