"""Where a check is, stage by stage, from upload to the decision. Written to data/results/<chart_id>/status.json
as each stage changes; the screen polls it. STATUS_DESIGN.md describes the model and what resuming would need.

    stage      status                       summary (plain words)                           model step logged
    chart      A  reading the chart          "85 lines over 3 pages from linda_park.pdf"     -
    order      B  finding the order          "Linda Park · laser ablation … (36478) · …"     detect_order
    guideline  C  reading the guideline      "Florida Blue: 5 sections, 42 codes" (cached)   narrow_guideline
    section    E-G code gate, section        "Code 36478 is covered; section: Great or …"    -
    checklist  H  building the checklist     "12 requirements under “Great or …”" (cached)   criteria_guideline
    read       I  reading the chart          "9 of 9 requirements answered"                  judge_chart
    verify     J  checking quotes and dates  "Every quote found; 6 dates verified"           -
    decide     K/L deciding                  the result's one sentence                       -

Stage status: waiting · running · done · needs_person · failed · skipped. A gate is a stage that ended
`needs_person`, with `gate` saying what kind, what is needed, the options, and the action that resumes
(today: the existing re-check endpoint). A stage that raised is `failed` with the error; stages after it stay
`waiting` (not run) and the whole check is `failed` until retried.

Check state: running · paused · done · needs_person · failed. `paused` is a check that stopped at the
`confirm_pathways` gate (pipeline.run(pause_at_pathways=True)) and waits for a person: `resume` says where it
continues; `Recorder.from_doc` restores the recorder and `answer` records who confirmed what before pipeline.resume
runs the remaining stages under the same run_id.
"""
from __future__ import annotations

import json
import os
import re
import statistics
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from . import llm, log, store

logger = log.get("status")

STAGES: list[tuple[str, str, str]] = [            # id, label on screen, letter in pipeline.py
    ("chart", "Reading the case", "A"),
    ("order", "Finding the order", "B"),
    ("guideline", "Reading the guideline for this order", "C"),
    ("section", "Checking the code and choosing the indication", "E-G"),
    ("checklist", "Building the requirement checklist", "H"),
    ("record", "Reading the record", "A2"),
    ("read", "Reading the case against it", "I"),
    ("verify", "Checking every quote and date", "J"),
    ("decide", "Deciding", "K-L"),
]
STAGE_IDS = [s[0] for s in STAGES]

# gate kinds; `blocking` = the pipeline could not go on without a person (resume would restart from the stage)
GATES = {
    "confirm_code": {"blocking": False, "title": "Confirm the code"},
    "pick_code": {"blocking": True, "title": "Which code is this check for?"},     # one code, one pathway (app/onecode.py)
    "which_section": {"blocking": True, "title": "Which indication of the guideline?"},
    "confirm_pathways": {"blocking": True, "title": "Confirm the indication of the guideline"},
    "guideline_problems": {"blocking": False, "title": "The guideline could not be read cleanly"},
    "checklist_problems": {"blocking": False, "title": "The checklist could not be fully built"},
    "review": {"blocking": False, "title": "A person decides what happens next"},
}


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class Stage:
    """One stage's record. Attribute writes land in the dict the status file holds."""

    def __init__(self, rec: dict):
        self.rec = rec

    @property
    def summary(self) -> str:
        return self.rec.get("summary") or ""

    @summary.setter
    def summary(self, s: str) -> None:
        self.rec["summary"] = s

    @property
    def cached(self) -> bool:
        return bool(self.rec.get("cached"))

    @cached.setter
    def cached(self, v: bool) -> None:
        self.rec["cached"] = bool(v)

    @property
    def doing(self) -> str:
        return self.rec.get("doing") or ""

    @doing.setter
    def doing(self, s: str) -> None:
        """One short line of what the step is at right now ("12 conditions so far"); the heartbeat saves it."""
        self.rec["doing"] = s

    def gate(self, kind: str, needs: str, options: Optional[list[str]] = None, action: Optional[dict] = None,
             blocking: Optional[bool] = None) -> None:
        """The stage ends 'needs a person'. `action` names what resumes it, e.g. {"recheck": {"field": "target"}}."""
        meta = GATES.get(kind, {})
        self.rec["status"] = "needs_person"
        self.rec["gate"] = {"kind": kind, "title": meta.get("title", kind), "needs": needs, "options": options or [],
                            "action": action, "blocking": meta.get("blocking", False) if blocking is None else blocking}


