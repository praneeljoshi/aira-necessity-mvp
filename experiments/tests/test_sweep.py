"""Reduce only the given pathway, and persist: the given-pathway prompt has no find step (every arm), script/tools
accept the second passing submit (the first starts the full-policy sweep), the form/code sweep round is add-only, and
notes say what the sweep added. Pure: fake models, tmp_path run logs."""
from __future__ import annotations

import pytest

from app.core import llm
from experiments.stepH import reduce_code, reduce_script, reduce_tools
from app.core.models import Procedure
from app.ingest.spans import split_guideline
from experiments.tests.test_reduce_code import ADL, FakeSession, _sel, tree
from experiments.tests.test_reduce_script import example
from experiments.tests.test_reduce_tools import WIDGET, FakeClient, few_shot, sel_for
from experiments.tests.test_reduce_tools import run as tools_run

HEAD = "Repeat EWR meets the definition of medical necessity when the criteria above are met"
FIND = ("1. Find the indication(s)", "First find which coverage indication")


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "RUNS", tmp_path / "runs")
    return tmp_path


# ---------------------------------------------------------------- the given pathway: no find step


@pytest.mark.parametrize("text", [
    lambda: reduce_tools.instructions("P", HEAD), lambda: reduce_script.instructions("P", HEAD),
    lambda: reduce_code.brief(False, HEAD)])
def test_given_pathway_has_no_find_step(text):
    t = text()
    assert not any(f in t for f in FIND)
    assert f"The pathway is given: “{HEAD}”" in t and "Don't choose or argue another pathway" in t
    assert "keep\neach route (OR)" in t or "keep each route (OR)" in t
    assert "Persist until the tree is exhaustive" in t and "The order states the member's plan." in t


def test_find_arm_keeps_its_find_step():
    assert FIND[0] in reduce_tools.instructions("P") and FIND[1] in reduce_code.brief(True)


# ---------------------------------------------------------------- script / tools: accept the second passing submit


def test_script_accepts_the_second_submit_and_notes_the_sweep(offline, monkeypatch):
    _, r2, _ = example()
    more = r2.replace("prior_failed = C(", 'symptomatic = C("symptomatic", "Symptomatic", "Symptoms?")\nprior_failed = C(') \
        .replace("& ~once)", "& symptomatic & ~once)")
    fake = FakeClient([[("submit", {"script": r2})], [("submit", {"script": more})]], [[("submit", {"script": more})]])
    monkeypatch.setattr(llm, "client", lambda: fake)
    n, sel = sel_for()
    cs = reduce_script.build(split_guideline(WIDGET), n, sel, "k", "run1", Procedure(cpt=["99999"]), indication=HEAD)
    assert cs.status == "ok" and "symptomatic" in {c.id for c in cs.criteria}
    assert "Sweep added: symptomatic" in cs.notes
    first = fake.sent[1]["input"]                          # the host's reply to the first passing submit
    assert "full-policy sweep" in str(first) and '"accepted": false' in str(first)


def test_script_cap_during_sweep_keeps_first_tree(offline, monkeypatch):
    _, r2, _ = example()
    fake = FakeClient([[("submit", {"script": r2})]])                      # then stops talking
    monkeypatch.setattr(llm, "client", lambda: fake)
    n, sel = sel_for()
    cs = reduce_script.build(split_guideline(WIDGET), n, sel, "k", "run1", Procedure(cpt=["99999"]))
    assert cs.status == "ok" and cs.script == r2 and "Sweep: cut off by a cap" in cs.notes


def test_tools_cap_during_sweep_keeps_first_tree(offline, monkeypatch):
    spans = split_guideline(WIDGET)
    cs = tools_run(spans, FakeClient(few_shot(spans)[:-1], [[("submit", {"indication_quotes": []})]]), monkeypatch)
    assert cs.status == "ok" and len(cs.criteria) == 12 and "Sweep: cut off by a cap" in cs.notes


def test_audit_caps_raised():
    assert reduce_tools.AUDIT_CALLS == 60 and reduce_script.AUDIT_CALLS == 60
    assert reduce_tools.MAX_CALLS == 60 and reduce_script.MAX_CALLS == 60          # main caps unchanged


