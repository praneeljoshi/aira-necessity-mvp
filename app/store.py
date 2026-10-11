"""JSON on disk.

    data/guidelines/<id>/spans.json        {id, sha256, filename, spans}            step A, at upload (code only)
    data/guidelines/<id>/guideline.json    Guideline + Code[] + Pathway[]           latest step C for this guideline
    data/criteria/<key>.json               {narrowed, criteria}                     steps C and H, per (sha256, cpt[], target)
    data/criteria/h-<key>.json             {narrowed: null, criteria}               step H alone, per confirmed pathways (resume)
    data/charts/<id>/{spans.json, order.json, sections.json}                        steps A, B and A2
    data/results/<order>/{selection.json, verdicts.json, result.json}               per check
    data/results/<order>/criteria.json     the exact CriteriaSet this case was judged with (pinned; readers prefer it)
    data/results/<order>/pathways.json     the section a person confirmed at the pause (suggested, confirmed, by, at)
    data/results/<order>/jreasons.json     step J's review reasons per criterion (K-L run again after a strike)
    data/results/<order>/strikes.json      requirements a person removed for this case (app/strikes.py)
    data/results/<order>/signoff.json      who signed the ready case off and when (app/signoff.py)
    data/results/<order>/asks.json         highlight-to-ask answers by (guideline sha, lines) (app/ask.py)
    data/results/<order>/probes.json       every ask: the lines, who, when, known / cached / asked (app/ask.py)
    data/results/<order>/additions.json    lines a person added to this case's checklist (app/additions.py)
    data/results/<order>/accepts.json      requirements a person accepted for this case (app/accepts.py)
    data/runs/<run>/                                                                every model exchange (llm.py)
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from .models import CriteriaSet, Narrowed, Order, Result, Selection, Span, Verdict

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
GUIDELINES = DATA / "guidelines"
CRITERIA = DATA / "criteria"
CHARTS = DATA / "charts"
RESULTS = DATA / "results"
RUNS = DATA / "runs"


def _dirs():
    for d in (GUIDELINES, CRITERIA, CHARTS, RESULTS, RUNS):
        d.mkdir(parents=True, exist_ok=True)


_dirs()


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=2))


# ---------------------------------------------------------------- guidelines


def save_guideline_spans(gid: str, sha: str, filename: str, spans: list[Span]) -> None:
    _write(GUIDELINES / gid / "spans.json",
           {"id": gid, "sha256": sha, "filename": filename, "spans": [s.model_dump() for s in spans]})


def load_guideline_spans(gid: str) -> tuple[list[Span], str, str]:
    d = json.loads((GUIDELINES / gid / "spans.json").read_text())
    return [Span(**s) for s in d["spans"]], d["sha256"], d.get("filename") or ""


def list_guidelines() -> list[dict]:
    out = []
    for p in sorted(GUIDELINES.glob("*/spans.json")):
        try:
            d = json.loads(p.read_text())
        except Exception as e:
            print(f"[store] skipping {p}: {e}")
            continue
        row = {"id": d["id"], "sha256": d["sha256"], "filename": d.get("filename"), "n_spans": len(d["spans"])}
        g = p.parent / "guideline.json"
        if g.exists():
            gj = json.loads(g.read_text())
            row.update(payer=gj["guideline"]["payer"]["name"], n_pathways=len(gj["pathways"]), n_codes=len(gj["codes"]))
        from . import titles                     # its own title and number, read from its first lines (display only)
        lab = titles.of(row["id"], row["sha256"], row.get("payer"))
        row.update(title_text=lab["title"], number=lab["number"], issuer=lab["issuer"])
        out.append(row)
    return out


def find_guideline_by_sha(sha: str) -> Optional[str]:
    for row in list_guidelines():
        if row["sha256"] == sha:
            return row["id"]
    return None


def guideline_exists(gid: str) -> bool:
    return (GUIDELINES / gid / "spans.json").exists()


def save_guideline_header(n: Narrowed) -> None:
    _write(GUIDELINES / n.guideline.id / "guideline.json",
           {"guideline": n.guideline.model_dump(), "codes": [c.model_dump() for c in n.codes],
            "pathways": [p.model_dump() for p in n.pathways]})


def delete_guideline(gid: str) -> None:
    d = GUIDELINES / gid
    if d.exists():
        shutil.rmtree(d)


# ---------------------------------------------------------------- criteria cache (steps C + H)


def criteria_cached(key: str) -> bool:
    return bool(key) and (CRITERIA / f"{key}.json").exists()


def load_criteria(key: str) -> tuple[Optional[Narrowed], Optional[CriteriaSet]]:
    p = CRITERIA / f"{key}.json"
    if not p.exists():
        return None, None
    d = json.loads(p.read_text())
    n = Narrowed.model_validate(d["narrowed"]) if d.get("narrowed") else None
    c = CriteriaSet.model_validate(d["criteria"]) if d.get("criteria") else None
    return n, c


def _replace(p: Path, obj) -> None:
    """Write through a temp file and rename, so a reader never sees half a file."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=2))
    os.replace(tmp, p)


