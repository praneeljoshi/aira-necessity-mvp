"""A2's coverage check: chart lines in no section are problems, one per run, and the existing retry fills them."""
from __future__ import annotations

import pytest

from app.core import llm
from app.core.models import Span
from app.ingest import sections

ID = "in no section"


@pytest.fixture
def chart():
    return [Span(id=f"r{i:04d}", text=f"line {i}", page=1) for i in range(1, 101)]


def out(*ranges, label="evidence"):
    return sections.SOut(sections=[sections.Section(title=f"s{k}", label=label, spans=[{"first": a, "last": b}])
                                   for k, (a, b) in enumerate(ranges)])


def gaps(o, spans):
    return [p for p in sections.check(o, spans) if ID in p]


def test_full_coverage(chart):
    assert sections.check(out(("r0001", "r0040"), ("r0041", "r0100")), chart) == []
    assert sections.check(out(("r0001", "r0100"), ("r0010", "r0020")), chart) == []      # overlap is fine


def test_gap_in_the_middle(chart):
    assert sections.check(out(("r0001", "r0040"), ("r0046", "r0100")), chart) == [
        "lines r0041-r0045 are in no section: add the section(s) they belong to with their label"]
    assert sections.check(out(("r0001", "r0040"), ("r0042", "r0100")), chart) == [
        "line r0041 is in no section: add the section it belongs to with its label"]


def test_uncovered_tail_and_head(chart):
    assert gaps(out(("r0003", "r0090")), chart) == [
        "lines r0001-r0002 are in no section: add the section(s) they belong to with their label",
        "lines r0091-r0100 are in no section: add the section(s) they belong to with their label"]


def test_bad_range_covers_nothing(chart):
    p = sections.check(out(("r0001", "r0040"), ("r0041", "r9999"), ("r0080", "r0060"), ("r0081", "r0100")), chart)
    assert any("not r9999" in x for x in p) and any("runs backwards" in x for x in p)
    assert [x for x in p if ID in x] == [
        "lines r0041-r0080 are in no section: add the section(s) they belong to with their label"]


def test_cap(chart):
    o = out(*[(f"r{i:04d}", f"r{i:04d}") for i in range(1, 101, 2)])        # every other line: 50 one-line runs
    p = sections.check(o, chart)
    assert len(p) == sections.GAPS + 1
    assert p[0] == "line r0002 is in no section: add the section it belongs to with its label"
    assert p[-1] == "... and 25 more runs of lines in no section (25 lines): add their sections too"
    assert sections.check(sections.SOut(), chart) == [
        "lines r0001-r0100 are in no section: add the section(s) they belong to with their label"]


def _split(chart, monkeypatch, *answers):
    sent = []
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "call", lambda rid, step, prompt, schema, **_: sent.append(prompt) or answers[len(sent) - 1])
    return sections.split(chart, "r"), sent


def test_retry_fills_the_gap(chart, monkeypatch):
    first, fixed = out(("r0001", "r0040"), ("r0046", "r0100")), out(("r0001", "r0100"))
    o, sent = _split(chart, monkeypatch, first, fixed)
    assert len(sent) == 2 and "lines r0041-r0045 are in no section" in sent[1]
    assert o is fixed
    assert {f"r{i:04d}" for i in range(41, 46)} <= {s.id for s in sections.evidence(o, chart)}


def test_no_gap_no_retry(chart, monkeypatch):
    whole = out(("r0001", "r0100"))
    o, sent = _split(chart, monkeypatch, whole)
    assert o is whole and len(sent) == 1


def test_worse_retry_is_dropped(chart, monkeypatch):
    first, worse = out(("r0001", "r0040"), ("r0046", "r0100")), out(("r0001", "r0010"))
    o, _ = _split(chart, monkeypatch, first, worse)
    assert o is first


def test_better_by_lines_not_by_problem_count(chart, monkeypatch):
    # an empty answer is one problem (one run); a retry leaving three one-line gaps is three problems but 3 lines, not 100
    better = out(("r0001", "r0009"), ("r0011", "r0049"), ("r0051", "r0089"), ("r0091", "r0100"))
    assert len(sections.check(better, chart)) == 3 > len(sections.check(sections.SOut(), chart)) == 1
    o, _ = _split(chart, monkeypatch, sections.SOut(), better)
    assert o is better