class Recorder:
    """Records a check's stages and writes status.json after every change. `persist=False` keeps it in memory."""

    def __init__(self, chart_id: str, guideline_id: Optional[str], filename: str = "chart.pdf",
                 override: Optional[dict] = None, source: str = "api", persist: bool = True):
        self.chart_id = chart_id
        self.persist = persist
        self.doc: dict[str, Any] = {
            "chart_id": chart_id, "guideline_id": guideline_id, "filename": filename, "source": source,
            "override": override, "run_id": None, "state": "running", "started_at": now(), "ended_at": None,
            "current": None, "error": None,
            "stages": [{"id": i, "label": l, "steps": letter, "status": "waiting", "started_at": None,
                        "ended_at": None, "summary": "", "cached": False, "logs": [], "gate": None, "error": None}
                       for i, l, letter in STAGES],
            "resume": None,      # later: {"stage": id, "with": {...}} — see STATUS_DESIGN.md
            "pid": os.getpid(),  # the process running the check (interrupted(): a dead holder means a restart)
        }
        self.steps: dict[str, str] = {}
        self.save()

    @classmethod
    def from_doc(cls, doc: dict, persist: bool = True) -> "Recorder":
        """A recorder over a loaded status.json: same run_id and stage records; the model step each stage links is
        rebuilt from its `logs` (data/runs/<run>/<step>[-n].json), so a resumed stage keeps listing its run logs."""
        self = cls.__new__(cls)
        self.chart_id = doc["chart_id"]
        self.persist = persist
        self.doc = doc
        self.steps = {}
        for s in doc.get("stages", []):
            for lg in s.get("logs") or []:
                stem = Path(lg.get("file") or "").stem
                if stem:
                    self.steps[s["id"]] = re.sub(r"-\d+$", "", stem)
                    break
        return self

    # ------------------------------------------------------------ lookups

    def stage_rec(self, sid: str) -> dict:
        return next(s for s in self.doc["stages"] if s["id"] == sid)

    @property
    def state(self) -> str:
        return self.doc["state"]

    def set_run(self, run_id: str) -> None:
        self.doc["run_id"] = run_id
        self.save()

    # ------------------------------------------------------------ the hook pipeline.run uses

    @contextmanager
    def stage(self, sid: str, step: Optional[str] = None) -> Iterator[Stage]:
        """Marks the stage running; on a clean exit done (unless a gate was raised inside), on an exception failed
        (the error recorded, the exception re-raised). `step` is the model step whose run log the stage links."""
        rec = self.stage_rec(sid)
        rec.update(status="running", started_at=now(), error=None, elapsed_s=0, doing="", typical_s=typical(sid))
        self.doc["current"] = sid
        if step:
            self.steps[sid] = step
        self.save()
        t0 = time.time()
        beat = _Heartbeat(self, rec, t0)
        beat.start()
        try:
            yield Stage(rec)
        except Exception as e:
            beat.stop()
            rec.update(status="failed", ended_at=now(), elapsed_s=round(time.time() - t0, 1), doing="",
                       error=f"{type(e).__name__}: {e}", traceback=traceback.format_exc()[-4000:])
            rec["logs"] = self._logs(sid)
            self.doc.update(state="failed", ended_at=now(), error=rec["error"])
            self.save()
            raise
        beat.stop()
        rec["ended_at"] = now()
        rec["elapsed_s"] = round(time.time() - t0, 1)
        rec["doing"] = ""
        rec["logs"] = self._logs(sid)
        if rec["status"] == "running":
            rec["status"] = "done"
        remember(sid, rec["elapsed_s"], bool(rec.get("cached")))
        self.save()

    def skip(self, sid: str, why: str) -> None:
        rec = self.stage_rec(sid)
        if rec["status"] == "waiting":
            rec.update(status="skipped", summary=why, started_at=now(), ended_at=now())
            self.save()

    def pause(self, sid: str, resume: dict) -> None:
        """The check stops at `sid`'s gate and waits for a person. The stage keeps its `needs_person` status and its
        gate; `resume` says where the check continues ({"stage", "needs", "key", "endpoint"}). Later stages stay
        `waiting`."""
        rec = self.stage_rec(sid)
        rec["status"] = "needs_person"
        rec["ended_at"] = rec.get("ended_at") or now()
        self.doc.update(state="paused", resume=resume, ended_at=now(), current=None)
        self.save()

    def answer(self, sid: str, by: Optional[str], confirmed: list, suggested: list) -> None:
        """A person answered the gate on `sid`: the stage is done, the record says who chose what and when, and the
        check is running again from where `resume` pointed."""
        rec = self.stage_rec(sid)
        rec["status"] = "done"
        rec["answered_by"] = {"by": by, "at": now(), "confirmed": confirmed, "suggested": suggested}
        if rec.get("gate"):
            rec["gate"]["answered"] = True
        self.reopen()

    def reopen(self) -> None:
        """Back to running (after an answer, or a retry of a failed resume): the pause and the error are cleared."""
        self.doc.update(state="running", resume=None, resumed_at=now(), error=None, ended_at=None, pid=os.getpid())
        self.save()

    def close(self) -> None:
        """The check ran to its end: done, or needs a person if any stage ended that way."""
        gates = [s for s in self.doc["stages"] if s["status"] == "needs_person"]
        self.doc.update(state="needs_person" if gates else "done", ended_at=now(), current=None)
        self.save()

    # ------------------------------------------------------------ files

    def _logs(self, sid: str) -> list[dict]:
        step, run_id = self.steps.get(sid), self.doc.get("run_id")
        if not step or not run_id:
            return []
        d = Path(llm.RUNS) / run_id
        return [{"file": f"data/runs/{run_id}/{p.name}", "url": f"/api/runs/{run_id}/{p.stem}"}
                for p in sorted(d.glob(f"{step}*.json"))] if d.exists() else []

    def save(self) -> None:
        if self.persist:
            save_status(self.chart_id, self.doc)


