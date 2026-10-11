"""STEP_H=loose-next: shipped loose + QA's sweep / admin / keep lists in its own prompt files (the loose prompts stay
byte-identical), dispatched by the pipeline and the reduce runner, with its own cache key and spend file. Pure: a
scripted fake model, tmp_path only."""
from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path

import pytest

from app import pipeline
from app.checklist import keys
from app.checklist import admin, criteria, reduce_next
from app.core.models import Procedure
from tests.stepH_fake import HEAD, REFLUX, C, H, _sel, offline, pid, script  # noqa: F401

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
SWEEP = ['"stop billing"', "rental or purchase", "supplier", "Evidence summaries, rationale and background text",
         "effective dates", '"As determined by <the payer>" cost-effectiveness', "subject to the member's benefit plan",
         "operative report, pathology report", '"prior authorization is required", "submit records"']
ADMIN = ['"may be required" documentation lists', "The procedure's own description",
         '"percutaneous, radiofrequency; first vein treated"', "Headings and list lead-ins",
         '"If this Medical Coverage Guideline contains a step therapy requirement …" is a lead-in']
KEEP = ["Frequency, quantity and time limits", "reimbursement rule that denies a combination",
        "an AHI from under 2 hours of sleep needs at least 10 events", '"as determined by the Plan"',
        "A coded diagnosis the criteria require", "attestation that stands in for evidence",
        "who performs or interprets", '"meets InterQual", "NCD 20.4"', '"other … disorder"',
        '"B. Presence of a comorbid condition:"', '"lymphoscintigraphy of the limb proposed for surgery"',
        '"FDA-approved"', '"adults" or an age', '"permanent"', "side and site", "a device type the order does not state",
        "The step-therapy exemption", "OR route"]
G_HEADS = ["## Sweep to notes (never a condition)", "## Write and mark admin",
           "## Keep these (always conditions; never swept, never admin)"]
A_HEADS = ["## Not loopholes (do not add these)", "## Admin lines", "## Still gaps to close"]
WHYS = '"billing or coding", "paperwork", "heading or definition", "procedure wording"'
ONCE = "Write each requirement once: if two lines of the policy say the same thing, make one condition and cite both."
OPS = '`threshold.op` is one of ">=", ">", "<=", "<", "=="'


def _sec(text, head, nxt):
    return text[text.index(head):text.index(nxt)]


def test_next_prompts_carry_the_three_lists():
    g, a = (PROMPTS / "criteria_guideline_next.md").read_text(), (PROMPTS / "criteria_audit_next.md").read_text()
    sweep, adm, keep = (_sec(g, G_HEADS[0], G_HEADS[1]), _sec(g, G_HEADS[1], G_HEADS[2]), _sec(g, G_HEADS[2], "{{plan_rule}}"))
    assert all(x in sweep for x in SWEEP) and all(x in adm for x in ADMIN) and all(x in keep for x in KEEP)
    assert "The member's plan rule below applies as written." in keep
    assert ONCE in g and OPS in g and "a range is two conditions" in g and WHYS in g and "{{plan_rule}}" in g
    asw, aad, akp = (_sec(a, A_HEADS[0], A_HEADS[1]), _sec(a, A_HEADS[1], A_HEADS[2]), _sec(a, A_HEADS[2], "## The request"))
    assert all(x in asw for x in SWEEP) and all(x in aad for x in ADMIN) and all(x in akp for x in KEEP)
    assert "carries `admin: true`" in aad and "a missing scope word, limit or side/site requirement is a loophole" in akp
    assert WHYS in a and OPS in a


def test_next_prompts_are_loose_plus_the_lists():
    """Everything else is the shipped loose text: the only lines removed are the admin sentence; the only lines added
    are the three lists, the "write once" and threshold-op lines and the new admin sentence."""
    for orig, nxt, first, after, admin in [
            ("criteria_guideline.md", "criteria_guideline_next.md", G_HEADS[0], "{{plan_rule}}", "- `admin: true`"),
            ("criteria_audit.md", "criteria_audit_next.md", A_HEADS[0], "## The request", "Quotes are copied exactly")]:
        o, x = (PROMPTS / orig).read_text(), (PROMPTS / nxt).read_text()
        lists = x[x.index(first):x.index(after)]
        ops = difflib.ndiff(o.splitlines(), x.splitlines())
        gone = [ln[2:] for ln in ops if ln.startswith("- ")]
        added = [ln[2:] for ln in difflib.ndiff(o.splitlines(), x.splitlines()) if ln.startswith("+ ")]
        assert len(gone) == 1 and gone[0].startswith(admin), nxt
        rest = [ln for ln in added if ln and ln not in lists.splitlines()]
        assert len(rest) == (3 if nxt == "criteria_guideline_next.md" else 1), (nxt, rest)
        assert all(ln.startswith(admin) or ONCE in ln or OPS in ln for ln in rest), nxt


