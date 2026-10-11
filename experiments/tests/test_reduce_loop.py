"""STEP_H=loose-loop: the external fixpoint loop (fixpoint, cycle, cap, check failure, removals, canonical form), and
STEP_H=loose given the runner's inputs, with the original loose prompts byte-identical. Pure: a scripted fake model."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.checklist import criteria
from app.core import llm
from experiments.stepH import reduce_loop
from app.core.models import Procedure
from tests.stepH_fake import ADL, HEAD, REFLUX, SIZE, C, H, _sel, offline, pid, script  # noqa: F401

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
EXP_PROMPTS = Path(__file__).resolve().parents[2] / "experiments" / "stepH" / "prompts"


def run(fl_spans, **kw):
    n, sel = _sel(fl_spans)
    return reduce_loop.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"], plan="commercial"),
                             extra={"age": 58}, indication=HEAD, **kw)


# ---------------------------------------------------------------- the loop


def test_fixpoint_at_round_3_ignores_ids_and_order(fl_spans, offline, monkeypatch):
    p = pid(fl_spans)
    a = H(p, "reflux", C("reflux", REFLUX))
    b = H(p, "reflux AND size", C("reflux", REFLUX), C("size", SIZE, threshold={"op": ">=", "value": 3, "unit": "mm"}))
    b2 = H(p, "s3 AND r1", C("s3", SIZE, threshold={"op": ">=", "value": 3, "unit": "mm"}), C("r1", REFLUX))  # renamed
    sent = script(monkeypatch, [a, b, b2])
    cs = run(fl_spans)
    assert cs.loop["reason"] == "fixpoint" and cs.loop["converged"] and cs.loop["rounds"] == 3
    assert cs.loop["counts"] == [1, 2, 2] and cs.loop["added"][0] == {"round": 2, "ids": ["size"]}
    assert cs.status == "ok" and "Loop: fixpoint after 3 rounds" in cs.notes
    loops = [x for s, x in sent if s == "criteria_loop"]
    assert "Be exhaustive" in loops[0] and "Your previous extraction" not in loops[0]
    assert "Your previous extraction" in loops[1] and '"reflux"' in loops[1].split("Your previous extraction")[1]
    assert [s for s, _ in sent][-1] == "criteria_audit"                   # the audit once, after the fixpoint
    assert HEAD in loops[0] and "age 58" in loops[0] and "plan: commercial" in loops[0]


def test_cycle_keeps_the_bigger(fl_spans, offline, monkeypatch):
    p = pid(fl_spans)
    a = H(p, "reflux", C("reflux", REFLUX))
    b = H(p, "reflux AND adl", C("reflux", REFLUX), C("adl", ADL))
    script(monkeypatch, [a, b, a])
    cs = run(fl_spans)
    assert cs.loop["reason"] == "cycle" and not cs.loop["converged"] and cs.loop["kept_round"] == 2
    assert {c.id for c in cs.criteria} == {"reflux", "adl"} and cs.status == "ok"
    assert "Loop: no fixpoint after 3 rounds (cycle)" in cs.notes


def test_cap_keeps_the_larger_of_the_last_two(fl_spans, offline, monkeypatch):
    monkeypatch.setattr(reduce_loop, "MAX_ROUNDS", 3)
    p = pid(fl_spans)
    script(monkeypatch, [H(p, "reflux", C("reflux", REFLUX)),
                         H(p, "reflux AND adl AND size", C("reflux", REFLUX), C("adl", ADL), C("size", SIZE)),
                         H(p, "reflux AND size", C("reflux", REFLUX), C("size", SIZE))])
    cs = run(fl_spans)
    assert cs.loop["reason"] == "cap" and cs.loop["rounds"] == 3 and cs.loop["kept_round"] == 2
    assert len(cs.criteria) == 3 and "Loop: no fixpoint after 3 rounds (cap)" in cs.notes


def test_removal_is_logged_with_the_models_reason(fl_spans, offline, monkeypatch):
    p = pid(fl_spans)
    ab = H(p, "reflux AND size", C("reflux", REFLUX), C("size", SIZE))
    a = H(p, "reflux", C("reflux", REFLUX), notes="size belongs to the other route; removed")
    script(monkeypatch, [ab, a, json.loads(json.dumps(a))])
    cs = run(fl_spans)
    assert cs.loop["removed"] == [{"round": 2, "ids": ["size"], "why": "size belongs to the other route; removed"}]
    assert "Loop removed in round 2: size. The model's notes: size belongs to the other route" in cs.notes
    assert {c.id for c in cs.criteria} == {"reflux"}                      # not add-only here


def test_check_failure_mid_loop_keeps_the_last_valid_tree(fl_spans, offline, monkeypatch):
    p = pid(fl_spans)
    good = H(p, "reflux AND size", C("reflux", REFLUX), C("size", SIZE))
    bad = H(p, "reflux AND ghost", C("reflux", REFLUX), C("ghost", "a sentence printed nowhere in the policy"))
    script(monkeypatch, [good, bad, bad])                                 # round 2 and its retry
    cs = run(fl_spans)
    assert cs.loop["reason"] == "check-fail" and cs.loop["kept_round"] == 1 and cs.status == "ok"
    assert {c.id for c in cs.criteria} == {"reflux", "size"} and "round 1) stands" in cs.notes


def test_canonical_form():
    from app.core.models import Criterion, Expression, Threshold
    a = [Criterion(id="x", refs=[], quote="There is  demonstrated\nreflux.", question="q1"), Criterion(id="y", refs=[], quote="B", question="q")]
    b = [Criterion(id="y2", refs=[], quote="B", question="other wording"), Criterion(id="x2", refs=[], quote="there is demonstrated reflux", question="q")]
    ea = [Expression(pathway="p", expr={"all": ["x", {"not": "y"}]})]
    eb = [Expression(pathway="p", expr={"all": [{"not": "y2"}, "x2"]})]
    assert reduce_loop.canonical(a, ea) == reduce_loop.canonical(b, eb)
    flipped = [Expression(pathway="p", expr={"all": ["x2", "y2"]})]       # polarity changed
    assert reduce_loop.canonical(b, flipped) != reduce_loop.canonical(b, eb)
    b[0] = Criterion(id="y2", refs=[], quote="B", question="q", threshold=Threshold(op="gte", value=3, unit="mm"))
    assert reduce_loop.canonical(b, eb) != reduce_loop.canonical(a, ea)   # a threshold is a change


# ---------------------------------------------------------------- loose: same inputs, prompts unchanged


def test_original_loose_prompts_unchanged():
    # approved 2026-10-10: admin flag
    sha = {"criteria_guideline.md": "25aeb5c67c521df207a8238700d4da4d17e31b66e009a8c3f2423837ee513ecd",
           "criteria_audit.md": "b6d0c075684446077687b2b1fbaf3081f13689b51b6518765a2e1fbf011cc5c6"}
    for name, want in sha.items():
        assert hashlib.sha256((PROMPTS / name).read_bytes()).hexdigest() == want, name
    loop = (EXP_PROMPTS / "criteria_guideline_loop.md").read_text()
    orig = (PROMPTS / "criteria_guideline.md").read_text()
    assert loop.replace(loop[loop.index("## Be exhaustive"):loop.index("## The guideline")], "") == orig


def test_loose_gets_the_runner_inputs_and_writes_spend(fl_spans, offline, monkeypatch):
    p = pid(fl_spans)
    sent = script(monkeypatch, [H(p, "reflux", C("reflux", REFLUX))])
    n, sel = _sel(fl_spans)
    cs = reduce_loop.loose(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"], plan="commercial"),
                           extra={"age": 58, "sex": "F"}, indication=HEAD + " ... from the list")
    first = sent[0][1]
    assert sent[0][0] == "criteria_guideline" and "Be exhaustive" not in first
    assert "age 58; sex F" in first and f"“{HEAD} ... from the list”" in first and "plan: commercial" in first
    assert cs.status == "ok" and (offline / "runs" / "r" / "criteria_loose-cost.json").exists()


def test_loose_defaults_render_as_before(fl_spans):
    """No runner inputs: the request line and the pathway line are what they were."""
    n, sel = _sel(fl_spans)
    p = Procedure(cpt=["36475"], target="great saphenous vein", diagnosis="I83.12")
    assert criteria.request_line(p) == "codes 36475; treating great saphenous vein; diagnosis I83.12"
    assert criteria.request_line(None) == "(not given)"
    assert criteria._pathways(n, criteria.picked(sel), fl_spans).startswith("- `")


@pytest.mark.parametrize("mode,fn", [("loose", "loose"), ("loose-loop", "build")])
def test_runner_dispatch(fl_spans, monkeypatch, mode, fn):
    import experiments.scripts.reduce_code as R
    from app.core import store
    monkeypatch.setenv("STEP_H", mode)
    monkeypatch.setattr(R, "guideline", lambda slug: ("g", fl_spans, "s" * 64))
    monkeypatch.setattr(store, "load_criteria", lambda key: (None, None))
    got = {}

    def fake(*a, **k):
        got.update(k)
        raise RuntimeError("dispatched")
    monkeypatch.setattr(reduce_loop, fn, fake)
    out = R.one({"guideline": "g", "pathway": "P", "cpt": ["36475"], "age": 58})
    assert "dispatched" in out["error"] and got["extra"]["age"] == 58
    assert R.base("gpt-6-sol").parts[-2:] == ("reduce_loose", "gpt-6-sol")