# ---------------------------------------------------------------- form / code: one sweep round, add-only


def swept():
    """The sweep's tree: adds adl, drops size (which must come back)."""
    return tree(conditions=[tree()["conditions"][0], {"id": "adl", "quote": ADL, "question": "ADL?"}],
                expression={"all": ["reflux", "adl"]})


def test_form_sweep_is_add_only(fl_spans, offline, monkeypatch):
    n, sel = _sel(fl_spans)
    answers = {"criteria_form": [tree()], "criteria_form_sweep": [swept()], "criteria_audit": [{}]}
    sent = {}

    def fake(run_id, step, prompt, schema, **_):
        sent.setdefault(step, prompt)
        return schema.model_validate(answers[step].pop(0))
    monkeypatch.setattr(llm, "call", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="form", indication=HEAD)
    from app.decide.evaluate import leaf_ids
    assert set(leaf_ids(cs.expressions[0].expr)) == {"reflux", "adl", "size"}          # size put back, ANDed
    assert {c.id for c in cs.criteria} == {"reflux", "adl", "size"} and cs.status == "ok"
    assert "Sweep added: adl; it dropped size, put back (add-only)" in cs.notes
    assert "Your tree so far" in sent["criteria_form_sweep"] and '"reflux"' in sent["criteria_form_sweep"]
    assert not any(f in sent["criteria_form"] for f in FIND)


def test_code_sweep_is_add_only(fl_spans, offline, monkeypatch):
    n, sel = _sel(fl_spans)
    fake = FakeSession([tree(), swept()])
    monkeypatch.setattr(llm, "CodeSession", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="code", indication=HEAD)
    assert "full-policy sweep" in fake.turns[1] and {c.id for c in cs.criteria} == {"reflux", "adl", "size"}
    assert "Sweep added: adl; it dropped size" in cs.notes
    assert not any(f in fake.files["BRIEF.md"].decode() for f in FIND)


def test_failed_sweep_leaves_first_tree(fl_spans, offline, monkeypatch):
    n, sel = _sel(fl_spans)
    bad = tree(expression={"all": ["reflux", "ghost"]})
    monkeypatch.setattr(llm, "CodeSession", FakeSession([tree(), bad]))
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="code")
    assert {c.id for c in cs.criteria} == {"reflux", "size"} and cs.status == "ok"
    assert "the first tree stands" in cs.notes


def test_runner_tag_is_in_the_cache_key(fl_spans, monkeypatch, tmp_path):
    """A tagged run (--tag sweep) must not reuse an earlier run's cached trees."""
    import experiments.scripts.reduce_code as R
    from app.core import store
    keys = []
    monkeypatch.setattr(R, "guideline", lambda slug: ("g", fl_spans, "s" * 64))
    monkeypatch.setattr(store, "load_criteria", lambda key: (keys.append(key), (None, None))[1])
    monkeypatch.setattr(R.reduce_code, "build", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))
    row = {"guideline": "g", "pathway": "P", "scenario_id": "s1", "cpt": ["36475"]}
    for tag in ("", "sweep"):
        monkeypatch.setattr(R, "TAG", tag)
        R.one(row)
    assert keys[0] != keys[1] and keys[1].endswith("-sweep")


def test_malformed_threshold_is_fed_back_not_a_crash(fl_spans, offline, monkeypatch):
    """form-gpt-5.5 PAP: {"op": "between_inclusive", "min": 31, "max": 91} has no value; it used to crash in to_hout
    before the retry. Now the range feedback goes back and the next answer is used."""
    n, sel = _sel(fl_spans)
    bad = tree()
    bad["conditions"][1]["threshold"] = {"op": "between_inclusive", "min": 31, "max": 91, "unit": "days"}
    answers = {"criteria_form": [bad, tree()], "criteria_form_sweep": [tree()], "criteria_audit": [{}]}
    sent = []

    def fake(run_id, step, prompt, schema, **_):
        sent.append(prompt)
        return schema.model_validate(answers[step].pop(0))
    monkeypatch.setattr(llm, "call", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="form", indication=HEAD)
    assert cs.status == "ok" and "a range is two conditions" in sent[1]


