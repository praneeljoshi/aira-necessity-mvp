"""A quote's date comes from the note, never from the request's paperwork (judge.verify, judge.note_date_lines).
Delgado's compression summary "… from 03/18/2025 through 07/22/2025 …" sits under "PA Status  Pending — Submitted
July 24, 2025" in the planned-procedure block; within DATE_LOOKBACK of it, that submission date used to verify, so the
quote read July 24, 2025. Pure: the sample chart's lines, the stub's checklist, no store."""
from __future__ import annotations

from app import judge, sections, tree
from app.models import CriteriaSet, Criterion, DateRef, Threshold, Verdict
from app.spans import table
from tests.conftest import rng, sid
from tests.fake import sections_answer


def _case(r, dates: list[str]):
    q = rng(r, "Conservative management with 20", "07/22/2025 (4 months)")
    c = Criterion(id="compression", refs=["g0001"], quote="compression", answerable=True,
                  threshold=Threshold(op="gte", value=3, unit="months"), question="Compression >= 3 months?")
    cs = CriteriaSet(key="k", criteria=[c], expressions=[])
    v = Verdict(criterion="compression", status="MET", confidence=0.9, **{"for": [q]},
                dates=[DateRef(span=q, date=d) for d in dates])
    return q, cs, {"compression": v}


def test_the_submission_date_never_dates_the_compression_quote(delgado_spans, fl_spans):
    r = delgado_spans
    q, cs, vs = _case(r, ["July 24, 2025"])
    pos = {s.id: i for i, s in enumerate(r)}
    status_line = sid(r, "PA Status")
    a = pos[q.split("-")[0]]
    assert 0 < a - pos[status_line] <= judge.DATE_LOOKBACK      # the old reach took it: the mis-date
    labels = sections.labels(sections.SOut.model_validate(sections_answer(r)), r)
    for lab in (None, labels):                                    # by its words alone, and by A2's order label
        q, cs, vs = _case(r, ["July 24, 2025"])
        reasons = judge.verify(vs, r, cs, ["compression"], fl_spans, lab)
        assert vs["compression"].dates[0].iso is None
        assert any("July 24, 2025" in x for x in reasons["compression"])
        assert vs["compression"].duration_months is None


def test_the_compression_quote_is_dated_by_its_own_lines(delgado_spans, fl_spans):
    r = delgado_spans
    labels = sections.labels(sections.SOut.model_validate(sections_answer(r)), r)
    q, cs, vs = _case(r, ["03/18/2025", "July 22, 2025"])
    reasons = judge.verify(vs, r, cs, ["compression"], fl_spans, labels)
    v = vs["compression"]
    assert [d.iso for d in v.dates] == ["2025-03-18", "2025-07-22"] and not reasons
    assert v.duration_months == 4.1
    shown = tree.quotes_of(v, r, table(r))
    assert shown[0]["date"] == "2025-03-18"


def test_a_visit_note_is_dated_by_its_heading_or_signature_not_the_next_note(delgado_spans, fl_spans):
    """The July follow-up's lines take the July 22 heading; a March date given for them is not taken from the March
    note above (that note ended at its signature)."""
    r = delgado_spans
    cont = rng(r, "Reports consistent daily use", "stockings since the March visit")
    pos = {s.id: i for i, s in enumerate(r)}
    a, b = pos[cont.split("-")[0]], pos[cont.split("-")[1]]
    got = judge.note_date_lines(r, a, b)
    assert any("Visit Date: July 22, 2025" in t for t in got) and any("signed" in t and "July 22, 2025" in t for t in got)
    assert not any("March 18, 2025" in t for t in got)
    reflux = rng(r, "Reflux at saphenofemoral junction 2.4", "reflux along thigh and calf")
    a, b = pos[reflux.split("-")[0]], pos[reflux.split("-")[1]]
    assert any("March 25, 2025" in t for t in judge.note_date_lines(r, a, b))
