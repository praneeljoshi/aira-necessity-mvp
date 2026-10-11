"""The app with the test stub in place of the model, for looking at the status screen without a key.

    .venv/bin/python -m scripts.dev_server --port 8010 [--delay 4] [--data DIR] [--no-target] [--fail judge_chart] [--two-codes]
                                          [--more-guidelines] [--unanswerable] [--seed-health N]

Serves app.main on the port with `llm.call` replaced by tests/fake.Stub (the FL varicose guideline and the Delgado
chart; upload data/samples/synthetic/maria_delgado_chart.pdf against the FL guideline). Every model step sleeps
`--delay` seconds so the stages can be watched. The store points at `--data` (default: a scratch folder under
/tmp) seeded with the FL guideline, so nothing under data/ is touched. `--no-target` makes the order come back
without a target (the "which section" gate); `--fail STEP` makes that step raise (the error gate); `--two-codes`
makes the order come back with cpt 36475 + 36478 (the Delgado chart only prints 36475, so the second code is put
back after `detect_order`'s "written in the chart" filter: two codes, two picks at the pathway gate); `--unanswerable`
adds two requirements no chart can show to the checklist (the section's "meets the definition of medical necessity"
and the reimbursement line, step C's every-request part): "Confirm outside the chart". `--seed-health N` writes N
synthetic cases on the FL guideline into the scratch store before serving (scripts/seed_health.py), so the policy
health page (/experimental/health/bcbsfl-02-33000-31) has numbers; the page marks them as demo data.
"""
from __future__ import annotations

import argparse
import hashlib
import tempfile
import time
from pathlib import Path

import uvicorn

from app import llm, pipeline, store
from app.pdf import pdf_to_text
from app.spans import split_chart, split_guideline
from tests.fake import Stub

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "data" / "samples"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--data", default=None)
    ap.add_argument("--no-target", action="store_true")
    ap.add_argument("--fail", default=None, help="model step that raises: detect_order, narrow_guideline, criteria_guideline, judge_chart")
    ap.add_argument("--two-codes", action="store_true", help="the order comes back with cpt 36475 and 36478")
    ap.add_argument("--unanswerable", action="store_true",
                    help="the checklist also has two requirements no chart can show (confirm outside the chart)")
    ap.add_argument("--more-guidelines", action="store_true", help="also put the CMS NCD 20.8.3 PDF on file (read-only copy of the sample)")
    ap.add_argument("--gap", default="", help="comma list of requirement ids the chart does NOT document (e.g. size,adl): they show as 'Add to the ask'")
    ap.add_argument("--seed-health", type=int, default=0, metavar="N",
                    help="write N synthetic cases (strikes, asks, sections, sign-offs, feedback) for the policy health page")
    a = ap.parse_args()

    data = Path(a.data) if a.data else Path(tempfile.mkdtemp(prefix="necessity-dev-"))
    for name in ("GUIDELINES", "CRITERIA", "CHARTS", "RESULTS", "RUNS"):
        d = data / name.lower()
        d.mkdir(parents=True, exist_ok=True)
        setattr(store, name, d)
    llm.RUNS = data / "runs"
    from app import feedback
    feedback.FEEDBACK = data / "feedback"       # feedback goes to the scratch folder too, never data/
    llm.pick_models = lambda ids=None: ("stub", "stub")

    gtext = pdf_to_text(SAMPLES / "fl_varicose_veins_guideline.pdf")
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    pipeline.add_guideline(gtext, "fl_varicose_veins_guideline.pdf", sha, "bcbsfl-02-33000-31")
    if a.more_guidelines:         # a second guideline on file: "None of these" then offers it (the stub never reads it)
        ncd = SAMPLES / "cms_ncd_20_8_3_pacemakers.pdf"
        pipeline.add_guideline(pdf_to_text(ncd), ncd.name, hashlib.sha256(ncd.read_bytes()).hexdigest(), "cms-ncd-20-8-3")
    g = split_guideline(gtext)
    r = split_chart(pdf_to_text(SAMPLES / "synthetic" / "maria_delgado_chart.pdf"))
    order_kw: dict = {}
    if a.no_target:
        order_kw["target"] = None
    if a.two_codes:
        order_kw["cpt"] = ("36475", "36478")
        real_detect = pipeline.detect_order

        def detect_two(rspans, chart_id, run_id):
            o = real_detect(rspans, chart_id, run_id)
            o.procedure.cpt = ["36475", "36478"]
            return o
        pipeline.detect_order = detect_two
    stub_kw: dict = {"order": order_kw} if order_kw else {}
    if a.gap:
        stub_kw["verdicts"] = {k: {"status": "INSUFFICIENT", "for": []} for k in a.gap.split(",") if k}
    stub = Stub(g, r, **stub_kw, unanswerable=a.unanswerable)
    if a.seed_health:
        from scripts.seed_health import seed
        t0 = time.time()
        ids = seed(a.seed_health, g, r, "bcbsfl-02-33000-31")
        print(f"seeded {len(ids)} demo cases in {time.time() - t0:.1f}s: /experimental/health/bcbsfl-02-33000-31", flush=True)

    def call(run_id, step, prompt, schema, **kw):
        time.sleep(a.delay)
        if a.fail == step:
            raise RuntimeError(f"{step}: the model answered with something that failed validation twice (simulated)")
        out = stub(run_id, step, prompt, schema, **kw)
        llm._log(run_id, step, {"step": step, "model": "stub", "parsed": out.model_dump()})
        return out
    llm.call = call

    print(f"stub server on http://127.0.0.1:{a.port}  data={data}  delay={a.delay}s  no_target={a.no_target}  fail={a.fail}  two_codes={a.two_codes}", flush=True)
    from app import main as app_main
    uvicorn.run(app_main.app, host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