@pytest.mark.parametrize("sweep", [
    lambda schema: (_ for _ in ()).throw(RuntimeError("criteria_form_sweep: model output failed validation twice")),
    lambda schema: schema.model_validate(tree(conditions=[{**tree()["conditions"][1],
                                                           "threshold": {"op": "between", "min": 1, "max": 2}}]))])
def test_invalid_sweep_output_keeps_first_tree(fl_spans, offline, monkeypatch, sweep):
    n, sel = _sel(fl_spans)

    def fake(run_id, step, prompt, schema, **_):
        if step == "criteria_form_sweep":
            return sweep(schema)
        return schema.model_validate(tree() if step == "criteria_form" else {})
    monkeypatch.setattr(llm, "call", fake)
    cs = reduce_code.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), mode="form", indication=HEAD)
    assert cs.status == "ok" and {c.id for c in cs.criteria} == {"reflux", "size"}
    assert "Sweep: output invalid, first tree stands" in cs.notes or "first tree stands" in cs.notes


def test_runner_loads_fixture_guidelines_read_only(monkeypatch, tmp_path):
    """bcbsfl-/cms- fixture slugs have no truth file: the runner copies data/guidelines/<slug>/spans.json (read only)
    into its own store."""
    import json
    import experiments.scripts.reduce_code as R
    from app.core import store
    src = tmp_path / "fixtures" / "cms-x"
    src.mkdir(parents=True)
    body = {"id": "cms-x", "sha256": "a" * 64, "filename": "x.pdf",
            "spans": [{"id": "g0001", "text": "Coverage is limited to adults.", "page": 1}]}
    (src / "spans.json").write_text(json.dumps(body))
    monkeypatch.setattr(R, "FIXTURES", tmp_path / "fixtures")
    monkeypatch.setattr(store, "GUIDELINES", tmp_path / "store")
    monkeypatch.setattr(R, "_GL", {})
    gid, spans, sha = R.guideline("cms-x")
    assert gid == "cms-x" and sha == "a" * 64 and spans[0].text == "Coverage is limited to adults."
    assert json.loads((src / "spans.json").read_text()) == body                 # the fixture is untouched


def test_joined_heading_is_found_part_by_part():
    """61 of 156 headings are "<lead-in> ... <item>": each part is found (the item after the lead-in), one range per
    part, and the model gets the printed parts joined with " ... "."""
    import experiments.scripts.reduce_code as R
    spans = split_guideline("Contents\n2. Ischemic cardiomyopathy (see below)\n\nThe use of the ICD meets the\n"
                            "definition of medical necessity in adults who meet ONE of the following criteria:\n"
                            "1. Ischemic cardiomyopathy with NYHA class II\n2. Ischemic cardiomyopathy with NYHA class I\n")
    head = ("The use of the ICD meets the definition of medical necessity in adults who meet ONE of the following "
            "criteria: ... 2. Ischemic cardiomyopathy")
    row = {"guideline": "g", "pathway": "P"}
    R.HEADINGS[("g", "P")] = head
    try:
        ranges, text = R.given(row, spans)
        ids = [s.id for s in spans]
        assert len(ranges) == 2 and ids.index(ranges[1].first) > ids.index(ranges[0].last)    # the item after the lead-in
        assert next(s.text for s in spans if s.id == ranges[1].first).endswith("NYHA class I")
        assert " ".join(text.split()) == head and text.count(" ... ") == 1
        R.HEADINGS[("g", "P")] = head.replace("2. Ischemic", "7. Ischemic")
        assert R.given(row, spans) == ([], None)                       # a part not printed: the row errors
    finally:
        R.HEADINGS.pop(("g", "P"), None)


def test_joined_heading_named_whole_in_the_instructions():
    ind = "The use of the ICD meets the\ndefinition of medical necessity in adults: ... 2. Ischemic cardiomyopathy"
    assert ("The pathway is given: “The use of the ICD meets the definition of medical necessity in adults: ... 2. "
            "Ischemic cardiomyopathy”") in reduce_tools.instructions("P", ind)
