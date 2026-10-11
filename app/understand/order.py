"""Step B: the order, read from the whole chart (patient, payer, procedure{cpt, as_written, target, surgeon,
diagnosis, plan}, refs), and the coordinator's corrections to it."""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from app.core import llm, log
from app.core.models import Order, Procedure, Span
from app.evidence import refs
from app.ingest.spans import render_chart, resolves, table

logger = log.get("pipeline")

class _Proc(BaseModel):
    cpt: list[str] = Field(default_factory=list)
    as_written: Optional[str] = None
    target: Optional[str] = None
    surgeon: Optional[str] = None
    diagnosis: Optional[str] = None
    plan: Optional[str] = None


class BOut(BaseModel):
    patient_name: Optional[str] = None
    payer: Optional[str] = None
    procedure: _Proc = Field(default_factory=_Proc)
    refs: list[str] = Field(default_factory=list)


_CODE = re.compile(r"^\s*([0-9]{4}[0-9A-Z]|[A-Z][0-9]{4})")


def base_code(c: str) -> str:
    """The CPT/HCPCS code without its modifier: "36475-LT", "36475 RT", "36475-50" -> "36475". A code table lists
    base codes; the side is the order's target, not part of the code."""
    m = _CODE.match((c or "").upper())
    return m.group(1) if m else (c or "").strip().upper()


def detect_order(rspans: list[Span], chart_id: str, run_id: str) -> Order:
    out = llm.call(run_id, "detect_order", llm.prompt("detect_order", chart_spans=render_chart(rspans)), BOut,
                   model=llm.pick_models()[0])
    tbl = table(rspans)
    text = " ".join(s.text for s in rspans)
    cpt = []
    for c in out.procedure.cpt:
        c = base_code(c)
        if c and re.search(rf"(?<![0-9A-Z]){re.escape(c)}(?![0-9A-Z])", text.upper()):
            cpt.append(c)
        else:
            logger.warning("order: code %r is not written in the chart; dropped", c)
    plan = (out.procedure.plan or "").strip() or None
    if plan and not refs.written_in([s.text for s in rspans], plan):
        logger.warning("order: plan %r is not written in the chart; dropped", plan)
        plan = None
    o = Order(id=chart_id, chart_id=chart_id, patient_name=out.patient_name, payer=out.payer,
              procedure=Procedure(cpt=list(dict.fromkeys(cpt)), as_written=out.procedure.as_written,
                                  target=out.procedure.target, surgeon=out.procedure.surgeon,
                                  diagnosis=out.procedure.diagnosis, plan=plan),
              refs=[r for r in out.refs if resolves(r, tbl)])
    logger.info("order: payer=%r cpt=%s as_written=%r target=%r surgeon=%r plan=%r", o.payer, o.procedure.cpt,
                o.procedure.as_written, o.procedure.target, o.procedure.surgeon, o.procedure.plan)
    return o


def apply_override(o: Order, override: Optional[dict]) -> Order:
    """The coordinator's corrections: codes, target and/or the member's plan."""
    if not override:
        return o
    p = o.procedure.model_copy()
    if override.get("cpt") is not None:
        p.cpt = list(dict.fromkeys(base_code(c) for c in override["cpt"] if c and c.strip()))
    if override.get("target"):
        p.target = str(override["target"]).strip()
    if override.get("plan"):
        p.plan = str(override["plan"]).strip()
    return o.model_copy(update={"procedure": p})
