"""Step H as loose with review-load rules (STEP_H=loose-next): criteria.build with its own prompt files,
criteria_guideline_next (loose's prompt + "Swept to notes" / "Written, marked admin" / "Keep these") and
criteria_audit_next (loose's audit + the same three lists, so the audit neither adds swept lines back nor misses a kept
one). Same inputs, one reading, one retry, the add-only audit; admin leaves are pruned per case by app/checklist/admin.py as
for loose. The loose prompt files are unchanged."""
from __future__ import annotations

from typing import Callable, Optional

from app.checklist import criteria
from app.core import llm, log
from app.core.models import CriteriaSet, Narrowed, Procedure, Selection, Span

logger = log.get("reduce_next")

PROMPT = "criteria_guideline_next"
AUDIT = "criteria_audit_next"


def build(spans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
          procedure: Optional[Procedure] = None, extra: Optional[dict] = None,
          indication: Optional[str] = None, progress: Optional[Callable[[str], None]] = None) -> CriteriaSet:
    tally: dict = {}
    cs = criteria.build(spans, n, sel, key, run_id, procedure, extra=extra, indication=indication, tally=tally,
                        progress=progress, prompt=PROMPT, audit_prompt=AUDIT)
    usd = llm.dollars(tally)
    llm._log(run_id, "criteria_loose_next-cost", {"all": {**tally, "dollars": usd}})
    logger.info("criteria (loose-next) %s: %d criteria, %s, $%.2f", key, len(cs.criteria), cs.status, usd)
    return cs
