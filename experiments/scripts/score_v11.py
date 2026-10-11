"""Score v1.1 steps C and H against the hand-built truth trees, per truth pathway. Model calls: C and H, cached.

    .venv/bin/python experiments/scripts/score_v11.py                     # the 13 Pass-2 guidelines, up to 3 pathways each
    .venv/bin/python experiments/scripts/score_v11.py --per 0             # every pathway
    .venv/bin/python experiments/scripts/score_v11.py --only florida-blue-02-99221-15 --per 0
    .venv/bin/python experiments/scripts/score_v11.py --report            # re-print from the last results, no calls

For each sampled truth pathway P: the order from --orders (written the way a chart's PLANNED PROCEDURE block words it:
procedure, CPT, diagnosis with ICD-10; never P's name). Without --orders, the order is P's first covered code alone,
so choice is by code (shared codes end as "asked"). P's name is never sent to the model.

  chosen   right / unconfirmed (read it by hand) by where P's criteria sit in the guideline (experiments/scripts/chosen_check.py: the picked lines hold
           P's criteria and no sibling's) · several (more than one picked) · asked (none picked; a person is asked) ·
           stopped (the code gate stopped it). Names are never compared.
  tree     P alone vs the picked section's expression, scorer v2 sampling: wrong-of-generated-passes (false
           approvals) and missed-of-truth-passes
  v1       for context, the v1 whole-document tree on the same code against every truth pathway for that code
           (the Pass-2 unit), from the guideline-reduce branch's generated files

Store: data/score_v11/ (gitignored); the criteria cache there makes re-runs free.
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app import pipeline  # noqa: E402
from app.core import llm, log, store
from app.core.models import Order, Pick, Procedure  # noqa: E402
from app.ingest.pdf import pdf_to_text  # noqa: E402
from app.understand.select import pathway_name, select  # noqa: E402
from app.ingest.spans import table, text_of  # noqa: E402
from experiments.scripts.legacy.models import Guideline as LGuideline  # noqa: E402
from experiments.scripts.chosen_check import check as chosen_check  # noqa: E402
from experiments.scripts.legacy.score_guideline import governs, score  # noqa: E402

BASE = ROOT / "data" / "score_v12"     # v1.2: new C and H; the v1.1 cache is in data/score_v11
OUT = BASE / "results.jsonl"
V1_DIR = ROOT.parent / "aira-necessity-guideline-reduce" / "data" / "guidelines" / "generated"
PASS2 = ["cigna-companies-0480", "evolent-evolent-cg-1764", "excellus-2-01-07",
         "fallon-health-implantable-cardioverter-defibrillators", "florida-blue-01-95828-01", "florida-blue-02-12000-11",
         "florida-blue-02-12000-18", "florida-blue-02-99221-15", "florida-blue-02-33000-31", "humana-la-cli-038-001",
         "kaiser-redundant-skin-surgery", "pennsylvania-health-and-wellness-pa-cp-mp-119", "unitedhealthcare-2026t0447ss",
         "ncd-20-8-3"]
V1_ALIAS = {"kaiser-redundant-skin-surgery": "kaiser-foundation-health-plan-of-the-mid-plastic-and-reconstructive-surgery",
            "excellus-2-01-07": "not-stated-in-document-2-01-07", "florida-blue-02-33000-31": "bcbsf-02-33000-31",
            "ncd-20-8-3": "centers-for-medicare-medicaid-services-national-coverage-determination-ncd-20-8-3"}


def isolate():
    for name in ("GUIDELINES", "CRITERIA", "CHARTS", "RESULTS", "RUNS"):
        d = BASE / name.lower()
        d.mkdir(parents=True, exist_ok=True)
        setattr(store, name, d)
    llm.RUNS = BASE / "runs"


def truth_files(only: list[str]) -> list[tuple[str, Path, Path]]:
    out = []
    for slug in only or PASS2:
        if slug == "ncd-20-8-3":
            out.append((slug, ROOT / "tests/fixtures/centers-for-medicare-medicaid-services-ncd-20-8-3.json",
                        ROOT / "data/samples/cms_ncd_20_8_3_pacemakers.pdf"))
            continue
        tp = ROOT / "tests/fixtures/truth" / f"{slug}.json"
        src = json.loads(tp.read_text()).get("source_file")
        hits = list((ROOT / "mined-guidelines").rglob(src)) if src else []
        if not hits:
            print(f"{slug}: source PDF {src!r} not found; skipped")
            continue
        out.append((slug, tp, hits[0]))
    return out


def sample(scenarios, per: int):
    if per <= 0 or len(scenarios) <= per:
        return list(scenarios)
    step = len(scenarios) / per
    return [scenarios[int(i * step)] for i in range(per)]


def to_legacy(e) -> dict:
    if isinstance(e, str):
        return {"type": "leaf", "criterion": e}
    (op, arg), = e.items()
    if op == "not":
        return {"type": "not", "child": to_legacy(arg)}
    if op == "at_least":
        kids = [to_legacy(x) for x in arg["of"]]
        combos = list(itertools.combinations(kids, arg["k"]))[:200]
        return {"type": "any", "children": [{"type": "all", "children": list(c)} for c in combos]}
    return {"type": op, "children": [to_legacy(x) for x in arg]}


def score_one(t: LGuideline, P, code: str, gen: dict) -> dict:
    """P alone vs the generated pathway(s), through the v2 scorer (temp files: it reads paths)."""
    tt = t.model_copy(deep=True)
    tt.scenarios = [P.model_copy(update={"applies_to_cpt": [code] if code else []})]
    tt.scope.cpt = {code: "covered"} if code else {}
    tt.status = "ok"
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "t.json", Path(d) / "g.json"
        a.write_text(tt.model_dump_json())
        b.write_text(json.dumps(gen))
        r = score(a, b)
    return {"criteria": {k: r["criteria"][k] for k in ("truth", "gen", "recall", "precision")}, **r["behaviour"]}


def v1_context(slug: str, t: LGuideline, code: str):
    p = V1_DIR / f"{V1_ALIAS.get(slug, slug)}.json"
    if not code or not p.exists():
        return None
    tt = t.model_copy(deep=True)
    tt.scope.cpt = {code: "covered"}
    tt.scenarios = [s for s in t.scenarios if governs(t, s, code)]
    g = json.loads(p.read_text())
    g["scope"]["cpt"] = {code: g["scope"]["cpt"].get(code, "covered")}
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "t.json", Path(d) / "g.json"
        a.write_text(tt.model_dump_json())
        b.write_text(json.dumps(g))
        r = score(a, b)
    return {k: r["behaviour"][k] for k in ("wrong_of_gen_passes", "missed_of_truth_passes")} | {"truth_paths": len(tt.scenarios)}


ORDERS: dict[tuple[str, str], dict] = {}


def load_orders(path: str) -> None:
    for x in Path(path).read_text().splitlines():
        if x.strip():
            d = json.loads(x)
            ORDERS[(d["guideline"], d["pathway"])] = d


def order_for(slug: str, P, code: str) -> Order:
    d = ORDERS.get((slug, P.name))
    if d:
        return Order(id=f"score-{slug}", procedure=Procedure(cpt=d.get("cpt") or ([code] if code else []),
                     as_written=d.get("as_written"), target=d.get("target"), diagnosis=d.get("diagnosis")))
    return Order(id=f"score-{slug}", procedure=Procedure(cpt=[code] if code else []))


def run(slug: str, tp: Path, pdf: Path, per: int) -> list[dict]:
    t = LGuideline.model_validate_json(tp.read_text())
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    gid = pipeline.add_guideline(pdf_to_text(pdf), pdf.name, sha, slug)
    gspans, sha, _ = store.load_guideline_spans(gid)
    gt = table(gspans)
    rows = []
    pool = [P for P in t.scenarios if (slug, P.name) in ORDERS] if ORDERS else t.scenarios
    for P in sample(pool, per):
        code = next((c for c in P.applies_to_cpt if t.scope.cpt.get(c) == "covered"), "")
        order = order_for(slug, P, code)
        run_id = llm.new_run_id()
        row = {"guideline": slug, "pathway": P.name, "code": code, "truth_pathways": len(t.scenarios)}
        try:
            n, cs, key = pipeline.narrowed_for(gid, gspans, sha, order, run_id)
            sel = select(n, order, gspans)
            picks = list(dict.fromkeys(p.pathway for p in sel.pathways))
            names = [pathway_name(n, x, gspans) for x in picks]
            row.update(key=key, gen_pathways=len(n.pathways), c_chosen=picks, picked=names, narrow_problems=len(n.problems))
            stopped = [g for g in sel.code_gate if g.outcome != "judge"]
            if not sel.applies or stopped:
                row["chosen"] = "stopped"
                row["stop"] = sel.reason[:200]
            elif not picks:
                row["chosen"] = "asked"
            elif len(picks) > 1:
                row["chosen"] = "several"
            else:
                row["chosen"], why = chosen_check(json.loads(tp.read_text()), gspans, n.model_dump(), code, P.name)
                if why:
                    row["chosen_why"] = why
            # the human gate: the right indication is confirmed, whether or not the model picked it
            key_json = json.loads(tp.read_text())
            confirmed = picks[0] if row["chosen"] == "right" else next(
                (x.id for x in n.pathways
                 if chosen_check(key_json, gspans, {**n.model_dump(), "chosen": [x.id]}, code, P.name)[0] == "right"), None)
            row["confirmed"] = "model" if row["chosen"] == "right" else ("corrected" if confirmed else "none")
            row["confirmed_id"] = confirmed
            if confirmed and sel.applies and not stopped:
                csel = sel.model_copy(update={"pathways": [Pick(code=code or "", pathway=confirmed, how="person")]})
                cs = pipeline.criteria_for(gspans, n, csel, cs, key, run_id, order.procedure)
                expr = {e.pathway: e.expr for e in cs.expressions}
                gen = {"id": "gen", "payer": "x", "title": "x", "scope": {"cpt": {code: "covered"} if code else {}},
                       "criteria": [{"id": c.id, "text": (c.quote or text_of(c.refs, gt)) + " " + c.question, "question": c.question,
                                     "answerable": c.answerable} for c in cs.criteria],
                       "scenarios": [{"id": confirmed, "name": confirmed, "applies_to_cpt": [code] if code else [],
                                      "requires": to_legacy(expr[confirmed])}] if confirmed in expr else [],
                       "status": "ok"}
                row["criteria_status"] = cs.status
                row["loopholes"] = len(cs.loopholes)
                if gen["scenarios"]:
                    row["tree"] = score_one(t, P, code, gen)
            row["v1"] = v1_context(slug, t, code)
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"[:300]
        print(line(row), flush=True)
        rows.append(row)
    return rows


def _f(x):
    return " n/a" if x is None else f"{x:.2f}"


def line(r: dict) -> str:
    tr, v1 = r.get("tree") or {}, r.get("v1") or {}
    return (f"{r['guideline'][:28]:28} {r['pathway'][:38]:38} {r['code'] or '-':6} {r.get('chosen', 'ERR'):8} {r.get('confirmed', '-'):9} "
            f"wrong {_f(tr.get('wrong_of_gen_passes'))} missed {_f(tr.get('missed_of_truth_passes'))}  "
            f"| v1 code wrong {_f(v1.get('wrong_of_gen_passes'))}" + (f"  ERROR {r['error']}" if r.get("error") else ""))


def report(rows: list[dict]) -> None:
    from collections import Counter
    print("\n== chosen ==")
    c = Counter(r.get("chosen", "error") for r in rows)
    print("  " + "  ".join(f"{k}: {v}" for k, v in c.most_common()) + f"   (of {len(rows)})")
    print("\n== per guideline: mean over pathways scored ==")
    print(f"  {'guideline':48} {'n':>3} {'right':>5} {'wrong':>6} {'missed':>7}   {'v1 wrong (per code)':>20}")
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["guideline"], []).append(r)
    mean = lambda xs: (sum(xs) / len(xs)) if xs else None
    for g, rs in by.items():
        w = [r["tree"]["wrong_of_gen_passes"] for r in rs if r.get("tree") and r["tree"]["wrong_of_gen_passes"] is not None]
        m = [r["tree"]["missed_of_truth_passes"] for r in rs if r.get("tree") and r["tree"]["missed_of_truth_passes"] is not None]
        v = [r["v1"]["wrong_of_gen_passes"] for r in rs if r.get("v1") and r["v1"]["wrong_of_gen_passes"] is not None]
        right = sum(r.get("chosen") == "right" for r in rs)
        print(f"  {g[:48]:48} {len(rs):>3} {right:>5} {_f(mean(w)):>6} {_f(mean(m)):>7}   {_f(mean(v)):>20}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--per", type=int, default=3)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--orders", default="", help="jsonl: {guideline, pathway, cpt, as_written, target, diagnosis}")
    ap.add_argument("--out", default="", help="results file (default data/score_v11/results.jsonl)")
    a = ap.parse_args()
    if a.report:
        report([json.loads(x) for x in (Path(a.out) if a.out else OUT).read_text().splitlines() if x.strip()])
        return
    out = Path(a.out) if a.out else OUT
    if a.orders:
        load_orders(a.orders)
    log.setup()
    isolate()
    rows = []
    only = [x for x in a.only.split(",") if x] or (sorted({g for g, _ in ORDERS}) if ORDERS else [])
    for slug, tp, pdf in truth_files(only):
        rows += run(slug, tp, pdf, a.per)
    BASE.mkdir(parents=True, exist_ok=True)
    with out.open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    report(rows)


if __name__ == "__main__":
    main()
