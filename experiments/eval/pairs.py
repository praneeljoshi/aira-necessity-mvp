"""What tree_diff compares: (answer key pathway, generated tree) pairs, read from a runner's results, never written.

Two sources:

  results   experiments/scripts/reduce_code.py output: data/reduce_<mode>/<model>/results-<arm>-<STEP_H>[-tag].jsonl,
            one row per test {guideline, pathway, scenario_id, code, key, criteria, ...}, and the step-H output for the
            row's key in criteria/<key>.json beside it ({narrowed, criteria}). Duplicate rows (re-runs appended to the
            same file): the last one wins. A row with an error or no criteria is yielded with `gen` None ("no tree").
  v1.1      a v1.1 score store (<store>/results.jsonl + <store>/criteria/*.json), paired on v1.1's cache key
            (sha256 of the guideline PDF, code, target), as scripts/score_v11 wrote it.

Answer keys: tests/fixtures/truth/<guideline>.json, except the two repo fixtures the test sets name by their short
slugs (REPO_KEYS). A key's pathway is found by the row's scenario_id, then by its name.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
TRUTH = ROOT / "tests" / "fixtures" / "truth"
REPO_KEYS = {"bcbsfl-02-33000-31": ROOT / "tests" / "fixtures" / "bcbsfl-02-33000-31.json",
             "cms-ncd-20-8-3": ROOT / "tests" / "fixtures" / "centers-for-medicare-medicaid-services-ncd-20-8-3.json"}
MINED = [ROOT / "mined-guidelines", ROOT.parent / "aira-necessity-main" / "mined-guidelines"]


# ---------------------------------------------------------------- the answer-key schema
# The hand-built keys keep the v1.0 guideline shape (criteria + scenarios, each with a `requires` tree), which
# app.core.models.Guideline no longer has. Only the fields the scorer reads; the rest of the file is ignored.

class KeyCriterion(BaseModel):
    id: str
    text: str
    question: str
    threshold: Optional[dict[str, Any]] = None
    answerable: bool = True


class LeafNode(BaseModel):
    type: Literal["leaf"] = "leaf"
    criterion: str


class AllNode(BaseModel):
    type: Literal["all"] = "all"
    children: list["Node"]


class AnyNode(BaseModel):
    type: Literal["any"] = "any"
    children: list["Node"]


class NotNode(BaseModel):
    type: Literal["not"] = "not"
    child: "Node"


Node = Union[AllNode, AnyNode, NotNode, LeafNode]
AllNode.model_rebuild()
AnyNode.model_rebuild()
NotNode.model_rebuild()


class Scenario(BaseModel):
    id: str
    name: str
    requires: Node


class Key(BaseModel):
    id: str
    source_file: Optional[str] = None
    criteria: list[KeyCriterion]
    scenarios: list[Scenario]


def key_path(gid: str) -> Path:
    return REPO_KEYS.get(gid) or TRUTH / f"{gid}.json"


def load_key(gid: str) -> Key:
    return Key.model_validate_json(key_path(gid).read_text())


def scenario_of(key: Key, scenario_id: Optional[str], pathway: str) -> Optional[Scenario]:
    return next((s for s in key.scenarios if scenario_id and s.id == scenario_id), None) or \
        next((s for s in key.scenarios if s.name == pathway), None)


def slug(s: str, n: int = 60) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:n].strip("-")


def pair_name(gid: str, code: str, pathway: str) -> str:
    """The alignment file's name; the hash suffix because truncated names can collide."""
    return f"{gid}__{code}__{slug(pathway, 50)}-{hashlib.sha1(pathway.encode()).hexdigest()[:6]}"


# ---------------------------------------------------------------- the current runner's results

def result_rows(results: Path) -> list[dict]:
    last = {}
    for line in results.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            last[(r["guideline"], r.get("scenario_id") or r["pathway"])] = r
    return list(last.values())


def results_pairs(results: Path, only: set[str] = frozenset()) -> list[dict]:
    """One record per test in a results-*.jsonl: {arm, name, guideline, pathway, code, scenario_id, key, scenario,
    gen (the criteria/<key>.json dict, or None), row}. arm = the results file's stem."""
    out = []
    for r in result_rows(results):
        if only and r["guideline"] not in only:
            continue
        key = load_key(r["guideline"])
        sc = scenario_of(key, r.get("scenario_id"), r["pathway"])
        if sc is None:
            raise ValueError(f"{results.name}: no pathway {r.get('scenario_id') or r['pathway']!r} in the key "
                             f"{key_path(r['guideline']).name}")
        cf = results.parent / "criteria" / f"{r.get('key')}.json"
        d = json.loads(cf.read_text()) if r.get("key") and cf.exists() else None
        ok = bool(not r.get("error") and r.get("criteria") and d and (d.get("criteria") or {}).get("criteria"))
        out.append({"arm": results.stem, "name": pair_name(r["guideline"], r.get("code") or "", sc.name),
                    "guideline": r["guideline"], "pathway": sc.name, "code": r.get("code") or "",
                    "scenario_id": sc.id, "key": key, "scenario": sc, "gen": d if ok else None, "row": r})
    return out


# ---------------------------------------------------------------- v1.1 score stores

_SIDE = re.compile(r"\b(left|right|bilateral|both|lt|rt|l|r)\b\.?", re.I)


def v11_key(sha: str, code: str, target: str) -> str:
    return f"{sha[:16]}-{code or 'nocpt'}-{slug(_SIDE.sub(' ', target), 50) or 'any'}"


def v11_pairs(stores: list[Path], only: set[str] = frozenset()) -> list[dict]:
    """Latest scored row per (guideline, pathway, code) across the stores, with the cached C/H output that produced
    it (found by the guideline PDF's sha256 under mined-guidelines/). arm 'v1.1'."""
    cache, latest = {}, {}
    for s in stores:
        for f in (s / "criteria").glob("*.json"):
            d = json.loads(f.read_text())
            if d.get("criteria"):
                cache[d["narrowed"]["key"]] = d
        for line in (s / "results.jsonl").read_text().splitlines():
            r = json.loads(line)
            if "tree" in r and (not only or r["guideline"] in only):
                latest[(r["guideline"], r["pathway"], r["code"])] = r
    pdfs = {p.name: p for m in MINED if m.exists() for p in m.rglob("*.pdf")}
    out = []
    for (gid, P, code), r in sorted(latest.items()):
        key = load_key(gid)
        sc = next((s for s in key.scenarios if s.name == P), None)
        pdf = pdfs.get(key.source_file or "")
        if not sc or not pdf:
            continue
        d = cache.get(v11_key(hashlib.sha256(pdf.read_bytes()).hexdigest(), code, P))
        if not d:
            continue
        out.append({"arm": "v1.1", "name": pair_name(gid, code, P), "guideline": gid, "pathway": P, "code": code,
                    "scenario_id": sc.id, "key": key, "scenario": sc, "gen": d, "row": r})
    return out
