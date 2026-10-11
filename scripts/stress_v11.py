"""v1.1 on the stress charts v1 was scored on (stress/score/v1/results.jsonl), first line: false Ready.

    .venv/bin/python scripts/stress_v11.py --jobs 6           # the 142 v1 cases
    .venv/bin/python scripts/stress_v11.py --limit 10         # a smoke run
    .venv/bin/python scripts/stress_v11.py --report           # re-print, no calls
    .venv/bin/python scripts/stress_v11.py --prefix multi. --jobs 6   # only the cases whose id starts with "multi."

Reads stress/out/<id>/{chart.pdf, expected.json} through the stress/ symlink; never writes there. Store:
data/stress_v11/ (gitignored); one shared criteria cache, as in the clinic.

Per case: determination (v1.1's CANT_CHECK counts for an expected NOT_APPLICABLE), queue, false Ready (queue ready
but the expected answer is not MET), section chosen vs the case's expected pathway, and the order key. Cases that
expect NOT_APPLICABLE because of the payer or plan are reported apart: v1.1 does not route on payer (the pair is
given), so they are out of scope by design.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import llm, log, pipeline, store  # noqa: E402
from app.pdf import pdf_to_text  # noqa: E402

STRESS = ROOT / "stress"
BASE = ROOT / "data" / "stress_v11"
OUT = BASE / "results.jsonl"
GID = {"bcbsfl-02-33000-31": "bcbsfl-02-33000-31", "centers-for-medicare-medicaid-services-ncd-20-8-3": "cms-ncd-20-8-3"}
PAYER_CLASSES = {"cms.commercial", "out.fl_wrong_payer", "out.fl_medicare_advantage"}
SECTION = {"great_small_saphenous": "great or small saphenous", "accessory_saphenous": "accessory saphenous",
           "tributaries": "tributar", "symptomatic_varicose_tributaries": "tributar", "perforator_veins": "perforator",
           "perforator": "perforator", "single_or_dual_chamber_permanent_cardiac_pacemakers": ""}


def isolate():
    for name in ("GUIDELINES", "CRITERIA", "CHARTS", "RESULTS", "RUNS"):
        d = BASE / name.lower()
        d.mkdir(parents=True, exist_ok=True)
        setattr(store, name, d)
    llm.RUNS = BASE / "runs"
    for gid in set(GID.values()):
        src = ROOT / "data" / "guidelines" / gid / "spans.json"
        dst = store.GUIDELINES / gid / "spans.json"
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text())


def case_ids(limit: int, prefix: str = "") -> list[str]:
    """The v1 scored set by default; with a prefix ("multi."), every generated case whose id starts with it."""
    if prefix:
        ids = sorted(d.name for d in (STRESS / "out").iterdir() if d.name.startswith(prefix) and (d / "expected.json").exists())
    else:
        ids = [json.loads(x)["id"] for x in (STRESS / "score/v1/results.jsonl").read_text().splitlines() if x.strip()]
        ids = [i for i in ids if (STRESS / "out" / i / "expected.json").exists()]
    return ids[:limit] if limit else ids


def section_ok(expected: str | None, used_names: list[str]) -> bool | None:
    if not expected:
        return None
    want = SECTION.get(expected, expected.replace("_", " "))
    return any(want in n.lower() for n in used_names) if want else bool(used_names)


def one(cid: str) -> dict:
    key = json.loads((STRESS / "out" / cid / "expected.json").read_text())
    exp = key["expected"]
    gid = GID[key["guideline_id"]]
    t0 = time.time()
    r = pipeline.run(pdf_to_text(STRESS / "out" / cid / "chart.pdf"), cid, gid, filename="chart.pdf", source="cli")
    o = store.load_order(cid)
    rec = store.load_result(cid)
    from app.select import pathway_name
    gspans, sha, _ = store.load_guideline_spans(gid)
    n, _ = store.load_criteria(pipeline.cache_key(sha, o.procedure))
    names = [pathway_name(n, p, gspans) for p in r.pathway_used] if n else []
    if "multi" in key:
        return score_multi(cid, key, r, o, n, gspans, time.time() - t0)
    acceptable = set(exp["acceptable"]) | ({"CANT_CHECK"} if "NOT_APPLICABLE" in exp["acceptable"] else set())
    return {"id": cid, "class": key["class"], "expected": exp["determination"], "got": r.determination, "queue": r.queue,
            "det_ok": r.determination in acceptable, "payer_case": key["class"] in PAYER_CLASSES,
            "false_ready": r.queue == "ready" and exp["determination"] != "MET",
            "missed_ready": exp["determination"] == "MET" and not exp.get("expect_review") and r.queue != "ready",
            "section_expected": exp.get("best_pathway"), "sections": names,
            "section_ok": section_ok(exp.get("best_pathway"), names) if r.determination in ("MET", "INSUFFICIENT", "NOT_MET") else None,
            "key_cpt_ok": sorted(o.procedure.cpt) == sorted(key["request"]["cpt"]) if key["request"].get("codes_written", True) else None,
            "target": o.procedure.target, "review_reasons": r.review_reasons, "run_id": r.run_id,
            "seconds": round(time.time() - t0, 1)}


def _section_word(section: str) -> str:
    low = section.lower()
    for w in ("concurrent", "great or small", "tributar", "perforator", "accessory"):
        if w in low:
            return w
    return low[:20]


def _matches(want: str, name: str) -> bool:
    low = name.lower()
    if want == "accessory":
        return "accessory" in low and "concurrent" not in low
    return want in low


def score_multi(cid, key, r, o, n, gspans, seconds) -> dict:
    """multi. cases: the combined determination, and per expected part whether a pathway with that section was
    judged for its code. Controls (determination null) pass when the order does not go to Ready."""
    from app.select import pathway_name
    m = key["multi"]
    want = m.get("determination")
    rec = store.load_result(cid)
    picks = [(p["code"], pathway_name(n, p["pathway"], gspans)) for p in rec["selection"].get("pathways", [])] if n else []
    parts = [(p["code"], _section_word(p.get("section") or p.get("pathway", ""))) for p in m.get("parts", [])]
    part_ok = [any(c == code and _matches(w, nm) for c, nm in picks) for code, w in parts]
    stopped = not r.pathway_used
    det_ok = (r.queue != "ready") if want is None else (r.determination == want)
    return {"id": cid, "class": key["class"], "multi": True, "expected": want or "stop/review", "got": r.determination,
            "queue": r.queue, "det_ok": det_ok, "payer_case": False, "stopped": stopped,
            "false_ready": r.queue == "ready" and want != "MET", "missed_ready": want == "MET" and r.queue != "ready",
            "parts": [f"{c}:{w}" for c, w in parts], "picks": [f"{c}:{nm[:50]}" for c, nm in picks],
            "parts_ok": part_ok, "all_parts_judged": all(part_ok) if parts and want is not None else None,
            "section_ok": None, "key_cpt_ok": sorted(set(o.procedure.cpt)) == sorted(set(m["codes_written"])),
            "codes_got": o.procedure.cpt, "target": o.procedure.target, "misses": [x.ask[:120] for x in r.misses],
            "ask_names_expected": m.get("ask_names"), "review_reasons": r.review_reasons, "run_id": r.run_id,
            "seconds": round(seconds, 1)}


def report_multi(rows: list[dict]) -> None:
    rows = [r for r in rows if r.get("multi")]
    if not rows:
        return
    print(f"\n# multi-pathway cases: {len(rows)}\n")
    print(f"**False Ready: {sum(r['false_ready'] for r in rows)}/{len(rows)}**")
    print(f"Determination right: {sum(r['det_ok'] for r in rows)}/{len(rows)}")
    judged = [r for r in rows if r["all_parts_judged"] is not None]
    print(f"Every expected part judged under its pathway: {sum(r['all_parts_judged'] for r in judged)}/{len(judged)}")
    print(f"Codes read right: {sum(r['key_cpt_ok'] for r in rows)}/{len(rows)}")
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r["class"], []).append(r)
    print(f"\n| class | expected | got | det ok | parts judged | picks |")
    print("|---|---|---|---|---|---|")
    for c, rs in sorted(by.items()):
        print(f"| {c} | {rs[0]['expected']} | {', '.join(x['got'] for x in rs)} | {sum(x['det_ok'] for x in rs)}/{len(rs)} | "
              f"{sum(bool(x['all_parts_judged']) for x in rs)}/{len(rs)} | {'; '.join(sorted(set(p for x in rs for p in x['picks'])))[:160]} |")


def report(rows: list[dict]) -> None:
    if rows and all(r.get("multi") for r in rows):
        report_multi(rows)
        return
    scope = [r for r in rows if not r["payer_case"]]
    print(f"\n# v1.1 stress: {len(rows)} cases ({len(rows) - len(scope)} payer-routing cases reported apart)\n")
    print(f"**False Ready: {sum(r['false_ready'] for r in scope)}/{len(scope)}**"
          + "".join(f"  ({r['id']}: expected {r['expected']})" for r in scope if r["false_ready"]))
    print(f"**Determination correct: {sum(r['det_ok'] for r in scope)}/{len(scope)}**")
    print(f"MET charts not sent to Ready: {sum(r['missed_ready'] for r in scope)}")
    sec = [r for r in scope if r["section_ok"] is not None]
    print(f"Section chosen right: {sum(r['section_ok'] for r in sec)}/{len(sec)} judged cases")
    print(f"Order codes right: {sum(bool(r['key_cpt_ok']) for r in scope if r['key_cpt_ok'] is not None)}/"
          f"{sum(1 for r in scope if r['key_cpt_ok'] is not None)}")
    conf = Counter((r["expected"], r["got"]) for r in scope)
    print("\nexpected -> got: " + ", ".join(f"{a}->{b} x{n}" for (a, b), n in sorted(conf.items())))
    print("\nWrong determinations:")
    for r in scope:
        if not r["det_ok"]:
            print(f"- {r['id']}: expected {r['expected']} got {r['got']} via {r['sections']} (target {r['target']!r})")
    pc = [r for r in rows if r["payer_case"]]
    if pc:
        print(f"\nPayer-routing cases (out of scope in v1.1): " + ", ".join(f"{r['id']} -> {r['got']}" for r in pc))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--prefix", default="", help='run every generated case whose id starts with this, e.g. "multi."')
    a = ap.parse_args()
    if a.report:
        report([json.loads(x) for x in OUT.read_text().splitlines() if x.strip()])
        return
    log.setup()
    isolate()
    ids = case_ids(a.limit, a.prefix)
    rows, lock = [], Lock()
    with ThreadPoolExecutor(a.jobs) as ex:
        futs = {ex.submit(one, i): i for i in ids}
        for f in as_completed(futs):
            try:
                row = f.result()
            except Exception as e:
                row = {"id": futs[f], "error": f"{type(e).__name__}: {e}"[:300]}
                print("ERROR", row, flush=True)
                continue
            with lock:
                rows.append(row)
                with OUT.open("a") as fh:
                    fh.write(json.dumps(row) + "\n")
                print(f"{row['id']:40} {row['expected']:14} {row['got']:14} {row['queue']:10} section {row['section_ok']}", flush=True)
    report(rows)


if __name__ == "__main__":
    main()
