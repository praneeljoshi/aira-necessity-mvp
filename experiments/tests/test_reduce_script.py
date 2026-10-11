"""v1.2-script step H, offline: the whitelist parser (never executed), evaluation to the v1.1 shape, every check, the
add-only audit, caps, isolation, and a scripted model replaying the worked example of experiments/stepH/prompts/reduce/script.md."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.core import llm
from experiments.stepH import reduce_script
from app.core.models import Procedure
from experiments.stepH.reduce_script import keeps, parse
from experiments.stepH.reduce_tools import State
from app.ingest.spans import split_guideline
from experiments.tests.test_reduce_tools import ORDER, WIDGET, FakeClient, sel_for

PROMPT = Path(__file__).resolve().parents[1] / "stepH" / "prompts" / "reduce" / "script.md"


@pytest.fixture
def st():
    return State(split_guideline(WIDGET))


def example() -> tuple[str, str, list[str]]:
    """Round 1, round 2 (whole) and round 1's errors, as the prompt shows them."""
    text = PROMPT.read_text()
    py = re.findall(r"```python\n(.*?)```", text, re.S)
    r1 = py[-2]
    r2 = r1[:r1.index("once = C(")] + "".join(l for l in py[-1].splitlines(True) if not l.startswith("# ..."))
    shown = re.search(r"Result:\n```\n(.*?)```", text, re.S).group(1)
    return r1, r2, json.loads(shown)["errors"]


PRE = '''a = C("adult", "in adults", "Adult?")
b = C("pt", "Physical therapy", "PT?")
c = C("am", "Activity modification", "AM?")
'''


def ind(logic, grant="medical necessity in adults"):
    return f'indication("i", grant="{grant}", logic={logic})\n'


# ---------------------------------------------------------------- parser and evaluation


def test_precedence_blocks_at_least_and_flattening(st):
    e, t = parse(PRE + "blk = b & c & a\n" + ind("a | b & ~c | at_least(2, a, b | c, blk)"), st)
    assert e == []
    assert t.inds["i"]["expr"] == {"any": ["adult", {"all": ["pt", {"not": "am"}]},
                                           {"at_least": {"k": 2, "of": ["adult", {"any": ["pt", "am"]},
                                                                        {"all": ["pt", "am", "adult"]}]}}]}
    assert t.blocks["blk"] == {"all": ["pt", "am", "adult"]}


@pytest.mark.parametrize("line, msg", [
    ("import os", "not allowed here: Import"),
    ("for x in y: pass", "not allowed here: For"),
    ("def f(): pass", "not allowed here: FunctionDef"),
    ("x = a.b", "not allowed here: Attribute"),
    ("x = open('f')", "not allowed here: Call"),
    ("print('x')", "not allowed here: call to 'print'"),
    ("x = a and b", "use & for AND"),
    ("x = [a for a in b]", "not allowed here: ListComp"),
    ("a.b = 1", "assign to one plain name"),
    ("C('z', 'in adults', 'q')", "assign C(...) to a name"),
    ("x = at_least(5, a, b)", "k must be a whole number from 1 to 2"),
])
def test_rejected_forms_name_their_line(st, line, msg):
    e, _ = parse(PRE + line + "\n" + ind("a & b & c"), st)
    assert any(x.startswith("line 4:") and msg in x for x in e), e


def test_checks_are_collected_with_lines(st):
    s = (PRE + 'd = C("adult", "Physical therapy", "again?")\n'            # line 4: duplicate id
         + 'e = C("x", "nowhere in this text", "q", threshold=("about", 3, "mm"))\n'       # line 5
         + 'f = C("y", "Activity modification", "q", threshold=5)\n'       # line 6
         + ind("a & b & z & later") + 'later = a & b\n'
         + 'indication("j", logic=a)\n')
    e, t = parse(s, st)
    want = ["line 4: duplicate id 'adult' (first on line 1)",
            "line 5: threshold op 'about' is not one of >=, >, <=, <, ==",
            "line 5: quote not found: 'nowhere in this text'",
            "line 6: threshold must be (op, value, unit)",
            "line 7: name 'z' is not defined",
            "line 9: indication 'j' needs grant="]
    for w in want:
        assert any(x.startswith(w) for x in e), (w, e)
    assert any("nearest" in x for x in e if x.startswith("line 5: quote"))
    e2, _ = parse(PRE + ind("a & b & later") + "later = c\n", st)
    assert e2 == ["line 4: name 'later' is used before it is defined (line 5)"]
    e3, _ = parse(PRE + ind("a & b"), st)
    assert e3 == ["line 3: unused condition 'am'"]
    e4, _ = parse(PRE, st)
    assert "no indication(...) and no not_covered(...)" in e4[0]
    e5, _ = parse(PRE + ind("a & b & c", grant="EWR is free for all"), st)
    assert e5[0].startswith("line 4: grant quote not found")
    assert parse("x = (", st)[0][0].startswith("line 1: syntax error")


