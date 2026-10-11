"""Where a requirement comes from (review.source_of): a plain citation under its words, the policy's own heading for
that part and the page ("Cited: …, p. N"), else the cited line's first words in quotes; `line` is where it points and
`other` (a warm dot, no commentary) marks a part outside the confirmed indication. Pure: the FL guideline's spans and the stub's step C ranges."""
from __future__ import annotations

from app import review
from tests.test_strikes import world, reqs  # noqa: F401  (the review-flow fixture)
from app.models import Guideline, Narrowed, Payer, Range
from tests.conftest import sid
from tests.fake import narrow_answer


def narrowed(fl_spans, always_on=()) -> Narrowed:
    d = narrow_answer(fl_spans, {})
    return Narrowed(key="k", guideline=Guideline(id="fl", sha256="x", payer=Payer(name="Florida Blue"),
                                                 always_on=[Range(first=a, last=b) for a, b in always_on]),
                    pathways=d["pathways"])


def test_inside_the_confirmed_section(fl_spans):
    n = narrowed(fl_spans)
    line = sid(fl_spans, "The varicosities are at least 3 millimeters")
    s = review.source_of([line], n, ["gsv"], fl_spans)
    assert s == {"other": False, "part": "Great or Small Saphenous Veins", "page": 2, "line": line, "pathway": "gsv",
                 "say": "Cited: Great or Small Saphenous Veins, p. 2"}


def test_another_indication_is_cited_by_its_name_without_commentary(fl_spans):
    n = narrowed(fl_spans)
    s = review.source_of([sid(fl_spans, "The varicosities are at least 3 millimeters")], n, ["accessory"], fl_spans)
    assert s["other"] and s["say"] == "Cited: Great or Small Saphenous Veins, p. 2" and "confirmed" not in s["say"]


def test_a_part_outside_every_section_is_named_by_its_heading(fl_spans):
    n = narrowed(fl_spans)
    line = sid(fl_spans, "Reimburse according to operative report")
    s = review.source_of([line], n, ["gsv"], fl_spans)
    assert s["other"] and s["say"] == "Cited: Reimbursement information, p. 7" and s["page"] == 7 and s["line"] == line
    d = sid(fl_spans, "Tributaries: veins that empty")
    assert review.source_of([d], n, ["gsv"], fl_spans)["say"].startswith("Cited: Definitions, p. ")


def test_the_part_for_every_request(fl_spans):
    line = sid(fl_spans, "Reimburse according to operative report")
    n = narrowed(fl_spans, always_on=[(line, line)])
    s = review.source_of([line], n, ["gsv"], fl_spans)
    assert s["other"] and s["say"] == "Cited: Reimbursement information, p. 7"


def test_the_first_line_outside_decides_and_nothing_without_lines(fl_spans):
    n = narrowed(fl_spans)
    inside, outside = sid(fl_spans, "The varicosities are at least 3 millimeters"), sid(fl_spans, "Reimburse according to operative report")
    assert review.source_of([inside, outside], n, ["gsv"], fl_spans)["part"] == "Reimbursement information"
    assert review.source_of([], n, ["gsv"], fl_spans) is None
    assert review.source_of([inside], None, ["gsv"], fl_spans) is None


def test_the_case_carries_each_requirements_source(world):
    d = world.doc(world.case())
    src = {k: v["source"] for k, v in reqs(d).items()}
    assert src["size"]["say"] == "Cited: Great or Small Saphenous Veins, p. 2" and not src["size"]["other"] and src["size"]["line"]
    assert all(v and not v["other"] for v in src.values())


def test_no_heading_cites_the_lines_first_words(fl_spans, monkeypatch):
    from app import ask
    n = narrowed(fl_spans)
    line = sid(fl_spans, "Reimburse according to operative report")
    monkeypatch.setattr(ask, "heading_above", lambda *a: None)
    s = review.source_of([line], n, ["gsv"], fl_spans)
    assert s["other"] and s["part"] is None and s["say"].startswith("Cited: “Reimburse according to operative report") and s["say"].endswith(", p. 7")
    assert review._first_words("• Treatment of accessory saphenous veins by surgery") == "Treatment of accessory saphenous veins…"
