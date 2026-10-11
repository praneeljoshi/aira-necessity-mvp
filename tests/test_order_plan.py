"""Step B reads the member's plan from the chart (procedure.plan) and it reaches H's request line, where the plan rule
prunes plan-only conditions (FEP, SAO). Shipped once with plan always None: Delgado ("PPO — BlueOptions") was asked for
"Federal Employee Program (FEP): Follow FEP guidelines". Code keeps a plan only when it is printed in the chart; the
coordinator's override can set it. Offline: stub model, store in tmp_path."""
from __future__ import annotations

import hashlib
import re

import pytest

from app import llm, pipeline
from app.models import Order, Procedure
from app.pdf import pdf_to_text
from app.spans import split_chart
from tests.conftest import SAMPLES
from tests.fake import Stub


class WithPlan:
    def __init__(self, g, r, plan):
        self.stub, self.plan, self.h_requests = Stub(g, r), plan, []

    def __call__(self, run_id, step, prompt, schema, **kw):
        out = self.stub(run_id, step, prompt, schema, **kw)
        if step == "detect_order":
            d = out.model_dump(by_alias=True)
            d["procedure"]["plan"] = self.plan
            return schema.model_validate(d)
        if step == "criteria_guideline":
            self.h_requests.append(re.search(r"## The request\n\n(.*?)\n", prompt).group(1))
        return out


@pytest.fixture
def run_with(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    def go(cid, plan, override=None):
        m = WithPlan(fl_spans, delgado_spans, plan)
        monkeypatch.setattr(llm, "call", m)
        assert pipeline.run("", cid, gid, rspans=delgado_spans, override=override, pause_at_pathways=True) is None
        pipeline.resume(cid, [{"code": "36475", "pathway": "gsv"}], by="Dana")
        return m
    return go


def test_the_charts_plan_reaches_h(run_with):
    m = run_with("p1", "PPO — BlueOptions")                  # Delgado's chart: "Plan Type   PPO — BlueOptions"
    assert m.h_requests and "plan: PPO — BlueOptions" in m.h_requests[0]


def test_a_plan_not_printed_in_the_chart_is_dropped(run_with):
    m = run_with("p2", "FEP Blue Standard")
    assert m.h_requests and "plan:" not in m.h_requests[0]


def test_the_coordinators_plan_overrides(run_with):
    m = run_with("p3", "PPO — BlueOptions", override={"plan": "FEP Blue Basic"})
    assert "plan: FEP Blue Basic" in m.h_requests[0]
    o = pipeline.apply_override(Order(procedure=Procedure(cpt=["36475"])), {"plan": " Medicare Part B "})
    assert o.procedure.plan == "Medicare Part B"


def test_a_plan_wrapped_over_two_chart_lines_is_kept():
    """Mitchell's chart prints the plan in a two-column layout and wraps it: "Plan Name: AARP Medicare Advantage
    Choice   Plan ID: H0062-001-000" / "PPO". Joined line by line the Plan ID sits in the middle; it was dropped."""
    from app import refs
    lines = [" Payer: UnitedHealthcare                                  Plan Type: Medicare Advantage",
             " Plan Name: AARP Medicare Advantage Choice                Plan ID: H0062-001-000",
             " PPO",
             " Member ID: UHC887134521A                                 Group Number: 82734-MA-NY"]
    assert refs.written_in(lines, "AARP Medicare Advantage Choice PPO")
    assert refs.written_in(["Plan: Blue Ad-", "vantage HMO"], "Blue Advantage HMO")        # hyphen at the break
    assert refs.written_in(["Plan: Blue", "Advantage HMO"], "Blue Advantage HMO")
    assert not refs.written_in(lines, "AARP Medicare Advantage Choice HMO")
    assert not refs.written_in(lines, "FEP Blue Standard")


def test_mitchells_real_chart_keeps_his_plan():
    from app import refs
    rs = split_chart(pdf_to_text(SAMPLES / "robert_mitchell_chart_final.pdf"))
    assert refs.written_in([s.text for s in rs], "AARP Medicare Advantage Choice PPO")