def test_audit_keep_rule(st):
    _, first = parse(PRE + ind("a & (b | c)"), st)
    _, ok = parse(PRE + 'd = C("diss", "widget dissection", "q")\n' + ind("a & (b | c) & ~d"), st)
    assert keeps(first, ok) == []
    _, lost = parse(PRE + ind("a & b") + 'notes("c dropped")\nz = c\n', st)
    assert "indication 'i' no longer uses am" in keeps(first, lost)[0]
    _, gone = parse('a = C("adult", "in adults", "Adult?")\n' + ind("a"), st)
    assert any("condition 'pt' was removed" in x for x in keeps(first, gone))
    _, wider = parse(PRE + ind("a & (b | c)") + 'indication("k", grant="Repeat EWR", logic=a)\n', st)
    assert any("new indication 'k'" in x for x in keeps(first, wider))


# ---------------------------------------------------------------- the session


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "RUNS", tmp_path / "runs")
    return tmp_path


def run(fake, monkeypatch):
    monkeypatch.setattr(llm, "client", lambda: fake)
    n, sel = sel_for()
    spans = split_guideline(WIDGET)
    proc = Procedure(cpt=["99999"], as_written=ORDER["procedure"], diagnosis=ORDER["diagnosis"])
    return reduce_script.build(spans, n, sel, "k", "run1", proc, extra={"cpt_line": ORDER["cpt_line"], "age": 58})


def test_worked_example_replay(offline, monkeypatch):
    r1, r2, shown = example()
    audit = [[("submit", {"script": r2 + 'notes("none found")\n'})]]
    fake = FakeClient([[("find", {"text": "medical necessity"})], [("check", {"script": r1})],
                       [("find", {"text": "investigational"})], [("check", {"script": r2})],
                       [("submit", {"script": r2})], [("submit", {"script": r2})]], audit)
    cs = run(fake, monkeypatch)
    log = json.loads((offline / "runs" / "run1" / "criteria_script.json").read_text())
    got = log["turns"][1]["calls"][0]["result"]["errors"]
    # round 1: the errors the prompt shows (its nearest line id is the example's own numbering)
    assert [re.sub(r"g\d{4}", "g", x) for x in got] == [re.sub(r"g\d{4}", "g", x) for x in shown]
    assert cs.status == "ok", cs.problems
    crit = {"all": ["adult", "stenosis_50", "conservative_6wk",
                    {"at_least": {"k": 2, "of": ["pt", {"any": ["nsaid", "nsaid_contraindicated"]}, "activity_mod"]}},
                    "fda_device"]}
    excl = {"not": {"any": ["dissection", "prophylactic"]}}
    assert cs.expressions[0].expr == {"any": [
        {"all": crit["all"] + [excl, {"not": "once_per_12mo"}]},
        {"all": crit["all"] + ["prior_repair_failed", excl, {"not": "once_per_12mo"}]}]}
    assert len(cs.criteria) == 12 and cs.script == r2 + 'notes("none found")\n' and cs.loopholes == []
    c6 = next(c for c in cs.criteria if c.id == "conservative_6wk")
    assert (c6.threshold.value, c6.threshold.unit) == (6, "weeks")
    assert "Indication used: Endoscopic widget repair (EWR)" in cs.notes
    s = json.loads((offline / "runs" / "run1" / "criteria_script-script.json").read_text())
    assert s["passed"] and "+once = C(\"once_per_12mo\", \"limited to" in s["changes"][0]


def test_audit_tightens_or_first_stands(offline, monkeypatch):
    _, r2, _ = example()
    tighter = r2.replace("prior_failed = C(", 'symptomatic = C("symptomatic", "Symptomatic", "Symptoms?")\nprior_failed = C(') \
        .replace("& ~once)", "& symptomatic & ~once)") + 'notes("- An asymptomatic patient passed; added symptomatic.")\n'
    cs = run(FakeClient([[("submit", {"script": r2})]], [[("submit", {"script": tighter})]]), monkeypatch)
    assert cs.status == "ok" and "symptomatic" in {c.id for c in cs.criteria}
    assert cs.loopholes == ["An asymptomatic patient passed; added symptomatic."]
    looser = r2.replace("& prior_failed & ~exclusions", "& prior_failed").replace(
        "logic=ewr_criteria & ~exclusions & ~once", "logic=ewr_criteria & ~once")
    looser = looser.replace("exclusions = dissection | prophylactic\n", "")
    fake = FakeClient([[("submit", {"script": r2})]], [[("submit", {"script": looser})]])
    cs = run(fake, monkeypatch)
    assert cs.script == r2 and "dissection" in json.dumps(cs.expressions[0].expr)      # the first script stands
    a = json.loads((offline / "runs" / "run1" / "criteria_script_audit.json").read_text())
    assert "may only add" in json.dumps(a["turns"][0]["calls"][0]["result"])


