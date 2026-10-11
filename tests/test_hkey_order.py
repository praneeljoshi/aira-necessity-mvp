"""The review flow's H cache is keyed by the order as well as the confirmed section (pipeline.h_cache_key): H's
prompt carries the order (criteria.request_line) and its tree can hold order-specific conditions (a technique, a CPT
descriptor). Found on real data: a laser order (36478) was served a radiofrequency order's (36475) checklist for the
same section, and resume copied that tree into the laser order's cache. Offline: stub model, store in tmp_path; the
stub's H writes the prompt's request line into a criterion, so each tree shows which order it was built for."""
from __future__ import annotations

import hashlib
import re

import pytest

from app import llm, pipeline, store
from app.models import Procedure
from app.status import load_status
from tests.conftest import SAMPLES
from tests.fake import Stub

RF = ("36475", "Endovenous radiofrequency ablation, left great saphenous vein")
LASER = ("36478", "Endovenous laser ablation, left great saphenous vein")


class ByOrder:
    """The stub, with the order's words chosen per chart (its code is the coordinator's override) and H echoing
    the request line."""

    def __init__(self, g, r):
        self.stub = Stub(g, r)
        self.h_calls: list[str] = []
        self.next_order = RF

    def __call__(self, run_id, step, prompt, schema, **kw):
        if step == "detect_order":
            cpt, words = self.next_order
            d = self.stub(run_id, step, prompt, schema).model_dump(by_alias=True)
            d["procedure"]["as_written"] = words
            return schema.model_validate(d)
        out = self.stub(run_id, step, prompt, schema, **kw)
        if step == "criteria_guideline":
            req = re.search(r"## The request\n\n(.*?)\n", prompt).group(1)
            self.h_calls.append(req)
            d = out.model_dump(by_alias=True)
            d["criteria"][0]["question"] = f"Reflux on duplex, for {req}?"
            out = schema.model_validate(d)
        return out


@pytest.fixture
def world(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    m = ByOrder(fl_spans, delgado_spans)
    monkeypatch.setattr(llm, "call", m)

    def check(cid, order):
        m.next_order = order
        assert pipeline.run("", cid, gid, rspans=delgado_spans, override={"cpt": [order[0]]},   # the coordinator's code
                            pause_at_pathways=True) is None
        return pipeline.resume(cid, [{"code": order[0], "pathway": "gsv"}], by="Dana")
    m.check, m.sha = check, sha
    return m


def _words(cs) -> str:
    return " ".join(c.question or "" for c in cs.criteria)


def test_two_orders_on_one_section_get_their_own_trees(world):
    world.check("rf", RF)
    world.check("laser", LASER)
    assert len(world.h_calls) == 2                       # the laser order built its own H, not a cache hit
    assert "radiofrequency" in world.h_calls[0] and "laser" in world.h_calls[1]
    k_rf, k_laser = (store.load_confirmation(c)["h_key"] for c in ("rf", "laser"))
    assert k_rf != k_laser and "-o36475-great-saphenous-vein-" in k_rf and "-o36478-great-saphenous-vein-" in k_laser
    # neither shared entry overwrote the other
    assert "radiofrequency" in _words(store.load_hcache(k_rf)) and "laser" not in _words(store.load_hcache(k_rf))
    assert "laser" in _words(store.load_hcache(k_laser)) and "radiofrequency" not in _words(store.load_hcache(k_laser))
    # each case is judged with, and pins, its own tree
    assert "laser" in _words(store.load_case_criteria("laser")) and "radiofrequency" not in _words(store.load_case_criteria("laser"))
    assert "radiofrequency" in _words(store.load_case_criteria("rf"))
    # the laser order's own C/H cache is filled from its own tree, not the radiofrequency one
    k_order = store.load_confirmation("laser")["narrowed_key"]
    assert k_order == pipeline.cache_key(world.sha, store.load_order("laser").procedure) and "-36478-" in k_order
    assert "laser" in _words(store.load_criteria(k_order)[1]) and "radiofrequency" not in _words(store.load_criteria(k_order)[1])


def test_the_same_order_twice_is_a_cache_hit(world):
    world.check("a", RF)
    world.check("b", RF)
    assert len(world.h_calls) == 1
    assert store.load_confirmation("a")["h_key"] == store.load_confirmation("b")["h_key"]
    st = {s["id"]: s for s in load_status("b")["stages"]}
    assert st["checklist"]["cached"] is True
    assert "radiofrequency" in _words(store.load_case_criteria("b"))


def test_precompute_trees_are_never_read_for_an_order(world, fl_spans):
    """Precompute writes under the order-less key (-onone); every order's key carries its facts instead."""
    from types import SimpleNamespace
    n = SimpleNamespace(pathways=[SimpleNamespace(id="gsv", spans=[SimpleNamespace(first=fl_spans[0].id, last=fl_spans[3].id)])])
    none = pipeline.h_cache_key(world.sha, n, ["gsv"], None)
    assert "-onone-" in none
    for p in (Procedure(), Procedure(cpt=["36475"]), Procedure(target="great saphenous vein"),
              Procedure(diagnosis="I83.811"), Procedure(plan="RFA")):
        assert pipeline.h_cache_key(world.sha, n, ["gsv"], p) != none


def test_the_order_key_and_the_h_key_share_one_order_part(world, fl_spans):
    from types import SimpleNamespace
    n = SimpleNamespace(pathways=[SimpleNamespace(id="gsv", spans=[SimpleNamespace(first=fl_spans[0].id, last=fl_spans[3].id)])])
    p = Procedure(cpt=["36478", "36475"], target="left great saphenous vein", diagnosis="Varicose veins I83.811, I87.2",
                  plan="laser then sclerotherapy")
    facts = pipeline.order_facts(p)
    assert facts.startswith("36475+36478-great-saphenous-vein-I83.811+I87.2-p")
    assert f"-{facts}-" in pipeline.cache_key(world.sha, p) and f"-o{facts}-" in pipeline.h_cache_key(world.sha, n, ["gsv"], p)
    right = p.model_copy(update={"target": "right great saphenous vein"})       # side is not an order fact
    assert pipeline.h_cache_key(world.sha, n, ["gsv"], right) == pipeline.h_cache_key(world.sha, n, ["gsv"], p)
    for k, v in (("cpt", ["36475"]), ("target", "small saphenous vein"), ("diagnosis", "I83.812"), ("plan", "RFA")):
        assert pipeline.h_cache_key(world.sha, n, ["gsv"], p.model_copy(update={k: v})) != pipeline.h_cache_key(world.sha, n, ["gsv"], p)