@contextmanager
def _locked(key: str):
    """An exclusive lock per cache key (data/criteria/.locks/<key>.lock, flock): threads and processes alike, each
    open() is its own lock holder."""
    d = CRITERIA / ".locks"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{key}.lock", "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _pathways(c: CriteriaSet) -> set[str]:
    return {e.pathway for e in c.expressions}


def save_criteria(key: str, n: Narrowed, c: Optional[CriteriaSet]) -> tuple[Narrowed, Optional[CriteriaSet]]:
    """First writer wins, under the key's lock: a narrowed guideline already stored is kept, and so is a stored
    CriteriaSet that covers the new one's pathways (a second run that built its own keeps it for its own case,
    pinned in its results folder; the shared file is not overwritten). Returns what the cache holds afterwards."""
    with _locked(key):
        n0, c0 = load_criteria(key)
        n_keep = n0 or n
        c_keep = c0 if c0 is not None and (c is None or _pathways(c) <= _pathways(c0)) else c
        if n0 is None or c_keep is not c0:
            _replace(CRITERIA / f"{key}.json", {"narrowed": json.loads(n_keep.model_dump_json()),
                                               "criteria": json.loads(c_keep.model_dump_json()) if c_keep else None})
    return n_keep, c_keep


# H alone, cached by the pathways a person confirmed and the order's facts (pipeline.h_cache_key):
# data/criteria/h-<sha16>-<pids>-<ranges8>-o<order facts>-m<model>-v<prompts>.json
# as {"narrowed": null, "criteria": ...}; load_criteria reads these files too (narrowed None, criteria set).


def load_hcache(key: str) -> Optional[CriteriaSet]:
    return load_criteria(key)[1]


def save_hcache(key: str, c: CriteriaSet) -> CriteriaSet:
    """First writer wins, under the key's lock: when the key already holds a checklist it stays and is returned;
    the caller keeps its own set for its own case (pinned by save_case_criteria)."""
    with _locked(key):
        c0 = load_hcache(key)
        if c0 is not None and _pathways(c) <= _pathways(c0):
            return c0
        _replace(CRITERIA / f"{key}.json", {"narrowed": None, "criteria": json.loads(c.model_dump_json())})
    return c


BUILD_STALE_S = 900     # a building marker older than this is from a run that died; it is taken over


