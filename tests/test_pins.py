"""Ship pins: structure gpt-6-sol, judge gpt-6-luna, STEP_H loose, without asking the API; the C/H cache keys carry
the structure model and a prompt version, and A2's sections cache the model, so a tree or labels built by another
model or prompt are never served; a case judged under an older key still shows from its pinned copy. Offline."""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import llm, main, pipeline, status, store
from app.models import Procedure
from tests.conftest import SAMPLES
from tests.fake import Stub

PROC = Procedure(cpt=["36475"], target="left great saphenous vein")
SHA = "s" * 64


@pytest.fixture
def no_api(monkeypatch):
    def boom():
        raise AssertionError("pick_models must not ask the API")
    monkeypatch.setattr(llm, "client", boom)


def test_pins_without_the_api(monkeypatch, no_api):
    for k in ("MODEL_STRUCTURE", "MODEL_JUDGE", "STEP_H"):
        monkeypatch.delenv(k, raising=False)
    assert llm.pick_models() == ("gpt-6-sol", "gpt-6-luna")
    assert llm.pick_models(["gpt-5.5", "gpt-5.5-2026-01-01"]) == ("gpt-6-sol", "gpt-6-luna")   # a list is ignored
    assert pipeline.step_h() == "loose-next"
    monkeypatch.setenv("MODEL_STRUCTURE", "gpt-x")
    assert llm.pick_models() == ("gpt-x", "gpt-6-luna")
    monkeypatch.setenv("MODEL_JUDGE", "gpt-y")
    assert llm.pick_models() == ("gpt-x", "gpt-y")
    assert llm.choose_flagship(["gpt-5.5", "gpt-5.5-2026-01-01"]) == "gpt-5.5"        # kept for scripts


def _n(fl_spans):
    """h_cache_key reads only the pathways' ids and line ranges."""
    rng = SimpleNamespace(first=fl_spans[0].id, last=fl_spans[3].id)
    return SimpleNamespace(pathways=[SimpleNamespace(id="gsv", spans=[rng])])


def test_keys_follow_the_model(monkeypatch, fl_spans):
    monkeypatch.setenv("STEP_H", "loose")
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("gpt-6-sol", "gpt-6-luna"))
    k1 = pipeline.cache_key(SHA, PROC)
    assert k1 == f"ssssssssssssssss-36475-great-saphenous-vein-mgpt-6-sol-v{pipeline.prompt_version()}"
    n = _n(fl_spans)
    h1 = pipeline.h_cache_key(SHA, n, ["gsv"], PROC)
    assert h1.endswith(f"-mgpt-6-sol-v{pipeline.prompt_version(with_c=False)}")
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("gpt-5.5", "gpt-6-luna"))
    assert pipeline.cache_key(SHA, PROC) != k1 and "-mgpt-5.5-v" in pipeline.cache_key(SHA, PROC)
    assert pipeline.h_cache_key(SHA, n, ["gsv"], PROC) != h1
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("gpt-6-sol", "gpt-5.5"))   # the judge is not in the key
    assert pipeline.cache_key(SHA, PROC) == k1 and pipeline.h_cache_key(SHA, n, ["gsv"], PROC) == h1


def test_keys_follow_the_prompt_files(monkeypatch, fl_spans):
    monkeypatch.delenv("STEP_H", raising=False)
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    n = _n(fl_spans)
    k, h = pipeline.cache_key(SHA, PROC), pipeline.h_cache_key(SHA, n, ["gsv"], PROC)
    real = pipeline._prompt_bytes

    def edited(which):
        return lambda name: real(name) + (b" edited" if name == which else b"")
    monkeypatch.setattr(pipeline, "_prompt_bytes", edited("reduce/plan"))          # an H prompt: both keys move
    assert pipeline.cache_key(SHA, PROC) != k and pipeline.h_cache_key(SHA, n, ["gsv"], PROC) != h
    monkeypatch.setattr(pipeline, "_prompt_bytes", edited("narrow_guideline"))     # C's prompt: the order key only
    assert pipeline.cache_key(SHA, PROC) != k and pipeline.h_cache_key(SHA, n, ["gsv"], PROC) == h
    monkeypatch.setattr(pipeline, "_prompt_bytes", edited("judge_chart"))          # not C or H: nothing moves
    assert pipeline.cache_key(SHA, PROC) == k and pipeline.h_cache_key(SHA, n, ["gsv"], PROC) == h
    monkeypatch.setattr(pipeline, "_prompt_bytes", real)
    monkeypatch.setenv("STEP_H", "script")                                          # another mode, other files
    assert pipeline.prompt_version(with_c=False) != pipeline.prompt_version(with_c=False, mode="loose")
    assert pipeline.h_cache_key(SHA, n, ["gsv"], PROC) != h


