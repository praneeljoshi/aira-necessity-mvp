"""Step I (model, whole chart, one call) and step J (code: verify).

I   in:  r-spans; Criterion[] (answerable only) {id, resolved text, threshold, question}; the order line
    out: Verdict[] {criterion, status, confidence, rationale, for[], against[], measurements[], dates[]}

J   citations (ids or line ranges) resolve · a date for a span not cited in for / against is dropped · each date string appears in its cited lines, the note's dated heading
    line above them (within 80 lines) or the note's signature line below (note_date_lines) · each measurement value appears in its cited lines · durations from verified
    dates only · MET with against -> review · NOT_MET with no against -> INSUFFICIENT · measurements on both sides
    of a threshold -> review · anything unverified -> review, never dropped
"""
from __future__ import annotations

import json
import os
import re
from typing import Optional

from pydantic import BaseModel, Field

from . import hints, llm, log
from .models import CriteriaSet, Criterion, DateRef, Measurement, Order, Span, Threshold, Verdict
from .refs import find_dates, months_between, number_in, to_float
from .spans import expand, render_chart, resolves, table, text_of, wording

logger = log.get("judge")

# A date is verified when it is written in the cited lines, in a line up to this far above them (the note heading
# with the visit date), or in the note's own signature line below. Spans are lines now, and a note between its
# heading and its signature runs 25-30 lines in the sample charts, more when it holds tables; 80 lines is about one
# page of `pdftotext -layout` output, so the heading of any note on the same or the previous page is reached.
DATE_LOOKBACK = 80
EFFORT = os.environ.get("EFFORT_JUDGE", "low")         # the judge call's reasoning effort
TIME_UNITS = {"month": 1.0, "months": 1.0, "mo": 1.0, "week": 12 / 52, "weeks": 12 / 52, "day": 12 / 365,
              "days": 12 / 365, "year": 12.0, "years": 12.0}


# Lines a date is never taken from: the request's own status, submission, authorization or scheduling lines ("PA
# Status  Pending — Submitted July 24, 2025") are dates of the paperwork, not of a note.
_STATUS = re.compile(r"\bPA\s+status\b|\bsubmitted\b|\bauth(?:orization|orized)?\b|\bscheduled\b|"
                     r"\bdate\s+of\s+service\s+requested\b", re.I)
_SIGNED = re.compile(r"\bsigned\b", re.I)
_SECTION = re.compile(r"^\d+\.\s+[A-Z][A-Z &/—–-]{3,}$")   # a numbered chart section: "8. PLANNED PROCEDURE",
                                                             # "6. VISIT NOTES — CARDIOLOGY"
NOT_A_NOTE = {"order", "summary", "admin"}                    # A2 labels whose lines never date a note
# A labelled note date, anywhere on its line: "Visit Date: October 8, 2025 | Attending: …", "Facility: …  Date
# Performed: November 5, 2025". "Date of service requested" (the request's own line) has no colon after the label and
# is a status line besides.
_DATE_LABEL = re.compile(r"\b(?:visit\s+date|date\s+performed|date\s+of\s+(?:visit|service|exam|study|procedure|report)"
                         r"|(?:exam|study|report|encounter|note)\s+date)\s*:", re.I)


def _dated_heading(rspans: list[Span], j: int) -> bool:
    """A visit / report heading that carries a date: a line with a date that opens a block (a blank line before it,
    the first line on its page, right under a numbered chart section) or carries a date label ("Visit Date: …",
    "Date Performed: …")."""
    s = rspans[j]
    t = s.text.strip()
    if not find_dates(t) or t.startswith(("•", "-", "–", "▪")):
        return False
    lab = _DATE_LABEL.search(t)
    return (s.blank_before or bool(lab and find_dates(t[lab.end():])) or j == 0 or rspans[j - 1].page != s.page
            or bool(_SECTION.match(rspans[j - 1].text.strip())))


def _note_ends(rspans: list[Span], a: int, b: int, labels: Optional[dict[str, str]] = None
               ) -> tuple[Optional[Span], Optional[Span]]:
    """(the note's dated heading above rspans[a..b], its signature line below); see note_date_lines."""
    labels = labels or {}
    skip = lambda x: _STATUS.search(x.text) or labels.get(x.id) in NOT_A_NOTE
    head = sig = None
    for j in range(a - 1, max(-1, a - DATE_LOOKBACK - 1), -1):
        x = rspans[j]
        if skip(x):
            continue
        if _SIGNED.search(x.text) or _SECTION.match(x.text.strip()):
            break
        if _dated_heading(rspans, j):
            head = x
            break
    for j in range(b + 1, min(len(rspans), b + DATE_LOOKBACK + 1)):
        x = rspans[j]
        if skip(x):
            continue
        if _SIGNED.search(x.text):
            sig = x
            break
        if _SECTION.match(x.text.strip()) or _dated_heading(rspans, j):
            break
    return head, sig


