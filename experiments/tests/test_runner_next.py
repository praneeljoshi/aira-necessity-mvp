"""The reduce runner (experiments/scripts/reduce_code.py) dispatches STEP_H=loose-next to the shipped step H."""
from __future__ import annotations

import json

import pytest  # noqa: F401

from app.checklist import reduce_next


def test_runner_dispatch(fl_spans, monkeypatch, tmp_path):
    import experiments.scripts.reduce_code as R
    from app.core import store
    monkeypatch.setenv("STEP_H", "loose-next")
    monkeypatch.setattr(R, "BASE", tmp_path)
    monkeypatch.setattr(R, "guideline", lambda slug: ("g", fl_spans, "s" * 64))
    monkeypatch.setattr(store, "load_criteria", lambda key: (None, None))
    got = {}

    def fake(*a, **k):
        got.update(k)
        raise RuntimeError("dispatched")
    monkeypatch.setattr(reduce_next, "build", fake)
    out = R.one({"guideline": "g", "pathway": "P", "cpt": ["36475"], "age": 58})
    assert "dispatched" in out["error"] and got["extra"]["age"] == 58 and "-hloose-next-" in out["key"]
    assert R.base("gpt-6-sol").parts[-2:] == ("reduce_loose", "gpt-6-sol")
    json.dumps(out)
