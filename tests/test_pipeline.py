"""The whole flow offline: A..L with the stub model, the store in tmp_path."""
from __future__ import annotations

import hashlib
import re

import pytest

from app import pipeline
from app.checklist import keys
from app.checklist import criteria
from app.core import llm, store
from app.evidence import judge
from app.understand import narrow
from app.core.models import CriteriaSet, Criterion, Order, Procedure, Span, Threshold, Verdict
from app.understand.select import select
from app.ingest.spans import expand
from tests.conftest import SAMPLES, rng, sid
from tests.fake import Stub, cosmetic_range, criteria_answer, narrow_answer

DENIAL = ("denied", "will deny", "deny without", "denial", "not eligible", "will not be covered", "cannot be approved", "is denied")
# deny-predicting words anywhere in an ask, packet or message ("Florida Blue will deny without it" shipped once);
# whole words, so a chart quote's "denies" is not caught
DENY = re.compile(r"\b(will deny|would deny|deny|denied|denial)\b", re.I)


def assert_no_denial(text: str):
    low = text.lower()
    assert not any(w in low for w in DENIAL), text
    assert not DENY.search(text), text
    return True


@pytest.fixture
def setup(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    def go(override=None, **kw):
        stub = Stub(fl_spans, delgado_spans, **kw)
        monkeypatch.setattr(llm, "call", stub)
        r = pipeline.run("", "delgado", gid, rspans=delgado_spans, source="cli", override=override)
        return r, stub
    return go


def test_met_ready(setup):
    r, stub = setup()
    assert stub.calls == ["detect_order", "narrow_guideline", "criteria_guideline", "criteria_audit", "chart_sections", "judge_chart"]
    assert r.determination == "MET" and r.queue == "ready", r.review_reasons
    assert r.pathway_used == ["gsv"]
    comp = next(c for c in r.checklist if c.criterion == "compression")
    assert [q.date for q in comp.quotes] == ["2025-03-18", "2025-07-22"]
    # the judge cited line ranges: the quote is the lines joined, the label is the wrapped requirement joined
    assert all("-" in q.span for q in comp.quotes)
    assert "Begin conservative management: graduated compression stockings 20–30 mmHg daily, leg elevation" in comp.quotes[0].text
    assert comp.text == "conservative management including compression therapy for at least 3 months has not improved the symptoms"
    assert r.ask.startswith("Nothing to ask")
    assert all(q.text for p in r.packet for q in p.quotes)


def test_cache_second_order_skips_c_and_h(setup):
    setup()
    _, stub = setup()
    assert stub.calls == ["detect_order", "judge_chart"]


def test_insufficient_asks_for_dates(setup):
    r, _ = setup(verdicts={"compression": {"status": "INSUFFICIENT", "for": []}})
    assert r.determination == "INSUFFICIENT" and r.queue == "review"
    assert [m.criterion for m in r.misses] == ["compression"]
    assert "addendum" in r.ask and "began" in r.ask
    assert_no_denial(r.ask)
    assert_no_denial(" ".join(m.ask for m in r.misses))


def test_not_met_without_against_becomes_insufficient(setup):
    r, _ = setup(verdicts={"size": {"status": "NOT_MET", "against": []}})
    assert r.determination == "INSUFFICIENT"


def test_contradiction_routes_review_and_asks(setup):
    r, _ = setup(verdicts={"size": {"status": "NOT_MET", "against": [sid_(setup, "Competent. No reflux. Diameter 2.8 mm.")]}})
    assert r.determination == "NOT_MET" and r.queue == "review"
    assert "could you review" in r.ask and "how would you like to proceed" in r.ask
    assert_no_denial(r.ask)


def _delgado():
    from app.ingest.pdf import pdf_to_text
    from app.ingest.spans import split_chart
    return split_chart(pdf_to_text(SAMPLES / "synthetic" / "maria_delgado_chart.pdf"))


def sid_(_, needle):
    return sid(_delgado(), needle)


def rng_(first, last):
    return rng(_delgado(), first, last)


def test_short_duration_flags(setup):
    r, _ = setup(verdicts={"compression": {"status": "MET", "for": [sid_(0, "Begin conservative management"), sid_(0, "Reflux at saphenofemoral junction 2.4")],
                                           "dates": [{"span": sid_(0, "Begin conservative management"), "date": "March 18, 2025"},
                                                     {"span": sid_(0, "Reflux at saphenofemoral junction 2.4"), "date": "March 25, 2025"}]}})
    assert r.queue == "review"
    assert any("less than the 3 required" in x for x in r.review_reasons)


def test_unverified_date_and_measurement_flag(setup):
    r, _ = setup(verdicts={"size": {"status": "MET", "for": [sid_(0, "Unchanged varicosities")],
                                    "measurements": [{"value": "9", "unit": "mm", "span": sid_(0, "Unchanged varicosities")}]}})
    assert any("measurement" in x for x in r.review_reasons)


def test_judge_dates_shown_only_when_cited_and_written(setup):
    """A date for a cited span written in its note is shown; a date for a span not cited is dropped; a date written
    nowhere near its span stays unverified, is not shown, and (not a duration) sends nothing to review."""
    from app.ingest.spans import table
    size, ceap, dvt = rng_("Unchanged varicosities medial left thigh", "ulcer."), sid_(0, "CEAP clinical class C4a"), sid_(0, "Denies history of DVT")
    r, _ = setup(verdicts={"size": {"status": "MET", "for": [size, ceap], "measurements": [{"value": "6", "unit": "mm", "span": size}],
                                    "dates": [{"span": size, "date": "July 22, 2025"}, {"span": dvt, "date": "March 18, 2025"},
                                              {"span": ceap, "date": "January 2, 2020"}]}})
    assert r.queue == "ready", r.review_reasons
    item = next(c for c in r.checklist if c.criterion == "size")
    assert item.quotes[0].date == "2025-07-22"
    v = Verdict.model_validate(store.load_result("delgado")["verdicts"]["size"])
    assert [(d.span, d.iso) for d in v.dates] == [(size, "2025-07-22"), (ceap, None)]
    rt = table(_delgado())
    assert judge.quote_date(v, ceap, rt) is None and judge.quote_date(v, dvt, rt) is None
    assert judge.quote_date(v, size.split("-")[0], rt) == "2025-07-22"     # a line inside the cited range


def test_measurements_both_sides(setup):
    a, b = sid_(0, "Unchanged varicosities"), sid_(0, "Competent. No reflux. Diameter 2.8 mm.")
    r, _ = setup(verdicts={"size": {"status": "MET", "for": [a], "measurements": [{"value": "6", "span": a}, {"value": "2.8", "span": b}]}})
    assert any("both sides" in x for x in r.review_reasons)


def test_judge_ranges_resolve_and_a_bad_range_is_flagged(setup):
    # a measurement cited as a range is checked against the joined text; a date in a range's heading verifies
    size = rng_("Unchanged varicosities medial left thigh", "ulcer.")
    r, _ = setup(verdicts={"size": {"status": "MET", "for": [size], "measurements": [{"value": "6", "unit": "mm", "span": size}],
                                    "dates": [{"span": size, "date": "July 22, 2025"}]}})
    assert r.determination == "MET" and r.queue == "ready", r.review_reasons
    item = next(c for c in r.checklist if c.criterion == "size")
    assert item.quotes[0].span == size and item.quotes[0].text.endswith("1+ edema. No ulcer.") and item.quotes[0].date == "2025-07-22"
    # against as a range for NOT_MET
    r, _ = setup(verdicts={"ulcer": {"status": "NOT_MET", "against": [rng_("Left leg: prominent tortuous", "No ulceration.")]}})
    assert r.determination == "MET"      # ulcer is one alternative; the others still carry the section
    # a range whose end is not in the chart is dropped and flagged
    r, _ = setup(verdicts={"ceap": {"status": "MET", "for": [sid_(0, "CEAP clinical class C4a") + "-r9999"]}})
    assert r.queue == "review" and any("could not be found" in x for x in r.review_reasons)


def test_not_covered_code_stops_before_criteria(setup):
    r, stub = setup(override={"cpt": ["36468"], "target": "spider veins"})
    assert r.determination == "NOT_COVERED" and r.queue == "cant_check"
    assert stub.calls == ["detect_order", "narrow_guideline"]
    assert "36468" in r.ask and "?" in r.ask
    assert_no_denial(r.ask)


def test_code_not_written_in_chart_is_dropped(setup):
    r, _ = setup(order={"cpt": ("36468",)})
    assert r.determination == "CANT_CHECK"
    assert "doesn't match" not in r.reason          # no code is not a mismatch


def test_code_not_in_table(setup):
    r, _ = setup(override={"cpt": ["33207"]})
    assert r.determination == "CANT_CHECK"
    assert "doesn't match this case" in r.reason and "The patient's payer:" in r.reason and "33207" in r.reason


def test_no_target_asks_which_section(setup):
    r, stub = setup(order={"target": None})
    assert r.determination == "INSUFFICIENT" and r.queue == "review"
    assert "which of these" in r.ask and "Great or Small Saphenous Veins" in r.ask
    assert "criteria_guideline" not in stub.calls


def test_override_target_rechecks(setup, monkeypatch, fl_spans, delgado_spans):
    setup(order={"target": None})
    stub = Stub(fl_spans, delgado_spans, order={"target": None})
    monkeypatch.setattr(llm, "call", stub)
    r = pipeline.recheck("delgado", {"target": "left great saphenous vein"})
    assert r.determination == "MET"
    assert "detect_order" not in stub.calls


# ---------------------------------------------------------------- the checks, directly


def test_narrow_check_catches(fl_spans):
    c = narrow.COut.model_validate(narrow_answer(fl_spans, {"target": "great saphenous vein", "cpt": ["36475"]}))
    assert narrow.check(c, fl_spans) == []
    bad = c.model_copy(deep=True)
    bad.codes[0].refs = [fl_spans[0].id]
    bad.chosen.pathway_ids = ["nope"]
    bad.pathways[2].spans[0].first = f"{bad.pathways[2].spans[0].first}-{bad.pathways[2].spans[0].last}"
    bad.pathways[3].spans = []
    p = " | ".join(narrow.check(bad, fl_spans))
    assert "does not appear in its cited span" in p and "nope" in p and "single span ids" in p and "no spans" in p


def test_pathway_with_several_ranges(fl_spans):
    d = narrow_answer(fl_spans, {"target": "perforator veins", "cpt": ["37761"]})
    perf = d["pathways"][3]
    extra = {"first": sid(fl_spans, "Telangiectasia"), "last": sid(fl_spans, "Telangiectasia")}
    perf["spans"] = perf["spans"] + [extra]
    c = narrow.COut.model_validate(d)
    assert narrow.check(c, fl_spans) == []
    n = narrow.resolve(c, fl_spans, "g", "s", "k", [])
    sel = select(n, Order(procedure=Procedure(cpt=["37761"], target="perforator veins")), fl_spans)
    assert [p.pathway for p in sel.pathways] == ["perforator"]
    assert sel.ranges[-1].first == extra["first"] and len(sel.ranges) == 2


def test_criteria_quote_found_anywhere_and_refs_corrected(fl_spans):
    h = criteria.HOut.model_validate(criteria_answer(fl_spans))
    h.criteria[0].refs = [fl_spans[0].id]                        # wrong line: code finds where it is printed
    problems, crit, exprs = criteria.check(h, fl_spans, ["gsv"])
    assert problems == [] and len(exprs) == 1
    reflux = next(c for c in crit if c.id == "reflux")
    assert reflux.quote == "There is demonstrated saphenous reflux" and reflux.refs != [fl_spans[0].id]
    h.criteria[0].quote = "There is clearly demonstrated saphenous reflux"
    assert any("not printed in the document" in x for x in criteria.check(h, fl_spans, ["gsv"])[0])


def test_logic_string_parses_and_bad_logic_is_a_problem(fl_spans):
    h = criteria.HOut.model_validate(criteria_answer(fl_spans))
    _, _, exprs = criteria.check(h, fl_spans, ["gsv"])
    assert exprs[0].expr == {"all": ["reflux", "ceap", "size", {"any": ["ulcer", "thromb", "hem",
                                                                         {"all": ["symptoms", "adl", "compression"]}]}]}
    h.logic[0].logic = "reflux AND (ceap OR"
    assert any("logic for gsv" in x for x in criteria.check(h, fl_spans, ["gsv"])[0])
    h.logic[0].logic = "reflux AND nope"
    assert any("unknown criterion 'nope'" in x for x in criteria.check(h, fl_spans, ["gsv"])[0])


def test_audit_only_tightens(setup):
    dvt = {"id": "dvt", "quote": "deep venous thrombosis", "refs": [], "question": "DVT?"}
    r, stub = setup(audit={"loopholes": ["a DVT patient passes"], "criteria": [dvt],
                           "logic": [{"pathway": "gsv", "logic": "reflux AND NOT dvt"}]},
                    verdicts={"dvt": {"status": "NOT_MET", "against": []}})
    assert "criteria_audit" in stub.calls
    _, cs = store.load_criteria(next(p.stem for p in store.CRITERIA.glob("*.json")))
    e = cs.expressions[0].expr
    from app.decide.evaluate import leaf_ids
    assert {"dvt", "ceap", "size", "compression"} <= set(leaf_ids(e))      # dropped ids put back
    assert cs.loopholes == ["a DVT patient passes"] and any("put back" in x for x in cs.problems)


def test_select_mapped_code(fl_spans):
    d = narrow_answer(fl_spans, {"target": "great saphenous vein"})
    row = next(x for x in d["codes"] if x["code"] == "36478")
    d["chosen"]["mapped_cpt"] = {"code": "36478", "refs": row["refs"]}
    n = narrow.resolve(narrow.COut.model_validate(d), fl_spans, "g", "s", "k", [])
    sel = select(n, Order(procedure=Procedure(cpt=[], as_written="laser ablation", target="great saphenous vein")), fl_spans)
    assert [g.code for g in sel.code_gate] == ["36478"] and sel.code_gate[0].mapped
    assert any("Confirm the code" in x for x in sel.reasons)
    assert [p.pathway for p in sel.pathways] == ["gsv"]


def test_select_no_pathways(fl_spans):
    d = narrow_answer(fl_spans, {})
    d["pathways"], d["no_pathways_reason"] = [], [sid(fl_spans, "Telangiectasia")]
    n = narrow.resolve(narrow.COut.model_validate(d), fl_spans, "g", "s", "k", [])
    sel = select(n, Order(procedure=Procedure(cpt=["36475"])), fl_spans)
    assert not sel.applies and "Telangiectasia" in sel.reason


def test_age_is_not_a_duration():
    c = Criterion(id="age_18", refs=["g1"], question="Is the patient 18 years of age or older?",
                  threshold=Threshold(op="gte", value=18, unit="years"))
    assert not judge.is_duration(c.threshold, c)
    c2 = Criterion(id="trial", refs=["g1"], question="Tried for 6 weeks?", threshold=Threshold(op="gte", value=6, unit="weeks"))
    assert judge.is_duration(c2.threshold, c2) and abs(judge.required_months(c2.threshold) - 6 * 12 / 52) < 1e-9


def test_cache_key_drops_side():
    a = keys.cache_key("x" * 64, Procedure(cpt=["36475"], target="Left great saphenous vein"))
    b = keys.cache_key("x" * 64, Procedure(cpt=["36475"], target="right great saphenous vein"))
    assert a == b


def test_wipe_keeps_guidelines(setup):
    setup()
    c = store.wipe(everything=True)
    assert c["charts"] == 1 and store.guideline_exists("bcbsfl-02-33000-31")


def test_model_cannot_supply_parsed_dates(setup):
    s = sid_(0, "Begin conservative management")
    r, _ = setup(verdicts={"compression": {"status": "MET", "for": [s], "dates": [{"span": s, "date": "2025", "iso": "2025"}]}})
    comp = next(c for c in r.checklist if c.criterion == "compression")
    assert all(q.date is None or len(q.date) == 10 for q in comp.quotes)
    assert any("not written near the cited note" in x for x in r.review_reasons)


def test_date_in_signature_below_and_other_format_verifies():
    sp = [Span(id="r1", text="30-Day Holter Monitor Report"), Span(id="r2", text="Longest pause 3.1 sec."),
          Span(id="r3", text="Electronically signed: Dr. Tran — 11/11/2025")]
    cs = CriteriaSet(key="k", criteria=[Criterion(id="c", refs=[], question="q")])
    from app.core.models import DateRef
    vs = {"c": Verdict(criterion="c", status="MET", confidence=0.9, **{"for": ["r2"]},
                       dates=[DateRef(span="r2", date="November 11, 2025")])}
    reasons = judge.verify(vs, sp, cs, ["c"], [])
    assert vs["c"].dates[0].iso == "2025-11-11" and not reasons.get("c")


def test_date_lookback_reaches_a_heading_many_lines_up():
    from app.core.models import DateRef
    sp = [Span(id="r0001", text="Visit Date: October 8, 2025 | Attending: Dr. Tran")]
    sp += [Span(id=f"r{n:04d}", text=f"line {n}") for n in range(2, 62)]
    sp += [Span(id="r0062", text="  Bradycardia noted, HR 44 bpm."), Span(id="r0063", text="  Asymptomatic.")]
    cs = CriteriaSet(key="k", criteria=[Criterion(id="c", refs=[], question="q")])
    vs = {"c": Verdict(criterion="c", status="MET", confidence=0.9, **{"for": ["r0062-r0063"]},
                       dates=[DateRef(span="r0062-r0063", date="October 8, 2025")])}
    assert judge.DATE_LOOKBACK >= 61
    reasons = judge.verify(vs, sp, cs, ["c"], [])
    assert vs["c"].dates[0].iso == "2025-10-08" and not reasons.get("c")


def test_criterion_quotes_are_shown(setup):
    r, _ = setup()
    assert any(i.text == "the symptoms significantly interfere with activities of daily living" for i in r.checklist)


def test_locate_forgives_only_whitespace_and_broken_hyphens():
    from app.ingest.spans import locate
    assert locate("activities of daily living", "interfere with activities  of daily living, AND") == "activities  of daily living"
    assert locate("interfere with", "inter- fere with") == "interfere with"
    assert locate("at least 3 months", "at least three months") is None


def test_unverified_date_flags_only_durations(setup):
    s = sid_(0, "Unchanged varicosities")
    r, _ = setup(verdicts={"size": {"status": "MET", "for": [s], "dates": [{"span": s, "date": "January 1, 2020"}]}})
    assert r.queue == "ready"
    size = next(c for c in r.checklist if c.criterion == "size")
    assert all(q.date != "2020-01-01" for q in size.quotes)


def test_code_modifiers_are_dropped():
    assert [pipeline.base_code(x) for x in ["36475-LT", "36475 RT", "36475-50", " 0524T ", "G0277-59", "36475"]] == \
        ["36475", "36475", "36475", "0524T", "G0277", "36475"]
    o = pipeline.apply_override(Order(procedure=Procedure(cpt=["36475"])), {"cpt": ["36475-LT", "36475-RT"]})
    assert o.procedure.cpt == ["36475"]


def test_pathway_label_skips_a_bare_section_heading(fl_spans):
    from app.understand.select import pathway_name
    d = narrow_answer(fl_spans, {})
    pos = sid(fl_spans, "POSITION STATEMENT")
    d["pathways"][0]["spans"][0]["first"] = pos                    # a range that starts at the section heading
    n = narrow.resolve(narrow.COut.model_validate(d), fl_spans, "g", "s", "k", [])
    assert pathway_name(n, "gsv", fl_spans).startswith("Great or Small Saphenous Veins")


def test_judge_cannot_cite_a_summary_or_the_order(setup, delgado_spans):
    from tests.conftest import idx
    plan = idx(delgado_spans, sid(delgado_spans, "PLANNED PROCEDURE"))
    cite = delgado_spans[plan + 1].id                                      # a line inside the planned-procedure block
    r, stub = setup(verdicts={"ceap": {"status": "MET", "for": [cite]}})
    assert r.queue != "ready"
    assert any("could not be found in the case" in x for x in r.review_reasons)


def test_sections_label_and_cache(tmp_store, delgado_spans, monkeypatch):
    from app.ingest import sections
    from tests.fake import sections_answer
    out = sections.SOut.model_validate(sections_answer(delgado_spans))
    assert sections.check(out, delgado_spans) == []
    ev = sections.evidence(out, delgado_spans)
    assert ev and all("PLANNED PROCEDURE" not in s.text for s in ev)
    # a summary inside an evidence range stays hidden
    over = out.model_copy(deep=True)
    over.sections.append(sections.Section(title="sum", label="summary", spans=[{"first": ev[3].id, "last": ev[3].id}]))
    assert ev[3].id not in {s.id for s in sections.evidence(over, delgado_spans)}
    calls = []
    monkeypatch.setattr(sections, "split", lambda sp, rid: calls.append(1) or out)
    pipeline.evidence_for("c1", delgado_spans, "r")
    pipeline.evidence_for("c1", delgado_spans, "r")
    assert calls == [1]