def claim_build(key: str) -> Optional[Path]:
    """Mark that this run is building the checklist for `key` (an O_EXCL create of data/criteria/.locks/<key>
    .building). None when another live run holds it."""
    d = CRITERIA / ".locks"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{key}.building"
    for _ in range(2):
        try:
            os.close(os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return p
        except FileExistsError:
            try:
                if time.time() - p.stat().st_mtime < BUILD_STALE_S:
                    return None
                p.unlink()
            except FileNotFoundError:
                pass
    return None


def release_build(p: Optional[Path]) -> None:
    if p is not None:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def wait_hcache(key: str, timeout: float, every: float = 0.5) -> Optional[CriteriaSet]:
    """The checklist another run is building for `key`, once it is written; None when the builder stops (its marker
    goes) without writing one, or after `timeout` seconds."""
    marker = CRITERIA / ".locks" / f"{key}.building"
    end = time.time() + timeout
    while True:
        c = load_hcache(key)
        if c is not None:
            return c
        if not marker.exists() or time.time() >= end:
            return None
        time.sleep(every)


# the checklist one case was judged with, pinned in its own folder: the shared cache may hold another run's ids


def save_case_criteria(chart_id: str, c: CriteriaSet) -> None:
    _replace(RESULTS / chart_id / "criteria.json", json.loads(c.model_dump_json()))


def load_case_criteria(chart_id: str) -> Optional[CriteriaSet]:
    p = RESULTS / chart_id / "criteria.json"
    return CriteriaSet.model_validate_json(p.read_text()) if p.exists() else None


def drop_case_criteria(chart_id: str) -> None:
    p = RESULTS / chart_id / "criteria.json"
    if p.exists():
        p.unlink()


# ---------------------------------------------------------------- charts and orders


def save_sections(chart_id: str, sha: str, out, model: Optional[str] = None, hint: Optional[str] = None) -> None:
    """`hint`: the clinic structure hint's id (app/hints.py, `<name>.<sha8>`) A2 was given; kept only when there was one."""
    _write(CHARTS / chart_id / "sections.json", {"sha": sha, "model": model, **({"hint": hint} if hint else {}),
                                                 **json.loads(out.model_dump_json())})


def load_sections(chart_id: str, sha: str, model: Optional[str] = None, hint: Optional[str] = None):
    """The chart's labelled sections, if they were made from these same lines (and, when `model` is given, by that
    model with the same clinic structure hint, or none: the A2 cache never serves another model's labels, nor labels
    made with another hint; a file from before the model was kept is a miss)."""
    from .sections import SOut
    p = CHARTS / chart_id / "sections.json"
    if not p.exists():
        return None
    d = json.loads(p.read_text())
    made_by, made_with = d.pop("model", None), d.pop("hint", None)
    if d.pop("sha", None) != sha or (model is not None and (made_by != model or made_with != hint)):
        return None
    return SOut.model_validate(d)


def save_chart(chart_id: str, filename: str, spans: list[Span], source: str = "api") -> None:
    _write(CHARTS / chart_id / "spans.json", {"id": chart_id, "filename": filename, "source": source,
                                              "spans": [s.model_dump() for s in spans]})


def load_chart_spans(chart_id: str) -> list[Span]:
    return [Span(**s) for s in json.loads((CHARTS / chart_id / "spans.json").read_text())["spans"]]


def chart_meta(chart_id: str) -> dict:
    p = CHARTS / chart_id / "spans.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    return {"filename": d.get("filename"), "source": d.get("source", "api")}


def save_order(o: Order) -> None:
    _write(CHARTS / o.chart_id / "order.json", o.model_dump_json(indent=2))


def load_order(chart_id: str) -> Optional[Order]:
    p = CHARTS / chart_id / "order.json"
    return Order.model_validate_json(p.read_text()) if p.exists() else None


# ---------------------------------------------------------------- results


def save_selection(chart_id: str, sel: Selection) -> None:
    """The section stage's output, written when a check pauses for a person to confirm the section (the same file
    save_result writes at the end)."""
    _write(RESULTS / chart_id / "selection.json", sel.model_dump_json(indent=2))


def save_confirmation(chart_id: str, doc: dict) -> None:
    """pathways.json: what the guideline reader suggested, what a person confirmed, by whom and when, and the H
    cache key the confirmed pathways were judged under."""
    _write(RESULTS / chart_id / "pathways.json", doc)


def load_confirmation(chart_id: str) -> Optional[dict]:
    p = RESULTS / chart_id / "pathways.json"
    return json.loads(p.read_text()) if p.exists() else None


def save_result(order_id: str, sel: Selection, verdicts: dict[str, Verdict], r: Result, guideline_id: str,
                override: Optional[dict] = None, jreasons: Optional[dict[str, list[str]]] = None) -> None:
    """`jreasons`: step J's review reasons per criterion, kept so K-L can run again over the stored verdicts (a
    strike, app/strikes.py) without re-running J."""
    d = RESULTS / order_id
    _write(d / "selection.json", sel.model_dump_json(indent=2))
    _write(d / "verdicts.json", json.dumps({k: v.model_dump(by_alias=True, exclude_none=True) for k, v in verdicts.items()}, indent=2))
    _write(d / "result.json", r.model_dump_json(indent=2))
    if jreasons is not None:
        _write(d / "jreasons.json", jreasons)
    meta = {"guideline_id": guideline_id, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "override": override}
    _write(d / "meta.json", meta)


def load_result(order_id: str) -> dict:
    d = RESULTS / order_id
    if not (d / "result.json").exists():
        raise FileNotFoundError(order_id)
    out = {p.stem: json.loads(p.read_text()) for p in d.glob("*.json")}
    return out


def list_results() -> list[dict]:
    rows = []
    for d in RESULTS.iterdir() if RESULTS.exists() else []:
        try:
            r = json.loads((d / "result.json").read_text())
            meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
        except Exception as e:
            print(f"[store] skipping result {d.name}: {e}")
            continue
        o = load_order(d.name)
        rows.append({"chart_id": d.name, "patient_name": o.patient_name if o else None,
                     "procedure_text": o.procedure.as_written if o else None, "cpt": o.procedure.cpt if o else [],
                     "payer": o.payer if o else None, "determination": r["determination"], "queue": r["queue"],
                     "needs_review": r["queue"] == "review", "run_id": r.get("run_id"),
                     "created_at": meta.get("created_at"), "guideline_id": r.get("guideline_id")})
    return sorted(rows, key=lambda x: x["created_at"] or "", reverse=True)


def wipe(everything: bool = False) -> dict[str, int]:
    """Forget checks (charts, results, runs). `everything=False` forgets only CLI checks. Guidelines and the
    criteria cache stay."""
    counts = {"charts": 0, "results": 0, "runs": 0}
    gone = [d.name for d in CHARTS.iterdir() if d.is_dir() and (everything or chart_meta(d.name).get("source") == "cli")]
    for cid in gone:
        r = RESULTS / cid
        if r.exists():
            try:
                rid = json.loads((r / "result.json").read_text()).get("run_id")
            except Exception:
                rid = None
            if rid and (RUNS / rid).exists():
                shutil.rmtree(RUNS / rid); counts["runs"] += 1
            shutil.rmtree(r); counts["results"] += 1
        shutil.rmtree(CHARTS / cid); counts["charts"] += 1
    if everything:
        for d in list(RUNS.iterdir()):
            if d.is_dir():
                shutil.rmtree(d); counts["runs"] += 1
    return counts


def load_run(run_id: str) -> dict:
    d = RUNS / run_id
    if not d.exists():
        raise FileNotFoundError(run_id)
    return {p.stem: json.loads(p.read_text()) for p in sorted(d.glob("*.json"))}