def test_removed_conditions_and_caps(offline, monkeypatch):
    _, r2, _ = example()
    extra = r2.replace("prior_failed = C(", 'z = C("zz", "Symptomatic", "q")\nprior_failed = C(').replace(
        "& ~once)", "& z & ~once)", 1)
    cs = run(FakeClient([[("check", {"script": extra})], [("submit", {"script": r2})]], [[("submit", {"script": r2})]]),
             monkeypatch)
    assert [r["id"] for r in cs.removed_conditions] == ["zz"] and "Both routes kept" in cs.removed_conditions[0]["why"]
    monkeypatch.setattr(reduce_script, "MAX_ROUNDS", 3)
    cs = run(FakeClient([[("check", {"script": "x = ("})]] * 5), monkeypatch)
    assert cs.status == "needs_review" and "3 check/submit rounds" in cs.problems[0] and "syntax error" in cs.problems[1]


def test_isolation_and_pitfalls(offline, monkeypatch):
    _, r2, _ = example()
    fake = FakeClient([[("submit", {"script": r2})]], [[("submit", {"script": r2})]])
    run(fake, monkeypatch)
    body = fake.sent[0]["input"]
    order = json.loads(body.split("## The order\n", 1)[1].split("## Codes")[0])
    assert set(order) <= {"procedure", "cpt", "cpt_line", "diagnosis", "age", "sex"}
    assert {t["name"] for t in fake.sent[0]["tools"]} == {"find", "read", "check", "submit"}
    assert "Common mistakes" not in fake.sent[0]["instructions"]
    monkeypatch.setenv("PITFALLS", "1")
    assert "Common mistakes" in reduce_script.instructions("P")


def test_runner_store_is_per_model(monkeypatch):
    import experiments.scripts.reduce_code as R
    monkeypatch.setenv("STEP_H", "script")
    monkeypatch.setenv("MODEL_STRUCTURE", "gpt-6-sol")
    assert R.model_for(False) == "gpt-6-sol"
    assert R.base("gpt-6-sol").parts[-2:] == ("reduce_script", "gpt-6-sol")
    assert R.base("gpt-5.5") != R.base("gpt-6-sol")


def test_heading_arm_sends_only_the_heading(offline, monkeypatch):
    """The product case: the indication is confirmed. Only its heading text reaches the model, as "the confirmed
    indication"; step 1 of the instructions says so instead of asking the model to find it."""
    from experiments.stepH import reduce_tools
    _, r2, _ = example()
    head = "Repeat EWR meets the definition of medical necessity when the criteria above are met"
    for mod, script in ((reduce_script, [[("submit", {"script": r2})]]), (reduce_tools, [[("show", {})]])):
        fake = FakeClient(script, script)
        monkeypatch.setattr(llm, "client", lambda: fake)
        n, sel = sel_for()
        mod.build(split_guideline(WIDGET), n, sel, "k", "run1", Procedure(cpt=["99999"]), indication=head)
        body, ins = fake.sent[0]["input"], fake.sent[0]["instructions"]
        conf = body.split("## The confirmed indication\n", 1)[1].split("## Codes on the order")[0]
        assert conf == head + "\n"
        assert "1. The pathway is given: “" + head in ins and "1. Find the indication(s)" not in ins
        assert "Don't choose or argue another pathway" in ins and "Persist until the tree is exhaustive" in ins
    n, sel = sel_for()
    plain = FakeClient([[("show", {})]])
    monkeypatch.setattr(llm, "client", lambda: plain)
    reduce_tools.build(split_guideline(WIDGET), n, sel, "k", "run2", Procedure(cpt=["99999"]))
    assert "## The confirmed indication" not in plain.sent[0]["input"]           # the find arm: nothing given
    assert "1. Find the indication(s)" in plain.sent[0]["instructions"]


def test_runner_heading_lookup(fl_spans, monkeypatch):
    import experiments.scripts.reduce_code as R
    monkeypatch.setattr(R, "HEADINGS", {("sid", "g", "s1"): "There is demonstrated saphenous reflux",
                                        ("g", "P"): "not printed anywhere"})
    rng, text = R.given({"guideline": "g", "pathway": "P", "scenario_id": "s1"}, fl_spans)
    assert text == "There is demonstrated saphenous reflux" and rng
    assert R.given({"guideline": "g", "pathway": "P", "scenario_id": "s2"}, fl_spans) == ([], None)
