"""Record reading (A2 sections + the judge) on the sample charts, end to end, into an isolated store.

    OPENAI_API_KEY=... MODEL_STRUCTURE=gpt-6-sol MODEL_JUDGE=gpt-6-sol EFFORT_SECTIONS=medium EFFORT_JUDGE=medium \\
        .venv/bin/python experiments/scripts/record_eval.py --tag sol6-medium [--runs 2] [--only elena_ruiz_chart,maria_delgado_chart]
    .venv/bin/python experiments/scripts/record_eval.py --tag sol6-medium --report

Each chart is checked against its guideline `--runs` times (determinism). Per run: determination, queue, confidence,
misses, review reasons, every verdict (status, confidence, cited spans, dates), the A2 label counts, and per-step
tokens / seconds from the run logs. Expected outcomes come from the samples' documented outcomes and
data/samples/synthetic/elena_ruiz.expected.json. Store: data/record_eval/<tag>/ (guidelines copied read-only from
data/guidelines; nothing in data/ proper is touched). Prices: each step at its model's list price (llm.PRICES), cached input at the cached rate.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import pipeline  # noqa: E402
from app.core import llm, log, store
from app.core.models import Span  # noqa: E402
from app.ingest.pdf import pdf_to_text  # noqa: E402

SAMPLES = ROOT / "data" / "samples"
FIXTURES = ROOT / "data" / "guidelines"
BASE = ROOT / "data" / "record_eval"

# chart -> (guideline, what the docs / the generator say should come out)
CHARTS = {
    "maria_delgado_chart": ("bcbsfl-02-33000-31", {"determination": "MET", "misses": 0, "months": 4.1}),
    "linda_park_chart": ("bcbsfl-02-33000-31", {"determination": "INSUFFICIENT", "misses": 1, "miss_about": "compression"}),
    "james_okafor_chart": ("bcbsfl-02-33000-31", {"determination": "NOT_COVERED", "judge_called": False}),
    "robert_mitchell_chart_final": ("cms-ncd-20-8-3", {"determination": "NOT_MET"}),
    "elena_ruiz_chart": ("bcbsfl-02-33000-31", {"determination": "MET", "misses": 0, "compression_start": "09/17/2024",
                                                "varicosity_mm": "5", "duplex_date": "08/25/2026",
                                                "wrong": {"compression_start": "02/13/2024", "varicosity_mm": "2",
                                                          "duplex_date": "11/14/2023"}}),
}


def isolate(tag: str) -> Path:
    base = BASE / tag
    for name in ("GUIDELINES", "CRITERIA", "CHARTS", "RESULTS", "RUNS"):
        d = base / name.lower()
        d.mkdir(parents=True, exist_ok=True)
        setattr(store, name, d)
    llm.RUNS = base / "runs"
    for gid in {g for g, _ in CHARTS.values()}:
        src = FIXTURES / gid / "spans.json"
        if not (store.GUIDELINES / gid / "spans.json").exists():
            d = json.loads(src.read_text())
            store.save_guideline_spans(gid, d["sha256"], d.get("filename") or "", [Span(**s) for s in d["spans"]])
    return base


def pdf_for(stem: str) -> Path:
    hits = list(SAMPLES.rglob(f"{stem}.pdf"))
    if not hits:
        raise FileNotFoundError(stem)
    return hits[0]


def usage(run_id: str) -> dict:
    """Per step: calls, prompt / completion tokens, seconds, list-price dollars."""
    out: dict[str, dict] = {}
    for f in sorted((llm.RUNS / run_id).glob("*.json")):
        try:
            j = json.loads(f.read_text())
        except ValueError:
            continue
        s, u = j.get("step"), j.get("usage") or {}
        if not s or "seconds" not in j:
            continue
        o = out.setdefault(s, {"calls": 0, "in": 0, "cached": 0, "out": 0, "seconds": 0.0, "model": j.get("model")})
        o["calls"] += 1
        o["in"] += u.get("prompt_tokens") or 0
        o["cached"] += ((u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        o["out"] += u.get("completion_tokens") or 0
        o["seconds"] += j["seconds"]
    for o in out.values():
        o["dollars"] = round(llm.dollars({"input_tokens": o["in"], "cached_tokens": o["cached"], "output_tokens": o["out"]},
                                         o["model"]), 3)
    return out


def labels(chart_id: str) -> dict:
    p = store.CHARTS / chart_id / "sections.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    c: Counter = Counter()
    for s in d.get("sections", []):
        n = 0
        for r in s.get("spans", []):
            a, b = int(r["first"][1:]), int(r["last"][1:])
            n += b - a + 1
        c[s["label"]] += n
    return dict(c)


def verdicts(chart_id: str) -> list[dict]:
    p = store.RESULTS / chart_id / "verdicts.json"
    if not p.exists():
        return []
    vs = list(json.loads(p.read_text()).values())
    return [{k: v.get(k) for k in ("criterion", "status", "confidence", "for", "against", "measurements", "dates")}
            for v in vs]


def one(stem: str, k: int) -> dict:
    gid, want = CHARTS[stem]
    chart_id = f"{stem}-{k}"
    row = {"chart": stem, "run": k, "guideline": gid, "expected": want}
    t0 = time.time()
    try:
        p = pdf_for(stem)
        r = pipeline.run(pdf_to_text(p), chart_id, gid, filename=p.name, source="cli")
        row.update(determination=r.determination, queue=r.queue, confidence=round(r.confidence, 3),
                   pathway=r.pathway_used, misses=[m.model_dump() for m in r.misses], review=r.review_reasons,
                   checklist=[{"status": c.status, "text": c.text[:120], "quotes": [{"span": q.span, "date": q.date}
                                                                                  for q in c.quotes]}
                              for c in r.checklist],
                   run_id=r.run_id, verdicts=verdicts(chart_id), labels=labels(chart_id),
                   usage=usage(r.run_id or ""), wall=round(time.time() - t0, 1))
        row["grade"] = grade(row)
    except Exception as e:
        row["error"] = f"{type(e).__name__}: {e}"[:300]
        row["trace"] = traceback.format_exc()[-1200:]
    print(line(row), flush=True)
    return row


def grade(row: dict) -> dict:
    want = row["expected"]
    g = {"determination": row.get("determination") == want["determination"]}
    if "misses" in want:
        g["misses"] = len(row.get("misses") or []) == want["misses"]
    if "judge_called" in want:
        g["no_judge"] = "judge_chart" not in (row.get("usage") or {})
    dates = " ".join(q.get("date") or "" for c in row.get("checklist") or [] for q in c["quotes"])
    dates += " " + " ".join(d.get("date") or "" for v in row.get("verdicts") or [] for d in v.get("dates") or [])
    values = [str(m.get("value")) for v in row.get("verdicts") or [] for m in v.get("measurements") or []]
    for key, hay in (("compression_start", dates), ("duplex_date", dates)):
        if key in want:
            g[key] = want[key] in hay and want["wrong"][key] not in hay
    if "varicosity_mm" in want:      # the value the judge used: the right one present, the distractor not alone
        g["varicosity_mm"] = want["varicosity_mm"] in values
    return g


def line(r: dict) -> str:
    u = r.get("usage") or {}
    tot = sum(v["dollars"] for v in u.values())
    toks = sum(v["in"] for v in u.values())
    g = r.get("grade") or {}
    ok = f"{sum(g.values())}/{len(g)} ok" if g else ""
    return (f"{r['chart'][:28]:28} run{r['run']} {r.get('determination', 'ERROR'):13} {r.get('queue', ''):8} "
            f"conf {r.get('confidence', 0):.2f} misses {len(r.get('misses') or []):2} {ok:8} "
            f"{toks // 1000:4}k tok ${tot:.2f} {r.get('wall', 0):5.0f}s"
            + (f"  ERROR {r['error']}" if r.get("error") else ""))


def report(rows: list[dict]) -> None:
    print()
    for r in rows:
        print(line(r))
    by = {}
    for r in rows:
        by.setdefault(r["chart"], []).append(r)
    print("\ndeterminism: " + ", ".join(f"{c} {'same' if len({x.get('determination') for x in xs}) == 1 else 'DIFFERS'}"
                                       for c, xs in by.items()))
    steps: dict[str, dict] = {}
    for r in rows:
        for s, v in (r.get("usage") or {}).items():
            o = steps.setdefault(s, {"n": 0, "in": 0, "out": 0, "seconds": 0.0, "dollars": 0.0})
            o["n"] += v["calls"]
            for k in ("in", "out", "seconds", "dollars"):
                o[k] += v[k]
    print("per step (all runs): " + "; ".join(
        f"{s}: {o['n']} calls, {o['in'] // 1000}k in / {o['out'] // 1000}k out, {o['seconds']:.0f}s, ${o['dollars']:.2f}"
        for s, o in sorted(steps.items())))
    for r in rows:
        if r.get("labels"):
            print(f"A2 {r['chart']} run{r['run']}: {r['labels']}")
    bad = [(r["chart"], r["run"], [k for k, v in (r.get("grade") or {}).items() if not v]) for r in rows
           if r.get("grade") and not all(r["grade"].values())]
    print("failed checks: " + (", ".join(f"{c} run{k}: {', '.join(ks)}" for c, k, ks in bad) if bad else "none"))
    print(f"errors: {sum(1 for r in rows if r.get('error'))}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--only", default="")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    base = isolate(a.tag)
    out = base / "results.jsonl"
    if a.report:
        report([json.loads(x) for x in out.read_text().splitlines() if x.strip()])
        return
    log.setup()
    stems = [s for s in CHARTS if not a.only or s in a.only.split(",")]
    meta = {"tag": a.tag, "models": {"structure": os.environ.get("MODEL_STRUCTURE"), "judge": os.environ.get("MODEL_JUDGE")},
            "effort": {"sections": os.environ.get("EFFORT_SECTIONS", "low"), "judge": os.environ.get("EFFORT_JUDGE", "low")},
            "step_h": os.environ.get("STEP_H", "loose"), "started": time.strftime("%Y-%m-%d %H:%M")}
    (base / "meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta))
    rows = [one(s, k) for s in stems for k in range(1, a.runs + 1)]
    with out.open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    report(rows)
    print(f"\nwritten: {out}")


if __name__ == "__main__":
    main()
