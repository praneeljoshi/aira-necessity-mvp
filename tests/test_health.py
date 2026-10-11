"""Policy health (app/review/health.py, GET /api/health/{id}, /experimental/health/{id}): counts across the cases on one guideline
from what coordinators stored, read-only, and a note to the payer that names no patient. Offline: the stub model,
the store and the feedback folder in tmp_path (the review-flow fixture). Never touches data/."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.core import store
from app.review import feedback, health
from tests.conftest import accept_all, sid
from tests.test_strikes import reqs, world  # noqa: F401  (the review-flow fixture)


def _snapshot(root) -> dict:
    return {str(p): hashlib.sha1(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def test_an_empty_guideline_and_an_unknown_one(world):
    c = world.client
    assert c.get("/api/health/nope").status_code == 404
    d = c.get(f"/api/health/{world.guideline}").json()
    assert d["headline"]["cases"] == 0 and d["removed"] == [] and d["missing"] == [] and d["demo"] is None
    assert d["guideline"]["number"].endswith("02-33000-31")
    page = c.get(f"/experimental/health/{world.guideline}")
    assert page.status_code == 200 and "/static/health.js?v=" in page.text and "no-cache" in page.headers["cache-control"]
    # the old address moves there; the experimental index lists it; the review page and / do not link it
    old = c.get(f"/review/health/{world.guideline}", follow_redirects=False)
    assert old.status_code in (301, 302, 307, 308) and old.headers["location"] == f"/experimental/health/{world.guideline}"
    idx = c.get("/experimental")
    assert idx.status_code == 200 and f'href="/experimental/health/{world.guideline}"' in idx.text
    for path in ("static/review.js", "static/review.html", "static/index.html"):
        text = (Path(__file__).resolve().parents[1] / path).read_text()
        assert "Policy health" not in text and "/review/health" not in text and "/experimental" not in text, path


def test_counts_across_cases(world, fl_spans, tmp_path):
    c = world.client
    # the checklist is cached per section, so the first case decides it for all three: two things no chart can show
    # 3: things no chart can show; CEAP struck by chip alone; one confirmed outside the chart
    u = world.case(unanswerable=True)
    assert c.post(f"/api/review/{u}/strikes", json={"criterion": "ceap", "code": "wrong_quote", "by": "Dana"}).status_code == 201
    assert c.post(f"/api/review/{u}/accepts", json={"criterion": "necessity", "by": "Dana"}).status_code == 201
    # 1: clean, every requirement accepted (both confirmed outside the chart), signed off
    a = world.case()
    accept_all(c, a)
    assert c.post(f"/api/review/{a}/signoff", json={"by": "Dana"}).status_code == 201
    # 2: the vein size not in the chart, added to the ask; CEAP struck with a chip and a note
    b = world.case(verdicts={"size": {"status": "INSUFFICIENT"}})
    assert c.post(f"/api/review/{b}/strikes", json={"criterion": "ceap", "code": "wrong_quote",
                                                     "reason": "Quote runs into the reflux line.", "by": "Lee"}).status_code == 201
    assert c.post(f"/api/review/{b}/accepts", json={"criterion": "size", "by": "Lee"}).status_code == 201
    # line feedback, and a section confirmed against the suggestion (written as the gate would record it)
    size_line = sid(fl_spans, "The varicosities are at least 3 millimeters")
    feedback.add(u, "edit", "guideline", "Say how the size is measured.", [size_line], proposal="… on duplex ultrasound", by="Dana")
    feedback.add(a, "edit", "guideline", "Say how the size is measured.", [size_line], by="Lee")
    feedback.add(a, "wrong_evidence", "chart", "Not this note.", ["r0001"], by="Lee")          # about the chart: not shown
    conf = json.loads((store.RESULTS / b / "pathways.json").read_text())
    conf["suggested"] = [{"code": "36475", "pathway": "accessory"}]
    (store.RESULTS / b / "pathways.json").write_text(json.dumps(conf))

    before = _snapshot(tmp_path)
    d = c.get(f"/api/health/{world.guideline}").json()
    assert _snapshot(tmp_path) == before                                    # read-only: not one byte written

    h = d["headline"]
    assert h["cases"] == 3 and h["signed"] == 1 and h["waiting"] == 1 and h["to_signoff_say"] and h["n_timed"] == 1
    rm = {x["label"]: x for x in d["removed"]}
    ceap = rm["CEAP C2 or greater"]
    assert ceap["count"] == 2 and ceap["cases"] == 3 and ceap["section"] == "Great or Small Saphenous Veins"
    assert ceap["reasons"] == [{"code": "wrong_quote", "label": "The quote is wrong", "count": 2}]
    assert ceap["notes"] == [{"text": "Quote runs into the reflux line.", "count": 1}]        # a chip alone adds no note
    assert ceap["words"].startswith("CEAP (Clinical-Etiology") and ceap["example"] in (b, u)
    miss = {x["label"]: x for x in d["missing"]}
    assert miss["Varicosities ≥ 3 mm"]["count"] == 1 and miss["Varicosities ≥ 3 mm"]["in_ask"] == 1 and miss["Varicosities ≥ 3 mm"]["example"] == b
    out = {x["label"]: x for x in d["outside"]}
    assert out["Meets the definition of medical necessity"]["confirmed"] == 2 and out["Meets the definition of medical necessity"]["cases"] == 3
    assert out["Meets the definition of medical necessity"]["why"] == "This is the plan's judgement, not something a case records."
    assert not any(x["label"].startswith("Meets") for x in d["missing"])               # no chart can show it: not a gap
    assert d["confused"] == [{"from": "Accessory Saphenous Veins", "to": "Great or Small Saphenous Veins", "count": 1,
                              "example": b, "none_suggested": False}] and d["confirmations"] == 3
    fl = d["flagged"]
    assert len(fl) == 1 and fl[0]["kind"] == "edit" and fl[0]["count"] == 2 and fl[0]["quote"].startswith("The varicosities")
    assert fl[0]["notes"] == [{"text": "Say how the size is measured.", "count": 2}] and fl[0]["proposals"][0]["text"] == "… on duplex ultrasound"
    assert not any(x.get("strike") for x in fl)                                        # strikes are counted once, above


def test_the_note_is_about_the_policy_never_a_patient(world):
    c = world.client
    ids = []
    for _ in range(health.MIN_CASES):
        cid = world.case(verdicts={"compression": {"status": "INSUFFICIENT"}})
        c.post(f"/api/review/{cid}/strikes", json={"criterion": "hem", "code": "not_for_case", "by": "Dana"})
        ids.append(cid)
    d = c.get(f"/api/health/{world.guideline}").json()
    note = d["note"]
    assert note.startswith("Policy feedback: ") and "02-33000-31" in note
    assert "compression therapy for at least 3 months" in note and f"{health.MIN_CASES} of {health.MIN_CASES} checks" in note
    for bad in ("Delgado", "Maria", "Dr.", "Vasquez", "Dana", *ids):
        assert bad not in note
    assert "%" not in note


def test_demo_cases_are_counted_and_said(world):
    cid = world.case()
    (store.RESULTS / cid / health.DEMO_FILE).write_text(json.dumps({"seeded": True}))
    d = world.client.get(f"/api/health/{world.guideline}").json()
    assert d["demo"] == {"cases": 1, "of": 1}


def test_short_labels_match_the_navigator():
    assert health.label("The varicosities are at least 3 millimeters in size") == "Varicosities ≥ 3 mm"
    assert health.label("CEAP (Clinical-Etiology-Anatomy-Pathophysiology) class C2* or greater") == "CEAP C2 or greater"
    assert health.label("conservative management including compression therapy for at least 3 months has not improved the symptoms") == "3 months of compression"
    assert health.wilson(20, 30) > health.wilson(2, 3) > 0 and health.wilson(0, 0) == 0


def test_the_seeder_writes_demo_cases_into_the_store_it_is_given(tmp_store, tmp_path, fl_text, fl_spans, delgado_spans, monkeypatch):
    from app import main, pipeline
    from app.core import llm
    from scripts.seed_health import seed
    from tests.conftest import SAMPLES

    monkeypatch.setattr(llm, "pick_models", lambda ids=None: ("m", "m"))
    monkeypatch.setattr(feedback, "FEEDBACK", tmp_path / "feedback")
    sha = hashlib.sha256((SAMPLES / "fl_varicose_veins_guideline.pdf").read_bytes()).hexdigest()
    gid = pipeline.add_guideline(fl_text, "fl.pdf", sha, "bcbsfl-02-33000-31")
    ids = seed(8, fl_spans, delgado_spans, gid)
    assert len(ids) == 8 and all((store.RESULTS / i / health.DEMO_FILE).exists() for i in ids)
    assert main.BACKGROUND is True                                   # put back as it was
    d = health.build(gid)
    assert d["demo"] == {"cases": 8, "of": 8} and d["headline"]["cases"] == 6       # the newest two wait at the section
    assert d["outside"] and d["removed"] and "Delgado" not in d["note"]