def note_date_lines(rspans: list[Span], a: int, b: int, labels: Optional[dict[str, str]] = None) -> list[str]:
    """The texts a date for the cited lines rspans[a..b] may be read from, besides the cited lines themselves: the
    note's heading line (the nearest dated visit / report heading above, within DATE_LOOKBACK, not past the previous
    note's signature or a numbered chart section) and the note's signature line below ("Electronically signed …",
    not past the next note's heading). Status / submission / authorization / scheduling lines and lines A2 labelled
    order / summary / admin (`labels`, when known) are never read."""
    return [x.text for x in _note_ends(rspans, a, b, labels) if x is not None]


def _cited(span: str, v: Verdict, tbl: dict[str, Span]) -> bool:
    """A date's span is one of the verdict's for / against citations, or lines inside one of them."""
    if not resolves(span, tbl):
        return False
    mine = set(expand([span], tbl))
    return any(mine <= set(expand([c], tbl)) for c in v.for_ + v.against if resolves(c, tbl))


def quote_date(v: Optional[Verdict], cite: str, tbl: dict[str, Span]) -> Optional[str]:
    """The verified date (ISO) of the quote `cite`: the date the judge gave for that same span, else one given for
    lines inside it or for a cited range holding it. None when no verified date belongs to it (an unverified date is
    never shown)."""
    if not v or not resolves(cite, tbl):
        return None
    ds = [d for d in v.dates if d.iso and resolves(d.span, tbl)]
    if (d := next((d for d in ds if d.span == cite), None)):
        return d.iso
    mine = set(expand([cite], tbl))
    return next((d.iso for d in ds if (o := set(expand([d.span], tbl))) <= mine or mine <= o), None)


class _D(BaseModel):
    span: str
    date: str


class _V(BaseModel):
    criterion: str
    status: str
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""
    for_: list[str] = Field(default_factory=list, alias="for")
    against: list[str] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    dates: list[_D] = Field(default_factory=list)


class IOut(BaseModel):
    verdicts: list[_V]


def order_line(o: Order) -> str:
    p = o.procedure
    bits = [x for x in [p.as_written, ("CPT " + ", ".join(p.cpt)) if p.cpt else None, p.target] if x]
    return "; ".join(bits) or "(not stated)"


def criteria_json(crit: list[Criterion], gtable: dict[str, Span]) -> str:
    return json.dumps([{"id": c.id, "text": wording(c, gtable), "question": c.question,
                        "threshold": c.threshold.model_dump(exclude_none=True) if c.threshold else None}
                       for c in crit], indent=1)


def judge(rspans: list[Span], cs: CriteriaSet, ids: list[str], gspans: list[Span], order: Order,
          run_id: str, hint: Optional[str] = None) -> dict[str, Verdict]:
    """`hint`: the clinic structure hint (app/hints.py) read from the whole chart; None: looked up from `rspans`."""
    crit = cs.criterion_map()
    asked = [crit[i] for i in ids if i in crit]
    logger.info("judge: %d criteria over %d spans", len(asked), len(rspans))
    if hint is None:
        hint = hints.clinic_hint(rspans)[1]
    out = llm.call(run_id, "judge_chart",
                   hints.for_chart(llm.prompt("judge_chart", order_line=order_line(order),
                                              criteria_json=criteria_json(asked, table(gspans)),
                                              chart_spans=render_chart(rspans)), hint),
                   IOut, model=llm.pick_models()[1], reasoning_effort=EFFORT)
    return to_verdicts(out.verdicts, crit)


def to_verdicts(out: list[_V], crit: dict[str, Criterion]) -> dict[str, Verdict]:
    """The model's verdicts for known criteria only, the first per id, statuses outside the three dropped. Shared
    with the highlight-to-ask call (app/ask.py), which writes verdicts the same way."""
    verdicts: dict[str, Verdict] = {}
    for v in out:
        if v.criterion in crit and v.criterion not in verdicts and v.status in ("MET", "NOT_MET", "INSUFFICIENT"):
            verdicts[v.criterion] = Verdict(criterion=v.criterion, status=v.status, confidence=v.confidence,
                                            rationale=v.rationale, **{"for": v.for_}, against=v.against,
                                            measurements=v.measurements,
                                            dates=[DateRef(span=d.span, date=d.date) for d in v.dates])
    return verdicts


# ---------------------------------------------------------------- J


def is_duration(t: Optional[Threshold], c: Criterion) -> bool:
    if not t or t.op not in ("gte", "gt"):
        return False
    unit = re.sub(r"^(consecutive|continuous|calendar)\s+", "", (t.unit or "").strip().lower())
    if unit not in TIME_UNITS:
        return False
    return not re.search(r"\bage\b|\bold\b|\byears? of age\b", (c.question + " " + c.id).lower().replace("_", " "))


def required_months(t: Threshold) -> Optional[float]:
    v = to_float(t.value)
    unit = re.sub(r"^(consecutive|continuous|calendar)\s+", "", (t.unit or "").strip().lower())
    return None if v is None else v * TIME_UNITS[unit]


