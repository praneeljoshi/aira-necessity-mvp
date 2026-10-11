"""PRECOMPUTE_H=1 builds every indication's checklist at guideline upload, under the order-less H key (`-onone`),
which resume never reads (the H key carries the order: tests/test_hkey_order.py); off by default, nothing runs
ahead of a chart."""
from __future__ import annotations

from app import pipeline
from app.checklist import keys
from app.core import llm, store
from tests.fake import Stub


def test_off_by_default_builds_nothing(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.delenv("PRECOMPUTE_H", raising=False)
    assert pipeline.precompute_wanted() is False


def test_precompute_builds_h_per_pathway_under_the_orderless_key(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    import hashlib
    monkeypatch.setenv("PRECOMPUTE_H", "1")
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    stub = Stub(fl_spans, delgado_spans)
    monkeypatch.setattr(llm, "call", stub)
    gid = pipeline.add_guideline(fl_text, "fl.pdf", hashlib.sha256(b"fl").hexdigest(), "bcbsfl-02-33000-31")
    out = pipeline.precompute(gid)
    assert out["pathways"] and set(out["built"]) == set(out["pathways"]) and out["cached"] == []
    assert stub.calls.count("narrow_guideline") == 1 and stub.calls.count("criteria_guideline") == len(out["pathways"])
    _, sha, _ = store.load_guideline_spans(gid)
    n, _ = store.load_criteria(keys.cache_key(sha, pipeline.Procedure()))
    for pid in out["pathways"]:
        assert store.load_hcache(keys.h_cache_key(sha, n, [pid], None)) is not None
    again = pipeline.precompute(gid)                      # a second call reads the cache
    assert again["built"] == [] and set(again["cached"]) == set(out["pathways"])
