"""Each case keeps the exact checklist it was judged with (data/results/<chart_id>/criteria.json), and the shared H
cache is written once, first writer wins. Two cases confirming the same section at once used to share (and
overwrite) one cached file; with a non-deterministic H the first case's page then showed the other case's ids.
Offline: stub model, store in tmp_path, the two resumes interleaved by events in the stub."""
from __future__ import annotations

import hashlib
import re
import threading

import pytest

from app import pipeline
from app.core import llm, store
from app.review import ask, review, tree
from app.core.models import CriteriaSet, Expression
from tests.conftest import SAMPLES, sid
from tests.fake import Stub

GSV = {"code": "36475", "pathway": "gsv"}


def _rename(d: dict, suffix: str) -> dict:
    """The stub's checklist / verdicts with every requirement id suffixed: another run of a non-deterministic H."""
    if "criteria" in d:
        ids = [c["id"] for c in d["criteria"]]
        d["criteria"] = [dict(c, id=c["id"] + suffix) for c in d["criteria"]]
        for e in d["logic"]:
            e["logic"] = re.sub(r"\b(" + "|".join(map(re.escape, ids)) + r")\b", lambda m: m.group(1) + suffix, e["logic"])
    if "verdicts" in d:
        d["verdicts"] = [dict(v, criterion=v["criterion"] + suffix) for v in d["verdicts"]]
    return d


class Two:
    """One llm.call for two charts, told apart by run id: chart -> (suffix, gate). A chart's H waits on its gate."""

    def __init__(self, g, r):
        self.stub = Stub(g, r)
        self.by_run: dict[str, tuple[str, threading.Event | None]] = {}
        self.h_done: dict[str, threading.Event] = {}
        self.h_calls: list[str] = []

    def __call__(self, run_id, step, prompt, schema, **kw):
        suffix, gate = self.by_run.get(run_id, ("", None))
        if step == "criteria_guideline":
            self.h_calls.append(suffix)
            if gate is not None:
                assert gate.wait(10)
        out = self.stub(run_id, step, prompt, schema, **kw)
        if suffix and step in ("criteria_guideline", "judge_chart"):
            out = schema.model_validate(_rename(out.model_dump(by_alias=True), suffix))
        return out


@pytest.fixture
def two(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    t = Two(fl_spans, delgado_spans)
    monkeypatch.setattr(llm, "call", t)
    for cid in ("c1", "c2"):
        assert pipeline.run("", cid, gid, rspans=delgado_spans, pause_at_pathways=True) is None
    from app.core.status import load_status
    t.run = {cid: load_status(cid)["run_id"] for cid in ("c1", "c2")}
    t.g = fl_spans
    return t


def _ids(cid: str) -> set[str]:
    return {x["criterion"] for x in review.case_view(cid)["requirements"]}


def _tree_ids(cid: str) -> set[str]:
    return {it["criterion"] for b in tree.build(cid)["blocks"] for it in b.get("items", [])}


def _resume(cid: str, errors: list):
    try:
        pipeline.resume(cid, [GSV], by="Dana")
    except Exception as e:                         # surfaced by the test, not swallowed
        errors.append(e)


def test_two_cases_on_one_section_keep_their_own_checklists(two, monkeypatch):
    """c1 starts H first but c2's (different ids) finishes and writes the cache first: the shared file holds c2's
    set, c1 keeps and shows its own (pinned), and neither case's page, tree or ask reads the other's ids."""
    monkeypatch.setattr(pipeline, "H_WAIT_S", 0)          # both build: the race the lock must survive
    gate1 = threading.Event()
    two.by_run[two.run["c1"]] = ("", gate1)
    two.by_run[two.run["c2"]] = ("_b", None)
    errors: list = []
    a = threading.Thread(target=_resume, args=("c1", errors))
    a.start()
    while two.h_calls.count("") < 1:                      # c1 is inside its H build, holding the build marker
        a.join(0.01)
    _resume("c2", errors)                                 # c2 builds, writes the shared cache, judges, decides
    gate1.set()
    a.join(10)
    assert not errors and not a.is_alive()
    assert sorted(two.h_calls) == ["", "_b"]

    key_h = store.load_confirmation("c1")["h_key"]
    assert key_h == store.load_confirmation("c2")["h_key"]
    shared = {c.id for c in store.load_hcache(key_h).criteria}
    assert "size_b" in shared and "size" not in shared   # the first writer's set, not overwritten by c1
    assert {c.id for c in store.load_case_criteria("c1").criteria} >= {"size", "reflux"}
    assert {c.id for c in store.load_case_criteria("c2").criteria} >= {"size_b", "reflux_b"}

    assert "size" in _ids("c1") and not any(x.endswith("_b") for x in _ids("c1"))
    assert "size_b" in _ids("c2") and "size" not in _ids("c2")
    assert "size" in _tree_ids("c1") and "size_b" in _tree_ids("c2")
    for cid, want in (("c1", "size"), ("c2", "size_b")):
        line = sid(two.g, "The varicosities are at least 3 millimeters", 0)
        a_ = ask.ask(cid, [line])
        assert a_["source"] == "known" and a_["requirements"] == [want]
    assert store.load_result("c1")["result"]["queue"] == store.load_result("c2")["result"]["queue"] == "ready"


def test_a_run_that_finds_the_checklist_in_flight_waits_and_reuses_it(two, monkeypatch):
    monkeypatch.setattr(pipeline, "H_WAIT_S", 10)
    gate1 = threading.Event()
    two.by_run[two.run["c1"]] = ("", gate1)
    two.by_run[two.run["c2"]] = ("_b", None)
    errors: list = []
    a = threading.Thread(target=_resume, args=("c1", errors))
    a.start()
    while two.h_calls.count("") < 1:
        a.join(0.01)
    b = threading.Thread(target=_resume, args=("c2", errors))
    b.start()
    b.join(0.3)
    assert b.is_alive()                                   # c2 waits for c1's build
    gate1.set()
    a.join(10)
    b.join(10)
    assert not errors and two.h_calls == [""]             # one H build for both
    assert "size" in _ids("c2") and {c.id for c in store.load_case_criteria("c2").criteria} == \
        {c.id for c in store.load_case_criteria("c1").criteria}


def test_save_criteria_and_save_hcache_first_writer_wins(tmp_store):
    from app.core.models import Guideline, Narrowed, Payer
    n1 = Narrowed(key="k", guideline=Guideline(id="g1", sha256="s", payer=Payer(name="One")))
    n2 = Narrowed(key="k", guideline=Guideline(id="g1", sha256="s", payer=Payer(name="Two")))
    a = CriteriaSet(key="k", criteria=[], expressions=[Expression(pathway="gsv", expr="x")])
    b = CriteriaSet(key="k", criteria=[], expressions=[Expression(pathway="gsv", expr="y")])
    got_n, got_c = store.save_criteria("k", n1, None)
    assert got_n.guideline.payer.name == "One" and got_c is None
    got_n, got_c = store.save_criteria("k", n2, a)        # the narrowed guideline stays; the checklist fills in
    assert got_n.guideline.payer.name == "One" and got_c.expressions[0].expr == "x"
    got_n, got_c = store.save_criteria("k", n2, b)        # a second checklist for the same pathways is not written
    assert got_c.expressions[0].expr == "x" and store.load_criteria("k")[1].expressions[0].expr == "x"
    assert store.save_hcache("h-k", b).expressions[0].expr == "y"
    assert store.save_hcache("h-k", a).expressions[0].expr == "y"
    assert store.load_hcache("h-k").expressions[0].expr == "y"