def test_loose_next_renders_its_prompts_and_writes_spend(fl_spans, offline, monkeypatch):
    p = pid(fl_spans)
    sent = script(monkeypatch, [H(p, "reflux", C("reflux", REFLUX))])
    n, sel = _sel(fl_spans)
    cs = reduce_next.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"], plan="commercial"),
                           extra={"age": 58}, indication=HEAD)
    (s1, first), (s2, aud) = sent
    assert s1 == "criteria_guideline" and s2 == "criteria_audit" and cs.status == "ok"
    assert all(h in first for h in G_HEADS) and all(x in first for x in SWEEP + ADMIN + KEEP)
    assert "## The member's plan" in first and HEAD in first and "age 58" in first and "plan: commercial" in first
    assert first.index(G_HEADS[0]) < first.index(G_HEADS[2]) < first.index("## The member's plan") < first.index("## The request")
    assert "{{" not in first and "{{" not in aud
    assert all(h in aud for h in A_HEADS) and all(x in aud for x in SWEEP + ADMIN + KEEP)
    assert (offline / "runs" / "r" / "criteria_loose_next-cost.json").exists()


def test_loose_still_renders_the_shipped_prompts(fl_spans, offline, monkeypatch):
    p = pid(fl_spans)
    sent = script(monkeypatch, [H(p, "reflux", C("reflux", REFLUX))])
    n, sel = _sel(fl_spans)
    criteria.build(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), indication=HEAD)
    assert all(h not in x for _, x in sent for h in G_HEADS + A_HEADS)


def test_admin_why_values_validate(fl_spans):
    n, sel = _sel(fl_spans)
    want = criteria.picked(sel)
    h = criteria.HOut.model_validate(H(want[0], "reflux AND desc",
                                       C("reflux", REFLUX),
                                       C("desc", REFLUX, admin=True, admin_why="procedure wording")))
    problems, crit, _ = criteria.check(h, fl_spans, want)
    desc = next(c for c in crit if c.id == "desc")
    assert desc.admin and admin.why_of(desc) == "procedure wording"
    for w in ("billing or coding", "paperwork", "heading or definition", "procedure wording"):
        assert w in admin.WHYS
    assert admin.why_of(desc.model_copy(update={"admin_why": "background"})) == admin.DEFAULT_WHY


def test_cache_key_and_prompt_version_differ_from_loose(monkeypatch):
    p = Procedure(cpt=["36475"], plan="commercial")
    monkeypatch.setenv("STEP_H", "loose")
    loose, vl = keys.legacy_cache_key("a" * 64, p), keys.prompt_version()
    monkeypatch.setenv("STEP_H", "loose-next")
    assert keys.legacy_cache_key("a" * 64, p) == loose + "-hloose-next"
    assert keys.prompt_version() != vl
    assert keys.H_PROMPTS["loose-next"] == ["criteria_guideline_next", "criteria_audit_next", "reduce/plan"]
    assert all((PROMPTS / f"{x}.md").exists() for x in keys.H_PROMPTS["loose-next"])


def test_pipeline_dispatch(fl_spans, monkeypatch):
    monkeypatch.setenv("STEP_H", "loose-next")
    got = {}

    def fake(*a, **k):
        got.update(k)
        raise RuntimeError("dispatched")
    monkeypatch.setattr(reduce_next, "build", fake)
    n, sel = _sel(fl_spans)
    with pytest.raises(RuntimeError, match="dispatched"):
        pipeline.build_h(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]), progress=lambda s: None)
    assert got["progress"] is not None
    monkeypatch.setenv("STEP_H", "loose")
    monkeypatch.setattr(criteria, "build", fake)
    with pytest.raises(RuntimeError, match="dispatched"):
        pipeline.build_h(fl_spans, n, sel, "k", "r", Procedure(cpt=["36475"]))


def test_original_loose_prompts_unchanged():
    # approved 2026-10-10: admin flag (the loose prompts' hashes; the loop comparison is in experiments/tests)
    sha = {"criteria_guideline.md": "25aeb5c67c521df207a8238700d4da4d17e31b66e009a8c3f2423837ee513ecd",
           "criteria_audit.md": "b6d0c075684446077687b2b1fbaf3081f13689b51b6518765a2e1fbf011cc5c6"}
    for name, want in sha.items():
        assert hashlib.sha256((PROMPTS / name).read_bytes()).hexdigest() == want, name