def _satisfies(x: float, t: Threshold) -> Optional[bool]:
    v = to_float(t.value)
    if v is None:
        return None
    return {"gte": x >= v, "gt": x > v, "lte": x <= v, "lt": x < v, "eq": x == v}[t.op]


def verify(verdicts: dict[str, Verdict], rspans: list[Span], cs: CriteriaSet, ids: list[str],
           gspans: list[Span], labels: Optional[dict[str, str]] = None) -> dict[str, list[str]]:
    """Mutates verdicts (status fixes, verified dates, durations). Returns review reasons per criterion, in plain
    words. A criterion the judge skipped becomes INSUFFICIENT with a reason. `labels`: A2's line labels for the
    chart (sections.labels), when known; lines labelled order / summary / admin never date a note."""
    tbl = table(rspans)
    pos = {s.id: i for i, s in enumerate(rspans)}
    crit = cs.criterion_map()
    gt = table(gspans)
    reasons: dict[str, list[str]] = {}
    for cid in ids:
        c = crit.get(cid)
        if c is None:
            continue
        say = lambda msg: reasons.setdefault(cid, []).append(msg)
        req = wording(c, gt).rstrip(".")[:160]
        v = verdicts.get(cid)
        if v is None:
            verdicts[cid] = Verdict(criterion=cid, status="INSUFFICIENT", confidence=0.0,
                                    rationale="The check returned nothing for this requirement.")
            say(f"“{req}” was not assessed; check it by hand.")
            continue
        bad = [r for r in v.for_ + v.against if not resolves(r, tbl)]
        if bad:
            say(f"A note cited for “{req}” could not be found in the case; read that part yourself.")
            v.for_ = [r for r in v.for_ if resolves(r, tbl)]
            v.against = [r for r in v.against if resolves(r, tbl)]
        if v.status == "MET" and not v.for_:
            say(f"“{req}” was marked documented without a quoted note; read the case yourself.")
        if v.status == "MET" and v.against:
            say(f"The case has notes for and against “{req}”; read both before submitting.")
        if v.status == "NOT_MET" and not v.against:
            v.status = "INSUFFICIENT"
            v.rationale = (v.rationale + " (No note was cited that contradicts it, so it is treated as not documented.)").strip()
        # dates: the parsed date must be written in the cited line(s) (a status / submission line excepted), in the
        # note's dated heading above them, or in the note's own signature line below ("Electronically signed ...
        # November 11, 2025"); never in the request's status lines or the order / summary / admin block
        # a date tied to a span the verdict does not cite is dropped (never attached to another quote)
        v.dates = [d for d in v.dates if _cited(d.span, v, tbl)]
        for d in v.dates:
            d.iso = None
            parsed = find_dates(d.date)
            ids_ = expand([d.span], tbl)
            ok = False
            if parsed:
                a, b = pos[ids_[0]], pos[ids_[-1]]
                texts = [" ".join(tbl[i].text.strip() for i in ids_ if not _STATUS.search(tbl[i].text))]
                texts += note_date_lines(rspans, a, b, labels)
                ok = any(parsed[0] in find_dates(t) for t in texts)
            if ok:
                d.iso = parsed[0]
            elif is_duration(c.threshold, c):
                # a date only decides something for a duration; elsewhere an unverified date is kept unverified (no
                # iso, never shown) and does not send the order to review
                say(f"A date given for “{req}” ({d.date}) is not written near the cited note; check the dates by hand.")
        # measurements: the value is written in the cited line(s)
        vals: list[float] = []
        for m in v.measurements:
            s = text_of([m.span], tbl) if resolves(m.span, tbl) else ""
            if not s or not number_in(s, m.value):
                say(f"A measurement for “{req}” ({m.value} {m.unit or ''}".rstrip() + ") is not in the cited note; check it by hand.")
            elif (x := to_float(m.value)) is not None:
                vals.append(x)
        t = c.threshold
        if t and vals and not is_duration(t, c):
            sides = {_satisfies(x, t) for x in vals} - {None}
            if len(sides) == 2:
                say(f"The case has measurements on both sides of “{req}”; confirm which applies to the planned procedure.")
        # durations
        if is_duration(t, c) and v.status == "MET":
            isos = sorted(d.iso for d in v.dates if d.iso)
            need = required_months(t)
            if len(set(isos)) >= 2:
                v.duration_months = round(months_between(isos[0], isos[-1]), 1)
                if need is not None and v.duration_months < need:
                    v.confidence = min(v.confidence, 0.5)
                    say(f"The dated notes for “{req}” span {v.duration_months:g} months ({isos[0]} to {isos[-1]}), "
                        f"less than the {need:g} required; check the dates by hand.")
            else:
                say(f"“{req}” needs a dated start note and a dated latest note; check the dates by hand.")
    return reasons
