"""Shared step-H test helpers: the FL guideline's section picked for 36475 (great saphenous vein), a few of its
requirement lines, and a scripted fake model. Used by the product's step-H tests and by experiments/tests."""
from __future__ import annotations

import pytest

from app.checklist import criteria
from app.core import llm
from app.core.models import Order, Procedure
from app.understand import narrow
from app.understand.select import select
from tests.fake import narrow_answer

REFLUX = "There is demonstrated saphenous reflux"
SIZE = "The varicosities are at least 3 millimeters in size"
ADL = "the symptoms significantly interfere with activities of daily living"
HEAD = "Great or Small Saphenous Veins"


def _sel(fl_spans):
    n = narrow.resolve(narrow.COut.model_validate(narrow_answer(fl_spans, {"target": "great saphenous vein", "cpt": ["36475"]})),
                       fl_spans, "g", "s", "k", [])
    return n, select(n, Order(procedure=Procedure(cpt=["36475"], target="great saphenous vein")), fl_spans)


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(llm, "RUNS", tmp_path / "runs")
    return tmp_path


def C(id, quote, **kw):
    return {"id": id, "quote": quote, "refs": [], "question": f"{id}?", **kw}


def H(pid, logic, *crit, notes=""):
    return {"notes": notes, "criteria": list(crit), "logic": [{"pathway": pid, "logic": logic}]}


def script(monkeypatch, rounds, audit=None):
    """The fake model: criteria_loop answers in order; criteria_audit answers `audit` (default: nothing found)."""
    sent = []

    def fake(run_id, step, prompt, schema, **_):
        sent.append((step, prompt))
        if step == "criteria_audit":
            return schema.model_validate(audit or {})
        return schema.model_validate(rounds.pop(0))
    monkeypatch.setattr(llm, "call", fake)
    return sent


def pid(fl_spans):
    return criteria.picked(_sel(fl_spans)[1])[0]