# ---------------------------------------------------------------- the heartbeat and typical durations


HEARTBEAT_S = 3.0          # how often a running stage writes its elapsed_s (the page polls status.json)
TIMINGS = 20               # durations kept per (stage, cached) for typical_s


class _Heartbeat:
    """Writes `elapsed_s` (and the step's `doing` line) while a stage runs, so a 60 s model call is not silent."""

    def __init__(self, rec_owner: "Recorder", rec: dict, t0: float):
        self.owner, self.rec, self.t0 = rec_owner, rec, t0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not self.owner.persist:
            return
        self._thread = threading.Thread(target=self._run, name="status-heartbeat", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(HEARTBEAT_S):
            self.rec["elapsed_s"] = round(time.time() - self.t0, 1)
            try:
                self.owner.save()
            except Exception as e:           # never let the heartbeat take the check down
                logger.debug("heartbeat save: %s", e)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=HEARTBEAT_S + 1)


def timings_path() -> Path:
    """Beside the results dir, not in it: store.list_results scans results/*/."""
    return Path(store.RESULTS).parent / "stage_timings.json"


def _timings() -> dict:
    p = timings_path()
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return {}


def remember(sid: str, seconds: float, cached: bool) -> None:
    """Keeps the last TIMINGS durations per (stage, cached), for typical_s."""
    try:
        d = _timings()
        key = f"{sid}:{'cached' if cached else 'fresh'}"
        d[key] = (d.get(key) or [])[-(TIMINGS - 1):] + [round(seconds, 1)]
        p = timings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d))
    except Exception as e:
        logger.debug("timings: %s", e)


