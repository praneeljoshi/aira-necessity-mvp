"""v1.1 data model. Every field is read by code or shown on screen; nothing else is stored.

    Span        one line of the extracted text, verbatim: g-spans (guideline) and r-spans (chart record)
    guideline   Guideline · Code · Pathway        (step C, narrowed by the order, cached by sha256 + cpt + target)
                Criterion · Expression            (step H, over the chosen ranges only, same cache key)
    order       Order · Procedure                 (step B)
    per order   Selection                         (steps E, F, G: code)
                Verdict                           (step I model, step J code)
                Result                            (steps K, L: code)

The model cites spans; code resolves every string a person reads from the span table. Every `refs`, `for`,
`against`, `span` or `spans` field the model fills holds citations: a span id ("g0031") or a range of lines
("g0031-g0033") where the text wraps. `spans.expand` turns citations into ids; code expands before every check.
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------- spans


class Span(BaseModel):
    id: str
    text: str                               # the line as extracted: leading whitespace kept, trailing stripped
    page: int = 1                           # PDF page the line is on; the renderer marks where a page starts
    blank_before: bool = False              # blank line(s) came before it; the renderer shows one empty line


class Range(BaseModel):
    first: str
    last: str


# ---------------------------------------------------------------- guideline (one PDF, reused)


class Payer(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)


class Guideline(BaseModel):
    id: str
    sha256: str
    payer: Payer
    no_pathways_reason: Optional[list[str]] = None   # citations: why the document grants nothing of its own
    refs: list[str] = Field(default_factory=list)    # citations: where the payer is named
    always_on: list[Range] = Field(default_factory=list)   # v1.1 only (lines that join every pathway); empty since v1.2


CodeTag = Literal["covered", "non_covered", "investigational", "not_addressed"]


class Code(BaseModel):
    code: str
    tag: CodeTag
    description: str = ""                  # resolved by code: the text of the table row it was read from
    refs: list[str] = Field(default_factory=list)    # citations: the row (a line or a range of lines)


class Pathway(BaseModel):
    """One route to approval: every line of the guideline that bears on it, as one or more ranges in document order.
    Labelled on screen by the first line of its first range."""
    id: str
    spans: list[Range]
    codes: list[str] = Field(default_factory=list)    # codes it governs; [] = decided by name
    targets: list[str] = Field(default_factory=list)  # what it is about: vein, indication, population, phase


class Threshold(BaseModel):
    op: Literal["gte", "gt", "lte", "lt", "eq"]
    value: Any
    unit: Optional[str] = None


class Criterion(BaseModel):
    id: str
    refs: list[str]                        # citations: the lines the requirement is printed on
    quote: Optional[str] = None            # the requirement's own words, resolved by code from inside text_of(refs)
    threshold: Optional[Threshold] = None
    answerable: bool = True
    question: str
    admin: bool = False                    # step H: not a condition about the patient; pruned per case (app/admin.py)
    admin_why: Optional[str] = None        # "billing or coding" | "paperwork" | "heading or definition" | "procedure wording"


class Expression(BaseModel):
    pathway: str
    expr: Any                              # "id" | {"all": [...]} | {"any": [...]} | {"not": e} | {"at_least": {"k", "of"}}


class Narrowed(BaseModel):
    """Step C for one (guideline, cpt[], target): the guideline's header, its code table, every pathway, and the
    ones this order falls under."""

    key: str
    guideline: Guideline
    codes: list[Code] = Field(default_factory=list)
    pathways: list[Pathway] = Field(default_factory=list)
    chosen: list[str] = Field(default_factory=list)          # pathway ids
    mapped_cpt: Optional[Code] = None                        # a table code mapped from as_written
    why_refs: list[str] = Field(default_factory=list)
    problems: list[str] = Field(default_factory=list)        # code checks still failing after one retry
    run_id: Optional[str] = None


class NotUsed(BaseModel):
    """v1.1 only: lines step H set aside; empty since v1.2 (the UI's ask still reads it)."""
    spans: list[str] = Field(default_factory=list)
    why: str = ""


class CriteriaSet(BaseModel):
    """Step H for one (guideline, cpt[], target) and its confirmed pathway(s)."""

    key: str
    criteria: list[Criterion] = Field(default_factory=list)
    expressions: list[Expression] = Field(default_factory=list)
    notes: str = ""                                       # the model's own reading, for the audit trail
    loopholes: list[str] = Field(default_factory=list)     # what the audit found and closed
    removed_conditions: list[dict] = Field(default_factory=list)  # STEP_H=tools/script: {id, quote, why}, for review
    script: Optional[str] = None                          # STEP_H=script: the final tree script, for review
    loop: Optional[dict] = None
    not_used: list[NotUsed] = Field(default_factory=list)   # v1.1 only; empty since v1.2                           # STEP_H=loose-loop: rounds, converged, reason, counts, added, removed
    status: Literal["ok", "needs_review"] = "ok"
    problems: list[str] = Field(default_factory=list)
    run_id: Optional[str] = None

    def criterion_map(self) -> dict[str, Criterion]:
        return {c.id: c for c in self.criteria}


# ---------------------------------------------------------------- order (one request)


class Procedure(BaseModel):
    cpt: list[str] = Field(default_factory=list)
    as_written: Optional[str] = None       # the procedure as the chart words it
    target: Optional[str] = None           # what it treats: vein and side, indication, joint
    surgeon: Optional[str] = None
    diagnosis: Optional[str] = None        # the clinic's stated indication with ICD-10 codes, as written (a claim, not evidence)
    plan: Optional[str] = None             # the member's plan / line of business (from coverage, not the chart); step H prunes plan-only conditions on it


class Order(BaseModel):
    id: str = ""
    patient_name: Optional[str] = None
    payer: Optional[str] = None
    chart_id: str = ""
    procedure: Procedure = Field(default_factory=Procedure)
    refs: list[str] = Field(default_factory=list)    # citations: the r-spans the order was read from


# ---------------------------------------------------------------- produced per order


Gate = Literal["judge", "not_covered", "cant_check"]


class CodeGate(BaseModel):
    code: str
    tag: Optional[CodeTag] = None
    outcome: Gate
    mapped: bool = False                   # the code was mapped from the procedure name, not written in the chart


class Pick(BaseModel):
    code: str
    pathway: str
    how: Literal["code", "name", "person"]  # the pathway lists the code, names no codes and was chosen by name, or a person confirmed it


class Selection(BaseModel):
    applies: bool
    reason: str = ""
    code_gate: list[CodeGate] = Field(default_factory=list)
    pathways: list[Pick] = Field(default_factory=list)
    ranges: list[Range] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)       # review reasons raised before judging
    candidates: dict[str, list[str]] = Field(default_factory=dict)  # code -> pathway ids, when none was chosen


