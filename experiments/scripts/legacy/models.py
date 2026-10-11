"""Data model.

Guideline -> criteria (leaf questions, each with the guideline's own wording) + scenarios
             (coverage pathways, each a logical expression over criteria)
Verdict   -> per-criterion judgment from one judge call over the whole chart. The model cites
             span ids (refs); code resolves them to Sources (exact chart text, heading, date).
             The packet and the duration cross-check read Sources, never model text.
Result    -> the expression compiled over verdicts, plus misses                     (code)
"""
from __future__ import annotations

from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- guideline


class Criterion(BaseModel):
    """One leaf requirement in the guideline's own words, plus what evidence would satisfy it."""

    id: str
    text: str                              # verbatim or near-verbatim from the guideline
    question: str                          # how a nurse would ask it of a chart
    threshold: Optional["Threshold"] = None  # present when the criterion contains a number/duration/class
    refs: list[str] = Field(default_factory=list)  # guideline span ids the wording was resolved from (g###)
    answerable: bool = True                # False: a chart cannot show it (credentials, contract); never judged


class Threshold(BaseModel):
    """A machine-checkable part of a criterion, used as a cross-check on the judge, never as the verdict."""

    kind: Literal["number", "duration_months", "enum"]
    op: Literal["gte", "lte", "gt", "lt", "eq", "gte_enum"]
    value: Any
    unit: Optional[str] = None
    enum_values: Optional[list[str]] = None  # ascending order for gte_enum


class LeafNode(BaseModel):
    type: Literal["leaf"] = "leaf"
    criterion: str  # Criterion.id


class AllNode(BaseModel):
    type: Literal["all"] = "all"
    label: str = ""
    children: list["Node"]


class AnyNode(BaseModel):
    type: Literal["any"] = "any"
    label: str = ""
    children: list["Node"]


class NotNode(BaseModel):
    type: Literal["not"] = "not"
    label: str = ""
    child: "Node"


Node = Union[AllNode, AnyNode, NotNode, LeafNode]
AllNode.model_rebuild()
AnyNode.model_rebuild()
NotNode.model_rebuild()


class Scenario(BaseModel):
    id: str
    name: str
    applies_to_cpt: list[str] = Field(default_factory=list)
    requires: Node
    notes: list[str] = Field(default_factory=list)


CptStatus = Literal["covered", "non_covered", "investigational"]


class Scope(BaseModel):
    cpt: dict[str, CptStatus] = Field(default_factory=dict)
    icd10: list[str] = Field(default_factory=list)


class Exclusion(BaseModel):
    """Something the guideline says is not covered: the guideline's own words, and the codes it names (if any)."""

    text: str
    cpt: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)


class SpanNote(BaseModel):
    """A guideline sentence the reduce step skipped (why empty) or set aside as not a requirement (why given)."""

    spans: list[str]
    text: str
    why: str = ""


class GuidelineReview(BaseModel):
    """What the ingest check found. A guideline with problems is saved with status needs_review and never judged."""

    problems: list[str] = Field(default_factory=list)
    skipped: list[SpanNote] = Field(default_factory=list)
    not_used: list[SpanNote] = Field(default_factory=list)
    no_criteria_reason: Optional[str] = None


class Guideline(BaseModel):
    id: str
    payer: str
    payer_aliases: list[str] = Field(default_factory=list)
    title: str
    guideline_number: Optional[str] = None
    effective_date: Optional[str] = None
    reviewed_date: Optional[str] = None
    source_file: Optional[str] = None
    source_sha256: Optional[str] = None     # of the uploaded PDF; the ingest cache key
    scope: Scope = Field(default_factory=Scope)
    criteria: list[Criterion]
    scenarios: list[Scenario]
    notes: list[str] = Field(default_factory=list)
    plan_types: list[str] = Field(default_factory=list)       # plans the document says it governs
    excluded_plans: list[str] = Field(default_factory=list)   # plans it says follow another policy (e.g. an NCD)
    exclusions: list[Exclusion] = Field(default_factory=list)
    status: Literal["ok", "needs_review"] = "ok"
    review: Optional[GuidelineReview] = None

    def criterion_map(self) -> dict[str, Criterion]:
        return {c.id: c for c in self.criteria}

    def leaves(self, scenario_ids: Optional[list[str]] = None) -> list[str]:
        """Criterion ids referenced by the given scenarios (default all), in order, deduped."""
        out: list[str] = []

        def walk(n: Node):
            if isinstance(n, LeafNode):
                if n.criterion not in out:
                    out.append(n.criterion)
            elif isinstance(n, NotNode):
                walk(n.child)
            else:
                for c in n.children:
                    walk(c)

        for s in self.scenarios:
            if scenario_ids is None or s.id in scenario_ids:
                walk(s.requires)
        return out


