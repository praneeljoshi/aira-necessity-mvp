"""Step A2 (model, whole chart): the chart split into labelled sections, so the judge reads only the record.

    in:  r-spans
    out: Section[] {title, label evidence | summary | order | admin, spans: Range[]}
    code: ranges are single ids of the chart and run forwards; one retry with the problems
    use: the judge sees and may cite only `evidence` lines. A line no section labels as evidence is not shown: a missed
         line costs a question (not ready), a summary shown as evidence could pass a chart the record does not support.
"""
from __future__ import annotations

import os
from typing import Literal

from pydantic import BaseModel, Field

from . import hints, llm, log
from .models import Range, Span
from .narrow import retry_prompt
from .spans import in_range, render_chart

logger = log.get("sections")

Label = Literal["evidence", "summary", "order", "admin"]
EFFORT = os.environ.get("EFFORT_SECTIONS", "low")      # the A2 call's reasoning effort


class _R(BaseModel):
    first: str
    last: str


class Section(BaseModel):
    title: str
    label: Label
    spans: list[_R] = Field(default_factory=list)


class SOut(BaseModel):
    sections: list[Section] = Field(default_factory=list)


def check(out: SOut, spans: list[Span]) -> list[str]:
    pos = {s.id: i for i, s in enumerate(spans)}
    problems = []
    for s in out.sections:
        for r in s.spans:
            bad = [x for x in (r.first, r.last) if x not in pos]
            if bad:
                problems.append(f"section {s.title[:50]!r}: first/last must be single line ids of the chart, not {', '.join(bad)}")
            elif pos[r.first] > pos[r.last]:
                problems.append(f"section {s.title[:50]!r}: range {r.first}..{r.last} runs backwards")
    return problems


def split(spans: list[Span], run_id: str) -> SOut:
    base = hints.for_chart(llm.prompt("chart_sections", chart_spans=render_chart(spans)), hints.clinic_hint(spans)[1])
    model = llm.pick_models()[0]
    out = llm.call(run_id, "chart_sections", base, SOut, model=model, reasoning_effort=EFFORT)
    problems = check(out, spans)
    if problems:
        logger.warning("sections: %d problem(s), retrying once: %s", len(problems), " | ".join(problems)[:300])
        out2 = llm.call(run_id, "chart_sections", retry_prompt(base, out, problems), SOut, model=model, reasoning_effort=EFFORT)
        if len(check(out2, spans)) <= len(problems):
            out = out2
    return out


def labels(out: SOut, spans: list[Span]) -> dict[str, str]:
    """Span id -> label. A later section wins where two overlap, except that nothing overrides a non-evidence label
    with `evidence` (when the model is unsure the line stays hidden)."""
    lab: dict[str, str] = {}
    for s in out.sections:
        for r in s.spans:
            for x in in_range(spans, Range(first=r.first, last=r.last)):
                if lab.get(x.id) in (None, "evidence") or s.label != "evidence":
                    lab[x.id] = s.label
    return lab


def evidence(out: SOut, spans: list[Span]) -> list[Span]:
    lab = labels(out, spans)
    keep = [s for s in spans if lab.get(s.id) == "evidence"]
    logger.info("sections: %d of %d lines are evidence; %s", len(keep), len(spans),
                ", ".join(f"{k} {sum(1 for v in lab.values() if v == k)}" for k in ("summary", "order", "admin")))
    return keep
