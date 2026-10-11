"""Pure tests: no network, never touch data/. The store is pointed at tmp_path; the model is a stub that answers
each step from span text, so the whole pipeline runs offline."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core import llm, store
from app.ingest.pdf import pdf_to_text
from app.ingest.spans import split_chart, split_guideline

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    for name in ("GUIDELINES", "CRITERIA", "CHARTS", "RESULTS", "RUNS"):
        d = tmp_path / name.lower()
        d.mkdir()
        monkeypatch.setattr(store, name, d)
    monkeypatch.setattr(llm, "RUNS", tmp_path / "runs")
    return tmp_path


@pytest.fixture(scope="session")
def fl_text() -> str:
    return pdf_to_text(SAMPLES / "fl_varicose_veins_guideline.pdf")


@pytest.fixture(scope="session")
def fl_spans(fl_text):
    return split_guideline(fl_text)


@pytest.fixture(scope="session")
def delgado_spans():
    return split_chart(pdf_to_text(SAMPLES / "synthetic" / "maria_delgado_chart.pdf"))


def sid(spans, needle: str, start: int = 0) -> str:
    """The first span (from `start`) whose line contains `needle`. Spans are lines, so the needle must fit on one."""
    for s in spans[start:]:
        if needle.lower() in s.text.lower():
            return s.id
    raise AssertionError(f"no span contains {needle!r}")


def idx(spans, span_id: str) -> int:
    return [s.id for s in spans].index(span_id)


def rng(spans, first: str, last: str, start: int = 0) -> str:
    """A range citation "g0049-g0054": from the line holding `first` to the next line (at or after it) holding `last`."""
    a = sid(spans, first, start)
    b = sid(spans, last, idx(spans, a))
    return f"{a}-{b}"


def accept_all(client, cid: str) -> dict:
    """Accept every requirement the case is built from that is not struck or accepted yet; the last document."""
    d = client.get(f"/api/review/{cid}").json()
    for x in d["case"]["requirements"]:
        if x["counted"] and x["mark"] != "struck" and not x["accepted"] and not x.get("in_ask"):
            r = client.post(f"/api/review/{cid}/accepts", json={"criterion": x["criterion"], "by": "Dana"})
            assert r.status_code == 201, r.text
            d = r.json()
    return d


@pytest.fixture(autouse=True)
def _step_h_loose_for_tests(monkeypatch):
    """Tests were written against loose's keys and prompts; the shipped default (loose-next) is checked in test_pins."""
    import os
    if "STEP_H" not in os.environ:
        monkeypatch.setenv("STEP_H", "loose")