# ---------------------------------------------------------------- chart side


class Source(BaseModel):
    """One chart span a verdict rests on, resolved by code from a span id. What the packet shows."""

    span_id: str
    text: str                              # the span's exact text from the chart
    heading: str = ""                      # nearest preceding heading (note title)
    date: Optional[str] = None             # ISO date parsed from the heading/span, if any


VerdictStatus = Literal["MET", "NOT_MET", "INSUFFICIENT"]


class Verdict(BaseModel):
    """The judge's call on one criterion."""

    status: VerdictStatus
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""
    refs: list[str] = Field(default_factory=list)      # span ids from the model; for a duration, start first, latest last
    sources: list[Source] = Field(default_factory=list)  # resolved by code from refs
    quote: Optional[str] = None            # the model's own copy of the key span; used only to verify, never shown
    quote_verified: bool = False           # True only when refs resolved and quote matched a resolved span
    flags: list[str] = Field(default_factory=list)  # code-raised review flags (unverified quote, no verdict, duration)
    duration_months: Optional[float] = None  # for duration criteria: computed by code from the cited notes' dates


class Order(BaseModel):
    payer: Optional[str] = None
    plan_type: Optional[str] = None
    cpt: list[str] = Field(default_factory=list)
    icd10: list[str] = Field(default_factory=list)
    laterality: Optional[str] = None
    procedure_text: Optional[str] = None
    patient_name: Optional[str] = None
    surgeon: Optional[str] = None          # treating surgeon as written, for the ask


# ---------------------------------------------------------------- verification (does this guideline apply to this chart?)


class Verification(BaseModel):
    """One model call per check: does the chosen guideline govern this chart's coverage and procedure?"""

    applies: bool
    cpt: list[str] = Field(default_factory=list)   # codes to judge against, confirmed from the guideline's table
    confidence: float = Field(ge=0, le=1)
    reason: str = ""                       # states both sides when it does not apply


# ---------------------------------------------------------------- result


class NodeResult(BaseModel):
    type: str
    label: str = ""
    status: VerdictStatus
    criterion: Optional[str] = None
    text: Optional[str] = None
    verdict: Optional[Verdict] = None
    confidence: float = 1.0                # compiled through the tree (evaluate._confidence)
    children: list["NodeResult"] = Field(default_factory=list)


class Miss(BaseModel):
    criterion: str
    text: str
    kind: Literal["missing", "unmet"]
    detail: str


class ScenarioResult(BaseModel):
    id: str
    name: str
    status: VerdictStatus
    tree: NodeResult
    misses: list[Miss]
    confidence: float = 1.0                # the tree's compiled confidence


Determination = Literal["MET", "NOT_MET", "INSUFFICIENT", "NOT_APPLICABLE", "NOT_COVERED", "GUIDELINE_REVIEW"]


class Result(BaseModel):
    determination: Determination
    reason: str = ""
    guideline_id: Optional[str] = None
    guideline_title: Optional[str] = None
    guideline_payer: Optional[str] = None
    guideline_number: Optional[str] = None
    key: Optional[Order] = None            # the order as detected in the chart (before any override or mapping)
    verification: Optional[Verification] = None  # whether the chosen guideline applies, and why
    order: Optional[Order] = None          # the order judged: key plus overrides, cpt from the match
    best_scenario: Optional[str] = None
    scenarios: list[ScenarioResult] = Field(default_factory=list)
    misses: list[Miss] = Field(default_factory=list)
    confidence: float = 1.0                # best scenario's compiled confidence (1.0 when no judging happened)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)
    run_id: Optional[str] = None


# ---------------------------------------------------------------- what the coordinator reads


class PacketQuote(BaseModel):
    quote: str                             # exact chart text (Source.text)
    source: str                            # "Consult note, March 18, 2025"


class PacketItem(BaseModel):
    criterion: str
    label: str                             # plain-English name of the requirement
    quotes: list[PacketQuote] = Field(default_factory=list)  # one usually; two for a duration (start, latest)
    status: Literal["met", "missing", "contradicted"] = "met"  # contradicted: NOT_MET leaf, the chart says otherwise
    missing: bool = False                  # INSUFFICIENT leaf on the best pathway: evidence is what the chart does say
    note: str = ""                         # for missing / contradicted items: what is absent or what the chart says
