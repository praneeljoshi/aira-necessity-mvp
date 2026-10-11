"""Demo data for the policy health page: N synthetic cases on the FL varicose guideline, written by the real review
flow (the app's own endpoints through a TestClient, the stub in place of the model) into the dev server's scratch
store, so every case opens like any other. Called by `scripts/dev_server.py --seed-health N`; never touches data/.

Each case varies, from one seeded random source (the same N gives the same cases): the patient's name, the vein the
order names (so the guideline reader suggests a different section, or none), the section a person confirms (now and
then not the suggested one), gaps in the chart (compression dates, the vein size, daily living), the two
requirements no chart can show, strikes with reason chips and notes, accepts, "Add to the ask", "Confirmed outside
the chart", sign-offs and line feedback. Times are spread over the last six weeks. Every case gets
`data/results/<id>/demo.json` so the page can say its numbers are demo data.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path

from app import feedback, llm, main, store
from app.health import DEMO_FILE
from tests.conftest import rng, sid
from tests.fake import P, Stub

CHART = Path(__file__).resolve().parents[1] / "data" / "samples" / "synthetic" / "maria_delgado_chart.pdf"

NAMES = ["Maria Delgado", "Robert Chen", "Linda Park", "James Okafor", "Aisha Rahman", "Thomas Byrne", "Grace Liu",
         "Daniel Moreno", "Helen Novak", "Samuel Adeyemi", "Patricia Walsh", "Victor Huang", "Rosa Jimenez",
         "Kevin O'Neill", "Fatima Haddad", "George Petrov", "Nora Lindqvist", "Ruth Abramson", "Carlos Vega",
         "Irene Kowalski", "Owen Price", "Mei Tanaka", "Laura Bianchi", "Peter Mensah", "Joan Fitzgerald"]
STAFF = ["Dana Ruiz", "Lee Chen", "Priya Nair", "Sam Okoro"]
TARGETS = [("left great saphenous vein", 66), ("right accessory saphenous vein", 12), (None, 12), ("perforator veins", 10)]
CONFIRM = {"gsv": [("gsv", 88), ("accessory", 8), ("perforator", 4)], "accessory": [("gsv", 60), ("accessory", 40)],
           None: [("gsv", 82), ("accessory", 18)], "perforator": [("gsv", 70), ("perforator", 30)]}
SUGGEST = {"left great saphenous vein": "gsv", "right accessory saphenous vein": "accessory", "perforator veins": "perforator", None: None}

OP_NOTES = ["Claim-time line; nothing to show before the procedure.", "Operative report goes with the claim, not the request.",
            "Reimbursement wording, not a criterion."]
CEAP_NOTES = ["The class sits on the reflux line; the quote runs the two together.", "Quote pulls in the reflux sentence too."]
OTHER_SECTION = ["This line is from the saphenous section, not the one confirmed.", "Belongs with the great saphenous criteria."]
COMPRESSION_GAP = ["Ulcer present; the policy's ulcer route does not ask for a compression trial.",
                   "Bleeding episode documented; compression trial not needed on that route."]


def _pick(r: random.Random, opts):
    return r.choices([o for o, _ in opts], weights=[w for _, w in opts])[0]


def _shift(obj, delta: float):
    """Every timestamp field ("at", "*_at") moved by delta seconds."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if (k == "at" or k.endswith("_at")) and isinstance(v, str) and len(v) >= 19 and v[4] == "-":
                try:
                    obj[k] = _fmt(time.mktime(time.strptime(v[:19], "%Y-%m-%dT%H:%M:%S")) + delta)
                except ValueError:
                    pass
            else:
                _shift(v, delta)
    elif isinstance(obj, list):
        for x in obj:
            _shift(x, delta)
    return obj


def _fmt(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t))


def _rewrite(p: Path, fn) -> None:
    if p.exists():
        p.write_text(json.dumps(fn(json.loads(p.read_text())), indent=2))


