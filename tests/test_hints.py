"""Known-structure hints (app/hints.py, STRUCTURE_HINTS=1): a payer block before "## The guideline" in step H (loose
and loose-next, main and audit), a clinic block before "## Chart" in A2 and the judge; byte-identical prompts when the
flag is off or nothing (or more than one file) matches; the hint's name + hash in the cache keys only when applied.
Pure: placeholder hints under tests/fixtures/hints, a scripted fake model, tmp_path only."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app import criteria, hints, judge, llm, pipeline, reduce_next, sections, store
from app.models import CriteriaSet, Order, Procedure
from tests.test_reduce_code import REFLUX, _sel
from tests.test_reduce_loop import HEAD, C, H, offline, pid, script  # noqa: F401

FIX = Path(__file__).resolve().parent / "fixtures" / "hints"
PAYER = "## What this payer's guidelines look like\n"
CLINIC = "## What this clinic's charts look like\n"
PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


@pytest.fixture
def hinted(monkeypatch):
    """Hints read from the placeholder fixtures; returns a setter for the flag."""
    monkeypatch.setattr(hints, "DIR", FIX)

    def on(flag: bool = True):
        monkeypatch.setenv("STRUCTURE_HINTS", "1" if flag else "0")
    return on


@pytest.fixture
def nomatch(tmp_path, monkeypatch):
    """A hints dir whose files match nothing in the FL guideline or the Delgado chart."""
    d = tmp_path / "hints"
    for kind in ("payers", "clinics"):
        (d / kind).mkdir(parents=True)
        (d / kind / "other.md").write_text("---\nmatch:\n  - Nobody Health Plan Of Nowhere\n---\nNever shown.\n")
    return d


def _payer_body():
    return hints.parse((FIX / "payers" / "placeholder-fl.md").read_text(), "placeholder-fl").text


def _clinic_body():
    return hints.parse((FIX / "clinics" / "placeholder-gulf-coast.md").read_text(), "placeholder-gulf-coast").text


def _inserted(plain: str, hinted: str, heading: str, title: str, body: str) -> None:
    """`hinted` is `plain` with exactly the block added, just before the heading line."""
    at = plain.index("\n" + heading + "\n") + 1
    assert hinted == plain[:at] + title + body + "\n\n" + plain[at:]


# ---------------------------------------------------------------- the module


def test_parse_and_match(fl_spans, delgado_spans, hinted):
    hinted(True)
    assert hints.payer_hint(fl_spans) == ("placeholder-fl", _payer_body())
    assert hints.clinic_hint(delgado_spans) == ("placeholder-gulf-coast", _clinic_body())
    assert hints.payer_hint(delgado_spans) == (None, "") and hints.clinic_hint(fl_spans) == (None, "")
    assert hints.payer_id(fl_spans).startswith("placeholder-fl.") and len(hints.payer_id(fl_spans)) == len("placeholder-fl.") + 8
    h = hints.parse("---\nmatch: [A b, \"C\"]\nwhere: first 5 lines\n---\nbody\n", "x")
    assert h.match == ("A b", "C") and h.lines == 5 and h.text == "body"
    assert hints.parse("no front matter", "x") is None and hints.parse("---\nwhere: first 3 lines\n---\nbody", "x") is None


def test_where_limits_the_lines_searched(fl_spans, tmp_path, monkeypatch):
    (tmp_path / "payers").mkdir()
    (tmp_path / "payers" / "deep.md").write_text("---\nmatch:\n  - position statement:\nwhere: first 10 lines\n---\nx\n")
    monkeypatch.setattr(hints, "DIR", tmp_path)
    monkeypatch.setenv("STRUCTURE_HINTS", "1")
    assert hints.payer_hint(fl_spans)[0] is None           # POSITION STATEMENT: is line 33
    (tmp_path / "payers" / "deep.md").write_text("---\nmatch:\n  - position statement:\n---\nx\n")
    assert hints.payer_hint(fl_spans)[0] == "deep"          # default: the first 40 lines, case-insensitive


def test_flag_off_and_two_matches_give_none(fl_spans, delgado_spans, hinted, tmp_path, monkeypatch):
    hinted(False)
    assert hints.payer_hint(fl_spans) == (None, "") and hints.clinic_hint(delgado_spans) == (None, "")
    monkeypatch.delenv("STRUCTURE_HINTS")
    assert hints.payer_hint(fl_spans) == (None, "")         # default "0"
    d = tmp_path / "two"
    shutil.copytree(FIX, d)
    shutil.copy(d / "payers" / "placeholder-fl.md", d / "payers" / "also-fl.md")
    shutil.copy(d / "clinics" / "placeholder-gulf-coast.md", d / "clinics" / "also-gulf.md")
    monkeypatch.setattr(hints, "DIR", d)
    hinted(True)
    assert hints.payer_hint(fl_spans) == (None, "") and hints.clinic_hint(delgado_spans) == (None, "")
    assert hints.payer_id(fl_spans) is None and hints.clinic_id(delgado_spans) is None


def test_shipped_hint_files_parse_and_match_nothing_internal():
    """The shipped hint files (QA, guideline-reduce 3d96dcf) all parse with front matter; no test/internal file ships."""
    from app import hints
    files = sorted(p for p in (hints.DIR).glob("*/*.md"))
    assert files, "prompts/hints/ should carry the QA hint files"
    for f in files:
        assert f.read_text().startswith("---"), f
        assert "internal-test" not in f.name and not f.name.endswith(".evidence.md"), f

def _h_prompts(fl_spans, monkeypatch, next_: bool):
    sent = script(monkeypatch, [H(pid(fl_spans), "reflux", C("reflux", REFLUX))])
    n, sel = _sel(fl_spans)
    if next_:
        reduce_next.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), indication=HEAD)
    else:
        criteria.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), indication=HEAD)
    (s1, main), (s2, aud) = sent
    assert (s1, s2) == ("criteria_guideline", "criteria_audit")
    return main, aud


@pytest.mark.parametrize("next_", [False, True], ids=["loose", "loose-next"])
def test_step_h_main_and_audit(fl_spans, offline, monkeypatch, hinted, nomatch, next_):
    hinted(False)
    plain = _h_prompts(fl_spans, monkeypatch, next_)
    hinted(True)
    got = _h_prompts(fl_spans, monkeypatch, next_)
    for p, g in zip(plain, got):
        _inserted(p, g, "## The guideline", PAYER, _payer_body())
    monkeypatch.setattr(hints, "DIR", nomatch)               # flag on, nothing matches: byte-identical
    assert _h_prompts(fl_spans, monkeypatch, next_) == plain
    # flag off is the shipped prompt itself, rendered as before
    n, sel = _sel(fl_spans)
    v = criteria.inputs(fl_spans, n, sel, Procedure(cpt=["36475"]), None, HEAD)[1]
    assert plain[0] == llm.prompt(reduce_next.PROMPT if next_ else "criteria_guideline", **v)
    assert PAYER not in plain[1]


def _a2_prompt(spans, monkeypatch):
    sent = []
    monkeypatch.setattr(llm, "call", lambda rid, step, prompt, schema, **_: sent.append(prompt) or schema())
    sections.split(spans, "r")
    return sent[0]


def _judge_prompt(spans, fl_spans, monkeypatch, **kw):
    sent = []
    monkeypatch.setattr(llm, "call", lambda rid, step, prompt, schema, **_: sent.append(prompt) or schema(verdicts=[]))
    judge.judge(spans, CriteriaSet(key="k"), [], fl_spans, Order(procedure=Procedure(cpt=["36475"])), "r", **kw)
    return sent[0]


def test_a2_and_judge(delgado_spans, fl_spans, offline, monkeypatch, hinted, nomatch):
    hinted(False)
    a2, ju = _a2_prompt(delgado_spans, monkeypatch), _judge_prompt(delgado_spans, fl_spans, monkeypatch)
    assert a2 == llm.prompt("chart_sections", chart_spans=sections.render_chart(delgado_spans))
    hinted(True)
    _inserted(a2, _a2_prompt(delgado_spans, monkeypatch), "## Chart", CLINIC, _clinic_body())
    _inserted(ju, _judge_prompt(delgado_spans, fl_spans, monkeypatch), "## Chart", CLINIC, _clinic_body())
    # the pipeline hands the judge the hint read from the whole chart (its evidence lines may lack the letterhead)
    ev = delgado_spans[20:]
    plain_ev = _judge_prompt(ev, fl_spans, monkeypatch)
    assert CLINIC not in plain_ev
    _inserted(plain_ev, _judge_prompt(ev, fl_spans, monkeypatch, hint=hints.clinic_hint(delgado_spans)[1]),
              "## Chart", CLINIC, _clinic_body())
    monkeypatch.setattr(hints, "DIR", nomatch)
    assert _a2_prompt(delgado_spans, monkeypatch) == a2 and _judge_prompt(delgado_spans, fl_spans, monkeypatch) == ju


def test_heading_missing_leaves_the_prompt_alone():
    assert hints.for_guideline("no heading here\n", "x") == "no heading here\n"
    assert hints.for_chart("## Chart\n{x}", "") == "## Chart\n{x}"
    assert hints.for_chart("a\n## Charter\n## Chart\nb", "T") == f"a\n## Charter\n{CLINIC}T\n\n## Chart\nb"


# ---------------------------------------------------------------- cache keys and status


def test_h_keys_change_only_when_the_hint_applies(fl_spans, delgado_spans, offline, monkeypatch, hinted, nomatch):
    n, _ = _sel(fl_spans)
    p, sha = Procedure(cpt=["36475"]), "s" * 64
    monkeypatch.setenv("STEP_H", "loose")
    hinted(False)
    k, h = pipeline.cache_key(sha, p), pipeline.h_cache_key(sha, n, ["gsv"], p)
    assert pipeline.cache_key(sha, p, fl_spans) == k and pipeline.h_cache_key(sha, n, ["gsv"], p, fl_spans) == h
    hinted(True)
    assert pipeline.cache_key(sha, p) == k                     # no guideline lines given: as before
    assert pipeline.cache_key(sha, p, delgado_spans) == k      # nothing matches
    k2, h2 = pipeline.cache_key(sha, p, fl_spans), pipeline.h_cache_key(sha, n, ["gsv"], p, fl_spans)
    assert k2 != k and h2 != h and k2.rsplit("-v", 1)[0] == k.rsplit("-v", 1)[0]
    assert pipeline.prompt_version(hint=hints.payer_id(fl_spans)) == k2.rsplit("-v", 1)[1]
    monkeypatch.setenv("STEP_H", "loose-next")
    assert pipeline.cache_key(sha, p, fl_spans) != pipeline.cache_key(sha, p)
    monkeypatch.setenv("STEP_H", "code")                       # a mode that does not inject it: key unchanged
    assert pipeline.cache_key(sha, p, fl_spans) == pipeline.cache_key(sha, p)
    monkeypatch.setenv("STEP_H", "loose")
    monkeypatch.setattr(hints, "DIR", nomatch)
    assert pipeline.cache_key(sha, p, fl_spans) == k


def test_a2_cache_keeps_the_clinic_hint(tmp_store, delgado_spans, monkeypatch, hinted):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    out = sections.SOut()
    calls = []
    monkeypatch.setattr(sections, "split", lambda sp, rid: calls.append(1) or out)
    hinted(False)
    pipeline.evidence_for("c1", delgado_spans, "r")
    pipeline.evidence_for("c1", delgado_spans, "r")
    assert calls == [1]
    import json
    assert "hint" not in json.loads((store.CHARTS / "c1" / "sections.json").read_text())
    hinted(True)                                               # the hint now applies: labels made without it miss
    pipeline.evidence_for("c1", delgado_spans, "r")
    pipeline.evidence_for("c1", delgado_spans, "r")
    assert calls == [1, 1]
    assert json.loads((store.CHARTS / "c1" / "sections.json").read_text())["hint"] == hints.clinic_id(delgado_spans)
    hinted(False)
    pipeline.evidence_for("c1", delgado_spans, "r")
    assert calls == [1, 1, 1]


def test_status_records_the_hints(fl_spans, delgado_spans, monkeypatch, hinted):
    class St:
        doc: dict = {}
    st = St()
    monkeypatch.setenv("STEP_H", "loose")
    hinted(False)
    pipeline._hints_meta(st, fl_spans, delgado_spans)
    assert st.doc["hints"] == {"payer": None, "clinic": None}
    hinted(True)
    pipeline._hints_meta(st, fl_spans, delgado_spans)
    assert st.doc["hints"] == {"payer": "placeholder-fl", "clinic": "placeholder-gulf-coast"}
    monkeypatch.setenv("STEP_H", "code")
    pipeline._hints_meta(st, fl_spans, delgado_spans)
    assert st.doc["hints"] == {"payer": None, "clinic": "placeholder-gulf-coast"}
