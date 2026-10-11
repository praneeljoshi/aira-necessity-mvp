"""Reduce-only runner for v1.2-code step H: one order per row, the row's key pathway given as the confirmed indication
(no step C call, no chart, no judge).

    OPENAI_API_KEY=... .venv/bin/python experiments/scripts/reduce_code.py --smoke            # the 3 smoke rows
    OPENAI_API_KEY=... .venv/bin/python experiments/scripts/reduce_code.py --jobs 6           # all rows
    .venv/bin/python experiments/scripts/reduce_code.py --report                               # summary of results.jsonl
    STEP_H=form ... (the no-sandbox form) · STEP_H=tools ... (host-side function tools, data/reduce_tools/)
    STEP_H=script ... (a declarative tree script the host parses and checks, data/reduce_script/)
    STEP_H=loose ... (v1.2-loose's step H, given the same inputs) · STEP_H=loose-loop ... (loose with an external
    fixpoint loop) · STEP_H=loose-next ... (loose with the review-load rules: sweep, admin, keep; data/reduce_loose/
    for all three)
    PITFALLS=1 ... (STEP_H=tools/script: the pitfall examples appended; own cache keys and results file)
    --only / --guidelines <slug, prefix or glob, comma-separated, e.g. 'florida-blue-02-33000-*'> · --rows 0,5,9 · --tag plan (results-<arm>-<STEP_H>[-pf]-plan.jsonl)

Orders: ../aira-necessity-guideline-reduce/experiments/swarm/orders_planned_procedure.jsonl. Arms:
  find (default)   the model gets the whole guideline and the order only, finds the indication(s) itself (any over
                   routes the order cannot separate) and quotes the sentence(s) it used; as the swarm did
  heading          --headings <jsonl {guideline, pathway, scenario_id?, heading}>: the indication's own heading or grant
                   sentence (checked to be printed) is sent alone as "the confirmed indication"; nothing else
The row's `pathway` (the key's name) is never sent to the model; it labels the result row for scoring. The order
carries the member's plan (row `plan`, default PLAN: the BCBSFL set is Florida Blue commercial); step H prunes
plan-only conditions on it, and it is part of the cache key.

Store: data/reduce_<code|tools|script>/<model>/ (cache files {narrowed, criteria} under criteria/, run logs under
runs/, results-<arm>-<STEP_H>[-pf].jsonl); the model is MODEL_STRUCTURE or llm.pick_models()'s pick, and is on every
row. Two models never share a cache or a results file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import pipeline  # noqa: E402
from app.checklist import keys
from app.checklist import reduce_next
from app.core import llm, log, store
from experiments.stepH import reduce_code, reduce_loop, reduce_script, reduce_tools
from app.checklist.criteria import find  # noqa: E402
from app.core.models import Code, Guideline, Narrowed, Pathway, Payer, Pick, Procedure, Range, Selection, Span  # noqa: E402
from app.ingest.pdf import pdf_to_text  # noqa: E402

BASE = ROOT / "data" / "reduce_code"


MODEL = ""


def base(model: str) -> Path:
    """data/reduce_<mode>/<model>/: each model keeps its own cache, run logs and results."""
    mode = os.environ.get("STEP_H")
    d = ROOT / "data" / ({"tools": "reduce_tools", "script": "reduce_script", "loose": "reduce_loose",
                          "loose-loop": "reduce_loose", "loose-next": "reduce_loose"}.get(mode) or "reduce_code")
    return d / model


def model_for(report: bool) -> str:
    """MODEL_STRUCTURE if set, else what llm.pick_models() picks; --report without a key: the only model run so far."""
    env = os.environ.get("MODEL_STRUCTURE")
    if env:
        return env
    if report and not os.environ.get("OPENAI_API_KEY"):
        root = base("x").parent
        runs = sorted(d.name for d in root.iterdir() if d.is_dir() and d.name not in
                      ("criteria", "runs", "guidelines", "charts", "results")) if root.exists() else []
        if len(runs) != 1:
            raise SystemExit(f"--report: set MODEL_STRUCTURE to one of {runs}")
        return runs[0]
    return llm.pick_models()[0]
ORDERS = ROOT.parent / "aira-necessity-guideline-reduce" / "experiments" / "swarm" / "orders_planned_procedure.jsonl"
ARM = "find"
TAG = ""        # --tag: in the results file name and in every cache key (a tagged run never reuses another's trees)
# the only order fields the model may see; pathway / scenario_id label the result row and never leave the host
ORDER_FIELDS = ("cpt", "cpt_line", "as_written", "diagnosis", "age", "sex")
PLAN = ("Florida Blue commercial (not a Federal Employee Program (FEP) member; not a State Account Organization (SAO) "
        "member)")
SMOKE = [("florida-blue-02-33000-31", "Great or Small Saphenous"), ("florida-blue-02-33000-34", "secondary prevention"),
         ("florida-blue-09-e0000-21", "replacement")]


def isolate():
    for name in ("GUIDELINES", "CRITERIA", "CHARTS", "RESULTS", "RUNS"):
        d = BASE / name.lower()
        d.mkdir(parents=True, exist_ok=True)
        setattr(store, name, d)
    llm.RUNS = BASE / "runs"


def source_pdf(slug: str) -> Path:
    tp = ROOT / "tests/fixtures/truth" / f"{slug}.json"
    src = json.loads(tp.read_text()).get("source_file")
    hits = list((ROOT / "mined-guidelines").rglob(src)) if src else []
    if not hits:
        raise FileNotFoundError(f"{slug}: source PDF {src!r} not found")
    return hits[0]


_GL: dict[str, tuple] = {}


FIXTURES = ROOT / "data" / "guidelines"          # the tracked fixture guidelines (bcbsfl-…, cms-…): read only


def guideline(slug: str):
    if slug not in _GL and not (ROOT / "tests/fixtures/truth" / f"{slug}.json").exists() \
            and (FIXTURES / slug / "spans.json").exists():
        d = json.loads((FIXTURES / slug / "spans.json").read_text())      # copied into this run's own store
        store.save_guideline_spans(slug, d["sha256"], d.get("filename") or "", [Span(**s) for s in d["spans"]])
        spans, sha, _ = store.load_guideline_spans(slug)
        _GL[slug] = (slug, spans, sha)
    if slug not in _GL:
        pdf = source_pdf(slug)
        sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
        gid = pipeline.add_guideline(pdf_to_text(pdf), pdf.name, sha, slug)
        spans, sha, _ = store.load_guideline_spans(gid)
        _GL[slug] = (gid, spans, sha)
    return _GL[slug]


HEADINGS: dict[tuple, str] = {}


def heading_for(row: dict) -> Optional[str]:
    return (HEADINGS.get(("sid", row["guideline"], row.get("scenario_id")))
            or HEADINGS.get((row["guideline"], row["pathway"])))


def given(row: dict, spans) -> tuple[list[Range], Optional[str]]:
    """Arm "heading" only: the indication's own heading or grant sentence (--headings), checked to be printed in the
    guideline. Only that text reaches the model, as "the confirmed indication". The find arm gives nothing.
    A heading joined with " ... " (a list's lead-in ... the item) is found part by part, each after the one before
    (the first printing after it wins); every part must be printed. One range per part; the model gets the parts as printed,
    joined with " ... "."""
    h = heading_for(row)
    parts = [x.strip() for x in (h or "").split(" ... ") if x.strip()]
    order = [s.id for s in spans]
    ranges, texts, after = [], [], None
    for part in parts:
        hit = find(part, spans, prefer=set(order[after:]) if after is not None else None)
        if not hit:
            return [], None
        ids = hit[0][0].split("-")
        if after is not None and order.index(ids[0]) < after:    # only printed before the lead-in: look no further
            return [], None
        ranges.append(Range(first=ids[0], last=ids[-1]))
        texts.append(hit[1])
        after = order.index(ids[-1])
    return (ranges, " ... ".join(texts)) if parts else ([], None)


def one(row: dict) -> dict:
    slug, pname = row["guideline"], row["pathway"]
    out = {"guideline": slug, "pathway": pname, "scenario_id": row.get("scenario_id"), "code": (row.get("cpt") or [""])[0]}
    try:
        gid, spans, sha = guideline(slug)
        proc = Procedure(cpt=row.get("cpt") or [], as_written=row.get("as_written"), target=row.get("target"),
                         diagnosis=row.get("diagnosis"), plan=row.get("plan", PLAN))
        where, heading = given(row, spans) if ARM == "heading" else ([], None)
        out["arm"] = ARM
        out["model"] = MODEL
        if ARM == "heading":
            out["located"] = bool(where)
        pid = "indication"
        code = out["code"]
        desc = (row.get("cpt_line") or code).split("—", 1)[-1].strip()
        payer = row.get("payer") or ("Medicare" if slug.startswith("cms-") else "Florida Blue")
        n = Narrowed(key="", guideline=Guideline(id=gid, sha256=sha, payer=Payer(name=payer)),
                     codes=[Code(code=code, tag="covered", description=desc)] if code else [],
                     pathways=[Pathway(id=pid, spans=where, codes=[code] if code else [])], chosen=[pid])
        key = (keys.cache_key(sha, proc) + f"-{ARM}-"
               + f"{row.get('scenario_id') or hashlib.sha1(pname.encode()).hexdigest()[:8]}" + (f"-{TAG}" if TAG else ""))
        n.key = key
        out["key"] = key
        sel = Selection(applies=True, pathways=[Pick(code=code, pathway=pid, how="code")], ranges=where)
        cached, cs = store.load_criteria(key)
        if cs is None:
            run_id = llm.new_run_id()
            out["run_id"] = run_id
            extra = {k: row.get(k) for k in ORDER_FIELDS if k not in ("cpt", "as_written", "diagnosis")}
            if ARM == "heading" and not heading:
                raise ValueError("heading arm: no heading for this row, or it is not printed in the guideline")
            if os.environ.get("STEP_H") == "loose-loop":
                cs = reduce_loop.build(spans, n, sel, key, run_id, proc, extra=extra, indication=heading)
            elif os.environ.get("STEP_H") == "loose-next":
                cs = reduce_next.build(spans, n, sel, key, run_id, proc, extra=extra, indication=heading)
            elif os.environ.get("STEP_H") == "loose":
                cs = reduce_loop.loose(spans, n, sel, key, run_id, proc, extra=extra, indication=heading)
            elif os.environ.get("STEP_H") == "script":
                cs = reduce_script.build(spans, n, sel, key, run_id, proc, extra=extra, indication=heading)
            elif os.environ.get("STEP_H") == "tools":
                cs = reduce_tools.build(spans, n, sel, key, run_id, proc, extra=extra, indication=heading)
            else:
                cs = reduce_code.build(spans, n, sel, key, run_id, proc, extra=extra, indication=heading)
            store.save_criteria(key, n, cs)
        out["indication_used"] = [ln[len("Indication used: "):] for ln in cs.notes.split("\n\n")
                                  if ln.startswith("Indication used: ")]
        out.update(status=cs.status, criteria=len(cs.criteria), problems=cs.problems, loopholes=len(cs.loopholes),
                   unanswerable=sum(not c.answerable for c in cs.criteria), removed=len(cs.removed_conditions))
        if cs.loop:
            out["loop"] = cs.loop
        step = {"tools": "criteria_tools", "script": "criteria_script", "loose": "criteria_loose",
                "loose-loop": "criteria_loop", "loose-next": "criteria_loose_next"}.get(os.environ.get("STEP_H")) or "criteria_code"
        cost = BASE / "runs" / (cs.run_id or "") / f"{step}-cost.json"
        if cs.run_id and cost.exists():
            out["spend"] = json.loads(cost.read_text())
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"[:300]
        out["trace"] = traceback.format_exc()[-800:]
    print(line(out), flush=True)
    return out


def line(r: dict) -> str:
    spend = sum(v.get("dollars", 0) for v in (r.get("spend") or {}).values())
    return (f"{r['guideline'][:26]:26} {r['pathway'][:40]:40} {r.get('status', 'ERROR'):12} "
            f"{r.get('criteria', '-'):>3} crit {r.get('loopholes', '-'):>2} holes "
            + (f"${spend:.2f}" if spend else "") + (f"  ERROR {r['error']}" if r.get("error") else ""))


def report(rows: list[dict]) -> None:
    from collections import Counter
    print(f"\n{len(rows)} rows: " + ", ".join(f"{k} {v}" for k, v in Counter(r.get("status", "error") for r in rows).items()))
    spend = [sum(v.get("dollars", 0) for v in (r.get("spend") or {}).values()) for r in rows if r.get("spend")]
    if spend:
        print(f"spend: ${sum(spend):.2f} total, ${sum(spend) / len(spend):.2f} per test ({len(spend)} with usage)")
    loops = [r["loop"] for r in rows if r.get("loop")]
    if loops:
        print(f"loop: {dict(Counter(x['reason'] for x in loops))}; rounds mean {sum(x['rounds'] for x in loops) / len(loops):.1f}, "
              f"max {max(x['rounds'] for x in loops)}; removals {sum(len(i['ids']) for x in loops for i in x['removed'])}")
    cells = [v.get("cells", 0) for r in rows for v in (r.get("spend") or {}).values()]
    if cells:
        print(f"code cells per order: mean {sum(cells) / len(cells):.1f}, max {max(cells)}")
    calls = [sum(v.get("calls", 0) for v in (r.get("spend") or {}).values()) for r in rows if r.get("spend")]
    if any(calls):
        print(f"tool calls per order: mean {sum(calls) / len(calls):.1f}, max {max(calls)}; capped "
              f"{sum(1 for r in rows for v in (r.get('spend') or {}).values() if v.get('capped'))}; "
              f"conditions removed by the agent: {sum(r.get('removed') or 0 for r in rows)}")
    probs = Counter(p.split(":")[0][:60] for r in rows for p in r.get("problems") or [])
    for k, v in probs.most_common(10):
        print(f"  {v:3}  {k}")
    print(f"heading not found: {sum(1 for r in rows if r.get('located') is False)}; "
          + ("no indication quoted: n/a (loose has no grant quote); " if os.environ.get("STEP_H", "").startswith("loose") else
             f"no indication quoted: {sum(1 for r in rows if not r.get('indication_used') and not r.get('error'))}; ")
          + 
          f"errors: {sum(1 for r in rows if r.get('error'))}")


def pick(rows: list[dict], only: str) -> list[dict]:
    """Rows whose guideline matches any of the comma-separated slugs, prefixes or globs; none matching is an error."""
    from fnmatch import fnmatch
    pats = [p.strip() for p in only.split(",") if p.strip()]
    out = [r for r in rows if any(fnmatch(r["guideline"], p) or r["guideline"].startswith(p) for p in pats)]
    if not out:
        raise SystemExit(f"--only {only!r}: no order matches")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orders", default=str(ORDERS))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", "--guidelines", dest="only", default="",
                    help="guideline slugs or globs, comma-separated (florida-blue-02-33000-*)")
    ap.add_argument("--rows", default="")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--tag", default="", help="results file suffix, e.g. plan -> results-<arm>-<STEP_H>-plan.jsonl")
    ap.add_argument("--headings", default="", help="arm 'heading': jsonl {guideline, pathway, heading}; default arm 'find'")
    a = ap.parse_args()
    global ARM, TAG
    TAG = a.tag
    if a.headings:
        ARM = "heading"
        for x in Path(a.headings).read_text().splitlines():
            if x.strip():
                d = json.loads(x)
                HEADINGS[(d["guideline"], d["pathway"])] = d["heading"]
                if d.get("scenario_id"):
                    HEADINGS[("sid", d["guideline"], d["scenario_id"])] = d["heading"]
    os.environ.setdefault("STEP_H", "code")
    global BASE, MODEL
    MODEL = model_for(a.report)
    BASE = base(MODEL)
    out = BASE / (f"results-{ARM}-{os.environ['STEP_H']}" + ("-pf" if os.environ.get("PITFALLS") == "1" else "")
                 + (f"-{a.tag}" if a.tag else "") + ".jsonl")
    if a.report:
        report([json.loads(x) for x in out.read_text().splitlines() if x.strip()])
        return
    rows = [json.loads(x) for x in Path(a.orders).read_text().splitlines() if x.strip()]
    if a.smoke:
        rows = [next(r for r in rows if r["guideline"] == g and k.lower() in r["pathway"].lower()) for g, k in SMOKE]
    if a.only:
        rows = pick(rows, a.only)
    if a.rows:
        rows = [rows[int(i)] for i in a.rows.split(",")]
    os.environ.setdefault("STEP_H", "code")
    log.setup()
    isolate()
    for slug in dict.fromkeys(r["guideline"] for r in rows):     # split once, before the threads
        guideline(slug)
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(one, rows))
    with out.open("a") as f:
        for r in res:
            f.write(json.dumps(r) + "\n")
    report(res)


if __name__ == "__main__":
    main()