def _backdate(cid: str, t0: float, r: random.Random, slow: bool) -> None:
    """Move the case to t0: status, meta, the confirmation; strikes and accepts a few minutes in (an ask a little
    later when the case waits on the surgeon); line feedback with them."""
    d = store.RESULTS / cid
    st = json.loads((d / "status.json").read_text())
    delta = t0 - time.mktime(time.strptime(st["started_at"][:19], "%Y-%m-%dT%H:%M:%S"))
    for name in ("status.json", "meta.json", "pathways.json", "nofit.json", "signoff.json"):
        _rewrite(d / name, lambda o: _shift(o, delta))
    step = [t0 + r.uniform(4, 15) * 60]

    def later(o, key):
        for x in o.get(key) or []:
            step[0] += r.uniform(0.4, 3) * 60 * (6 if slow and x.get("mark") in ("missing", "contradicted") else 1)
            x["at"] = _fmt(step[0])
        return o
    _rewrite(d / "strikes.json", lambda o: later(o, "strikes"))
    _rewrite(d / "accepts.json", lambda o: later(o, "accepts"))
    files = [Path(feedback.FEEDBACK) / f"{cid}.jsonl"] + list((Path(feedback.FEEDBACK) / "by-guideline").glob("*/*.jsonl"))
    for f in files:
        if not f.exists():
            continue
        out = []
        for ln in f.read_text().splitlines():
            try:
                x = json.loads(ln)
            except ValueError:
                out.append(ln)
                continue
            if x.get("chart_id") == cid and x.get("at"):
                x["at"] = _fmt(t0 + r.uniform(10, 40) * 60)
            out.append(json.dumps(x))
        f.write_text("\n".join(out) + "\n")