def typical(sid: str, cached: Optional[bool] = None) -> Optional[float]:
    """The median past duration of a stage ("usually about 50 s"); None until it has run."""
    d = _timings()
    keys = [f"{sid}:fresh", f"{sid}:cached"] if cached is None else [f"{sid}:{'cached' if cached else 'fresh'}"]
    xs = [x for k in keys for x in d.get(k) or []]
    return round(statistics.median(xs), 1) if xs else None


# ---------------------------------------------------------------- on disk


def status_path(chart_id: str) -> Path:
    return Path(store.RESULTS) / chart_id / "status.json"


def save_status(chart_id: str, doc: dict) -> None:
    p = status_path(chart_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(f".json.{os.getpid()}.{threading.get_ident()}.tmp")   # the heartbeat writes from its own thread
    tmp.write_text(json.dumps(doc, indent=2))
    os.replace(tmp, p)                 # readers never see a half-written file


def load_status(chart_id: str) -> Optional[dict]:
    p = status_path(chart_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:
        logger.warning("status of %s unreadable: %s", chart_id, e)
        return None


def list_pending() -> list[dict]:
    """Checks with a status but no result yet (running, failed before the end, or stopped at a blocking gate)."""
    out = []
    root = Path(store.RESULTS)
    for d in root.iterdir() if root.exists() else []:
        if (d / "status.json").exists() and not (d / "result.json").exists():
            st = load_status(d.name)
            if st:
                out.append(st)
    return sorted(out, key=lambda s: s.get("started_at") or "", reverse=True)


def summary_row(st: dict) -> dict:
    """What the queue shows for a check in progress or stopped: its state and current stage."""
    cur = next((s for s in st["stages"] if s["status"] == "running"), None)
    failed = next((s for s in st["stages"] if s["status"] == "failed"), None)
    gate = next((s for s in st["stages"] if s["status"] == "needs_person"), None)
    label = (failed or cur or gate or {}).get("label") or ""
    return {"state": st["state"], "stage": (failed or cur or gate or {}).get("id"), "stage_label": label,
            "error": st.get("error"), "started_at": st.get("started_at"), "run_id": st.get("run_id"),
            "order": st.get("order") or {}}


# ---------------------------------------------------------------- a check cut off by a restart


INTERRUPTED = "Interrupted: the server restarted while this check was running. Run it again."
STALE_S = 60.0       # a "running" record with no process id, untouched this long, is not being worked on


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def held_elsewhere(st: dict) -> bool:
    """True when a "running" record may be worked on by another live process (another server or a script on the
    same data/). This process's own checks are known from main.LIVE, not from here. A record without a process id
    (written before the id was kept) counts as held while the heartbeat still touches it."""
    pid = st.get("pid")
    if isinstance(pid, int):
        return pid != os.getpid() and _pid_alive(pid)
    try:
        return time.time() - status_path(st["chart_id"]).stat().st_mtime < STALE_S
    except (OSError, KeyError):
        return False


def mark_interrupted(chart_id: str, st: Optional[dict] = None) -> Optional[dict]:
    """A "running" check nobody is working on: the stage that was running is failed with INTERRUPTED, and so is the
    check, in the same shape a stage that raised leaves (so the page and retry treat it as any failure)."""
    st = st if st is not None else load_status(chart_id)
    if not st or st.get("state") != "running":
        return st
    t = now()
    for s in st.get("stages") or []:
        if s.get("status") == "running":
            s.update(status="failed", ended_at=t, doing="", error=INTERRUPTED)
    st.update(state="failed", error=INTERRUPTED, ended_at=t, current=None)
    save_status(chart_id, st)
    logger.info("check of chart %s was cut off by a restart; marked failed", chart_id)
    return st


def sweep_interrupted(is_live) -> list[str]:
    """At startup: every check left "running" that no live worker holds (`is_live(chart_id)` for this process,
    held_elsewhere for others) is marked interrupted. Returns the chart ids marked."""
    out = []
    root = Path(store.RESULTS)
    for d in sorted(root.iterdir()) if root.exists() else []:
        if not (d / "status.json").exists():
            continue
        st = load_status(d.name)
        if st and st.get("state") == "running" and not is_live(d.name) and not held_elsewhere(st):
            mark_interrupted(d.name, st)
            out.append(d.name)
    return out