VerdictStatus = Literal["MET", "NOT_MET", "INSUFFICIENT"]


class Measurement(BaseModel):
    value: str
    unit: Optional[str] = None
    span: str                              # citation: the line holding the number (a range when it wraps)


class DateRef(BaseModel):
    span: str                              # citation: the evidence line(s)
    date: str                              # as written in the chart, in that span, a heading above or a signature below
    iso: Optional[str] = None              # code: parsed, only when verified


class Verdict(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    criterion: str
    status: VerdictStatus
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""
    for_: list[str] = Field(default_factory=list, alias="for")   # citations; a range is quoted as one sentence
    against: list[str] = Field(default_factory=list)
    measurements: list[Measurement] = Field(default_factory=list)
    dates: list[DateRef] = Field(default_factory=list)
    duration_months: Optional[float] = None  # code, from verified dates


# ---------------------------------------------------------------- the tree, evaluated (code)


class NodeResult(BaseModel):
    type: str
    status: VerdictStatus
    criterion: Optional[str] = None
    k: Optional[int] = None
    confidence: float = 1.0
    children: list["NodeResult"] = Field(default_factory=list)


Determination = Literal["MET", "NOT_MET", "INSUFFICIENT", "NOT_COVERED", "CANT_CHECK"]
Queue = Literal["ready", "review", "cant_check"]


class Miss(BaseModel):
    criterion: str
    ask: str                               # one line of the message to the surgeon


class Quote(BaseModel):
    span: str                              # the citation as the judge gave it (an id or a range)
    text: str                              # resolved by code from the span table: the cited lines joined
    date: Optional[str] = None             # ISO, verified


class PacketItem(BaseModel):
    criterion: str
    text: str                              # the guideline's words
    quotes: list[Quote] = Field(default_factory=list)


class CheckItem(BaseModel):
    criterion: str
    text: str                              # the guideline's words
    status: VerdictStatus
    quotes: list[Quote] = Field(default_factory=list)


class Result(BaseModel):
    order_id: str
    guideline_id: str
    determination: Determination
    reason: str = ""                       # the one sentence on screen
    pathway_used: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    queue: Queue = "review"
    review_reasons: list[str] = Field(default_factory=list)
    # the review reasons that only ask a person to confirm, outside the chart, a requirement no chart can show; in the
    # review flow a person's "Confirmed outside the chart" closes them (signoff.ready)
    confirm_reasons: list[str] = Field(default_factory=list)
    misses: list[Miss] = Field(default_factory=list)
    packet: list[PacketItem] = Field(default_factory=list)
    ask: str = ""
    checklist: list[CheckItem] = Field(default_factory=list)
    run_id: Optional[str] = None


NodeResult.model_rebuild()