@pytest.fixture
def world(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.delenv("STEP_H", raising=False)
    monkeypatch.setattr(main, "BACKGROUND", False)
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")

    def check(chart_id, model):
        monkeypatch.setattr(llm, "pick_models", lambda ids=None: (model, model))
        stub = Stub(fl_spans, delgado_spans)
        monkeypatch.setattr(llm, "call", stub)
        return pipeline.run("", chart_id, gid, rspans=delgado_spans), stub
    return check, TestClient(main.app), sha


def test_another_model_never_reads_the_old_trees(world):
    check, _, _ = world
    r, s1 = check("a", "gpt-5.5")
    assert r.determination == "MET" and "narrow_guideline" in s1.calls and "criteria_guideline" in s1.calls
    r, s2 = check("b", "gpt-5.5")                              # same model: C, H and A2 come from the caches
    assert "narrow_guideline" not in s2.calls and "criteria_guideline" not in s2.calls
    r, s3 = check("a", "gpt-6-sol")                            # the pins changed: C, H and A2 are built again
    assert {"narrow_guideline", "criteria_guideline", "chart_sections"} <= set(s3.calls)
    assert status.load_status("a")["tree"]["model"] == "gpt-6-sol"
    assert "-mgpt-6-sol-v" in status.load_status("a")["tree"]["criteria_key"]


def test_sections_cache_keeps_its_model(world, delgado_spans):
    check, _, _ = world
    check("a", "gpt-5.5")
    sha = pipeline._lines_sha(delgado_spans)
    assert store.load_sections("a", sha, model="gpt-5.5") is not None
    assert store.load_sections("a", sha, model="gpt-6-sol") is None
    p = store.CHARTS / "a" / "sections.json"
    d = json.loads(p.read_text())
    d.pop("model")
    p.write_text(json.dumps(d))                                 # written before the model was kept
    assert store.load_sections("a", sha, model="gpt-5.5") is None
    assert store.load_sections("a", sha) is not None            # labels for showing the case it was read with


def test_an_old_case_still_renders(world, monkeypatch):
    check, c, sha = world
    check("old", "gpt-5.5")
    before = c.get("/api/orders/old/tree").json()["tree"]
    assert before["sections"] and any(ln["kind"] == "req" for ln in before["sections"][0]["lines"])
    # make it an older case: its cache file under the key from before models were in it, no key recorded
    st = status.load_status("old")
    key = st["tree"]["criteria_key"]
    o = store.load_order("old")
    legacy = pipeline.legacy_cache_key(sha, o.procedure)
    (store.CRITERIA / f"{key}.json").rename(store.CRITERIA / f"{legacy}.json")
    st.pop("tree")
    status.save_status("old", st)
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("gpt-6-sol", "gpt-6-luna"))   # today's pins

    def no_model(*a, **k):
        raise AssertionError("showing a case never calls the model")
    monkeypatch.setattr(llm, "call", no_model)
    assert pipeline.case_order_key(sha, o.procedure, "old") == legacy
    assert store.load_case_criteria("old") is not None          # its checklist: the copy pinned in its folder
    after = c.get("/api/orders/old/tree").json()["tree"]
    assert after["sections"] == before["sections"]
    d = c.get("/api/orders/old").json()
    assert d["result"]["determination"] == "MET" and d["decided"]["sections"]
    rv = c.get("/api/review/old")
    assert rv.status_code == 200, rv.text