def seed(n: int, g, rs, gid: str, seed_: int = 17) -> list[str]:
    """Write n cases; returns their chart ids, oldest first."""
    from fastapi.testclient import TestClient

    r = random.Random(seed_)
    was_bg, was_call = main.BACKGROUND, llm.call
    main.BACKGROUND = False
    client = TestClient(main.app)
    p = P(g)
    lines = {"size": [sid(g, "The varicosities are at least 3 millimeters", p)],
             "lead": [sid(g, "There is documentation of one or more of the following", p)],
             "sym": [rng(g, "4. Persistent pain", "improved the symptoms.", p)],
             "cosmetic": [rng(g, "Treatment of great or small saphenous veins by surgery, endovenous", "considered cosmetic and does not meet", p)]}
    flags = [("logic_wrong", "sym", "Reads as if the compression trial is needed even when an ulcer is documented.", None, 5),
             ("logic_wrong", "lead", "Unclear whether item 4 needs all three of its parts or any one.", None, 3),
             ("edit", "size", "Say how and where the size is measured.",
              "The varicosities measure at least 3 millimeters in diameter on duplex ultrasound AND", 4),
             ("should_be_requirement", "cosmetic", "The cosmetic limitation decides requests; it should be checked like a requirement.", None, 3)]
    shown = sid(rs, "Unchanged varicosities medial left thigh")     # a chart line the other sections' stub items cite
    now = time.time()
    span = 42 * 86400
    ids: list[str] = []
    try:
        for i in range(n):
            name = NAMES[i % len(NAMES)]
            target = _pick(r, TARGETS)
            # the checklist is cached per section, so the two requirements no chart can show are on every case
            gaps: dict = {k: {"status": "MET", "for": [shown]} for k in ("accessory_1", "accessory_2", "perforator_1", "perforator_2")}
            if r.random() < 0.26:
                gaps["compression"] = {"status": "INSUFFICIENT", "for": []}
            if r.random() < 0.10:
                gaps["size"] = {"status": "INSUFFICIENT", "for": []}
            if r.random() < 0.06:
                gaps["adl"] = {"status": "INSUFFICIENT", "for": []}
            if r.random() < 0.08:
                gaps["accessory_2"] = gaps["perforator_2"] = {"status": "INSUFFICIENT", "for": []}
            kw: dict = {"unanswerable": True, "verdicts": gaps}
            kw["order"] = {"target": target}
            stub = Stub(g, rs, **kw)

            def call(run_id, step, prompt, schema, _stub=stub, _name=name, **k):
                out = _stub(run_id, step, prompt, schema, **k)
                if step == "detect_order":
                    out.patient_name = _name
                llm._log(run_id, step, {"step": step, "model": "stub", "parsed": out.model_dump()})
                return out
            llm.call = call
            with open(CHART, "rb") as f:
                res = client.post("/api/review/charts", files={"file": (f"{name.split()[-1].lower()}_chart.pdf", f, "application/pdf")},
                                  data={"guideline_id": gid})
            cid = res.json()["chart_id"]
            ids.append(cid)
            t0 = now - span + span * (i + r.uniform(0.1, 0.9)) / max(n, 1)
            who = r.choice(STAFF)
            last = i >= n - 2 and n >= 6                  # the newest two wait at the section, unconfirmed
            if last:
                _backdate(cid, t0, r, False)
                (store.RESULTS / cid / DEMO_FILE).write_text(json.dumps({"seeded": True, "by": "scripts/dev_server.py --seed-health"}))
                continue
            pick = _pick(r, CONFIRM[SUGGEST[target]])
            d = client.post(f"/api/review/{cid}/pathways", json={"picks": [{"code": "36475", "pathway": pick}], "by": who}).json()

            def reqs():
                return {x["criterion"]: x for x in d["case"]["requirements"]} if d.get("case") else {}

            def strike(crit, code, note=""):
                nonlocal d
                x = client.post(f"/api/review/{cid}/strikes", json={"criterion": crit, "code": code, "reason": note, "by": who})
                if x.status_code == 201:
                    d = x.json()

            q = reqs()
            if "op_report" in q and r.random() < 0.68:
                strike("op_report", "billing" if r.random() < 0.7 else "paperwork", r.choice(OP_NOTES) if r.random() < 0.4 else "")
            if "necessity" in q and r.random() < 0.06:
                strike("necessity", "paperwork")
            if "ceap" in q and r.random() < 0.14:
                strike("ceap", "wrong_quote", r.choice(CEAP_NOTES) if r.random() < 0.7 else "")
            if "hem" in q and r.random() < 0.12:
                strike("hem", "not_for_case")
            if "thromb" in q and r.random() < 0.07:
                strike("thromb", "not_for_case")
            if "compression" in q and q["compression"]["bad"] and r.random() < 0.18:
                strike("compression", "not_for_case", r.choice(COMPRESSION_GAP))
            for k in ("accessory_2", "perforator_2"):
                if k in q and r.random() < 0.45:
                    strike(k, "other_section", r.choice(OTHER_SECTION) if r.random() < 0.5 else "")
            for k in ("accessory_1", "perforator_1"):
                if k in q and r.random() < 0.2:
                    strike(k, "other", "Heading text, not something to document.")
            # accept what is documented; the gaps go to the ask most of the time; confirm the rest outside the chart
            thorough = r.random() < 0.9
            for x in list(reqs().values()):
                if not x["counted"] or x["mark"] == "struck" or x["accepted"] or x.get("in_ask"):
                    continue
                if not x["proof"] and r.random() > 0.8:
                    continue
                if x["mark"] == "confirm" and r.random() > 0.88:
                    continue
                if not thorough and r.random() < 0.5:
                    continue
                y = client.post(f"/api/review/{cid}/accepts", json={"criterion": x["criterion"], "by": who})
                if y.status_code == 201:
                    d = y.json()
            for kind, where, text, prop, weight in flags:
                if r.random() < weight / 40:
                    feedback.add(cid, kind, "guideline", text, lines[where], by=r.choice(STAFF), proposal=prop)
            slow = bool(d.get("case") and d["case"]["progress"].get("in_ask"))
            _backdate(cid, t0, r, slow)
            if d.get("signoff", {}).get("can_sign") and r.random() < 0.85:
                if client.post(f"/api/review/{cid}/signoff", json={"by": who}).status_code == 201:
                    hours = r.lognormvariate(1.1, 0.9) * (3 if "necessity" in q else 1)
                    _rewrite(store.RESULTS / cid / "signoff.json", lambda o: dict(o, at=_fmt(min(now - 300, t0 + hours * 3600))))
            (store.RESULTS / cid / DEMO_FILE).write_text(json.dumps({"seeded": True, "by": "scripts/dev_server.py --seed-health"}))
    finally:
        main.BACKGROUND, llm.call = was_bg, was_call
    return ids
