"""A check cut off by a server restart: at startup every check left "running" that nothing works on is failed with
a plain message, and retry runs it again; a check really being worked on still answers 409. Offline, tmp store."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import llm, main, pipeline, status
from tests.conftest import SAMPLES
from tests.fake import Stub


@pytest.fixture
def world(tmp_store, fl_text, fl_spans, delgado_spans, monkeypatch):
    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(main, "BACKGROUND", False)
    monkeypatch.setattr(llm, "call", Stub(fl_spans, delgado_spans))
    monkeypatch.setattr(main, "LIVE", {})
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    c = TestClient(main.app)
    with open(SAMPLES / "synthetic" / "maria_delgado_chart.pdf", "rb") as f:
        cid = c.post("/api/charts", files={"file": ("delgado.pdf", f, "application/pdf")},
                     data={"guideline_id": gid}).json()["chart_id"]
    return c, cid


def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def left_running(cid, pid, stage="read"):
    """The status a restart leaves behind: the check and one stage still say running."""
    st = status.load_status(cid)
    for s in st["stages"]:
        if s["id"] == stage:
            s.update(status="running", ended_at=None, doing="Checking 9 requirements", error=None)
    st.update(state="running", ended_at=None, current=stage, error=None)
    if pid is None:
        st.pop("pid", None)
    else:
        st["pid"] = pid
    status.save_status(cid, st)
    return st


def test_restart_marks_failed_and_retry_runs_again(world):
    c, cid = world
    left_running(cid, dead_pid())
    with TestClient(main.app):              # startup runs the sweep
        pass
    st = status.load_status(cid)
    assert st["state"] == "failed" and st["error"] == status.INTERRUPTED and st["ended_at"] and st["current"] is None
    read = next(s for s in st["stages"] if s["id"] == "read")
    assert read["status"] == "failed" and read["error"] == status.INTERRUPTED and read["doing"] == ""
    assert "thread" not in status.INTERRUPTED and "status.json" not in status.INTERRUPTED
    r = c.post(f"/api/orders/{cid}/retry")
    assert r.status_code == 200, r.text
    assert r.json()["result"]["determination"] == "MET"
    assert status.load_status(cid)["state"] == "done"


def test_retry_alone_treats_an_unheld_running_check_as_interrupted(world):
    c, cid = world
    left_running(cid, dead_pid())          # no restart sweep: retry itself sees nothing holds it
    r = c.post(f"/api/orders/{cid}/retry")
    assert r.status_code == 200, r.text
    assert r.json()["result"]["determination"] == "MET"


def test_review_retry_after_restart(world):
    c, cid = world
    left_running(cid, dead_pid())
    assert status.sweep_interrupted(main.is_live) == [cid]
    assert c.post(f"/api/review/{cid}/retry").status_code == 200


def test_a_check_being_worked_on_still_answers_409(world):
    c, cid = world
    left_running(cid, os.getpid())
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, daemon=True)
    t.start()
    main.LIVE[cid] = t
    try:
        assert status.sweep_interrupted(main.is_live) == []
        assert status.load_status(cid)["state"] == "running"
        assert c.post(f"/api/orders/{cid}/retry").status_code == 409
        assert c.post(f"/api/review/{cid}/retry").status_code == 409
    finally:
        stop.set()
        t.join()
    # the worker ended without closing the record: now it is an interrupted check
    assert c.post(f"/api/orders/{cid}/retry").status_code == 200


def test_held_by_another_live_process_is_left_alone(world):
    c, cid = world
    left_running(cid, os.getppid())        # e.g. another server on the same data
    assert status.sweep_interrupted(main.is_live) == []
    assert c.post(f"/api/orders/{cid}/retry").status_code == 409


def test_older_record_without_pid_goes_by_its_heartbeat(world):
    c, cid = world
    left_running(cid, None)                # just written: the heartbeat could still be touching it
    assert status.sweep_interrupted(main.is_live) == []
    old = time.time() - status.STALE_S - 5
    os.utime(status.status_path(cid), (old, old))
    assert status.sweep_interrupted(main.is_live) == [cid]


def test_live_registry_is_cleared_when_the_work_ends(world, monkeypatch):
    monkeypatch.setattr(main, "BACKGROUND", True)
    gate = threading.Event()
    main.run_tracked("x1", gate.wait, "check-x1")
    assert main.is_live("x1")
    gate.set()
    for _ in range(100):
        if "x1" not in main.LIVE:
            break
        time.sleep(0.01)
    assert "x1" not in main.LIVE and not main.is_live("x1")
