"""The cache keys: which C (narrowed guideline) and H (checklist) a case reads, built from the guideline, the
order's facts, the structure model and the bytes of the prompts each step reads."""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Optional

from app.checklist import hints
from app.core import llm, store
from app.core.models import Narrowed, Procedure, Span
from app.core.status import load_status


def slug(s: str, n: int = 60) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")[:n].strip("-")


_SIDE = re.compile(r"\b(left|right|bilateral|both|lt|rt|l|r)\b\.?", re.I)


def target_key(p: Procedure) -> str:
    """Side does not change which section applies; it is dropped from the key."""
    t = p.target or ("" if p.cpt else p.as_written or "")
    return slug(_SIDE.sub(" ", t), 50) or "any"


# The prompt files each step-H mode reads (C reads narrow_guideline). Their bytes, with the mode, make the prompt
# version in the cache keys, so a tree built from other prompts is never served.
C_PROMPTS = ["narrow_guideline"]
H_PROMPTS = {
    "loose": ["criteria_guideline", "criteria_audit", "reduce/plan"],
    "loose-loop": ["criteria_guideline_loop", "loop_round", "reduce/plan"],
    "loose-next": ["criteria_guideline_next", "criteria_audit_next", "reduce/plan"],
    "code": ["reduce/policies", "reduce/indication_given", "reduce/indication_find", "reduce/brief", "reduce/plan",
             "reduce/sweep", "reduce/task", "reduce/fix", "reduce/sweep_code", "reduce/audit"],
    "form": ["reduce/form", "reduce/brief", "reduce/policies", "reduce/indication_given", "reduce/indication_find",
             "reduce/plan", "reduce/sweep", "reduce/sweep_form", "criteria_audit"],
    "script": ["reduce/script", "reduce/plan", "reduce/sweep", "reduce/pitfalls", "reduce/script_audit"],
    "tools": ["reduce/tools", "reduce/plan", "reduce/sweep", "reduce/pitfalls", "reduce/tools_audit"],
}


def step_h() -> str:
    """Shipped step H: loose-next (owner, 2026-10-10). STEP_H=loose rolls back."""
    return os.environ.get("STEP_H", "loose-next")


def _prompt_bytes(name: str) -> bytes:
    p = llm.prompt_path(name)
    return p.read_bytes() if p.exists() else b""


def prompt_version(with_c: bool = True, mode: Optional[str] = None, hint: Optional[str] = None) -> str:
    """8 hex over the mode's name and the bytes of every prompt file C (with_c) and its H read; `hint` (the payer
    structure hint's `<name>.<sha8>`, only when one was applied) joins them, so the version without one is unchanged."""
    mode = mode or step_h()
    h = hashlib.sha1(mode.encode())
    for name in (C_PROMPTS if with_c else []) + H_PROMPTS.get(mode, []):
        h.update(b"\0" + name.encode() + b"\0" + _prompt_bytes(name))
    if hint:
        h.update(b"\0hint\0" + hint.encode())
    return h.hexdigest()[:8]


# The step-H modes that inject the payer structure hint (criteria.build and its audit; app/checklist/hints.py).
HINT_MODES = ("loose", "loose-next")


def h_hint(gspans: Optional[list[Span]]) -> Optional[str]:
    """The payer structure hint H applies to this guideline (`<name>.<sha8>`), or None: flag off, unknown payer, two
    files matching, no guideline lines given, or a mode that does not inject it."""
    return hints.payer_id(gspans) if gspans and step_h() in HINT_MODES else None


def _pin(with_c: bool, hint: Optional[str] = None) -> str:
    """`-m<structure model>-v<prompt version>`: what built a cached tree, so another model's or prompt's never is."""
    return f"-m{re.sub(r'[^A-Za-z0-9._-]+', '_', llm.pick_models()[0])[:40]}-v{prompt_version(with_c, hint=hint)}"


def order_facts(p: Procedure) -> str:
    """Every order fact step H's prompt receives (criteria.request_line), as a key part: the sorted CPT codes, the
    target (side dropped), the ICD codes in the diagnosis and a hash of the plan; `<cpts|nocpt>-<target>[-icd][-p<8>]`.
    The order key (cache_key) and the H key (h_cache_key) both build on it, so the two can never drift."""
    icd = sorted(set(re.findall(r"\b[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?\b", p.diagnosis or "")))
    return (f"{'+'.join(sorted(p.cpt)) or 'nocpt'}-{target_key(p)}" + (f"-{'+'.join(icd)}" if icd else "")
            + (f"-p{hashlib.sha1(p.plan.encode()).hexdigest()[:8]}" if p.plan else ""))


def legacy_cache_key(sha: str, p: Procedure) -> str:
    """The order key before models and prompts were in it: read only for older cases that recorded no key."""
    mode = step_h()
    return (f"{sha[:16]}-{order_facts(p)}"
            + ("" if mode == "loose" else f"-h{mode}") + ("-pf" if os.environ.get("PITFALLS") == "1" else ""))


def cache_key(sha: str, p: Procedure, gspans: Optional[list[Span]] = None) -> str:
    """C and H for an order: data/criteria/<sha16>-<cpts>-<target>[-icd][-plan][-hmode][-pf]-m<model>-v<prompts>.
    `gspans`: the guideline's lines, to fold in the payer structure hint when H applies one (else the key is as before)."""
    return legacy_cache_key(sha, p) + _pin(with_c=True, hint=h_hint(gspans))


def h_cache_key(sha: str, n: Narrowed, pids: list[str], p: Optional[Procedure],
                gspans: Optional[list[Span]] = None) -> str:
    """H cached by the pathways a person confirmed AND the order: H's prompt carries the order (procedure, codes,
    target, diagnosis, plan) and its tree holds order-specific conditions (a technique, a CPT descriptor), so one
    order's tree is never served to another order on the same section. `h-<sha16>-<pids>-<ranges8>-o<order facts>
    -m<model>-v<prompts>`: the guideline, the pathway ids, a hash of their line ranges (the same id over different
    ranges is a different section), `order_facts(p)` (the same part cache_key uses), then the model and the H prompt
    version (which includes the mode, and the payer structure hint when H applies one: `gspans`, app/checklist/hints.py).
    `p=None` (precompute, no order) gives `-onone`, a key no order ever reads."""
    by = {x.id: x for x in n.pathways}
    pids = sorted(dict.fromkeys(pids))
    ranges = json.dumps([[[r.first, r.last] for r in by[x].spans] if x in by else None for x in pids])
    return ("h-" + sha[:16] + "-" + "+".join(pids) + "-" + hashlib.sha1(ranges.encode()).hexdigest()[:8]
            + "-o" + (order_facts(p) if p is not None else "none") + _pin(with_c=False, hint=h_hint(gspans)))


def case_order_key(sha: str, p: Procedure, chart_id: Optional[str] = None) -> str:
    """The order key a case was read with, for showing it: the key its check recorded (status tree / resume, the
    confirmation's narrowed_key) when that file exists; else today's key when cached; else the key older cases were
    written under. Runs never read through this; they use cache_key."""
    tried = []
    if chart_id:
        st = load_status(chart_id) or {}
        conf = store.load_confirmation(chart_id) or {}
        tk = (st.get("tree") or {}).get("criteria_key") or ""
        tried += [tk if not tk.startswith("h-") else "", (st.get("resume") or {}).get("key") or "",
                  conf.get("narrowed_key") or ""]
    gspans = None
    if chart_id and hints.enabled():          # today's key carries the payer structure hint when H applies one
        try:
            gspans = store.load_guideline_spans((load_status(chart_id) or {}).get("guideline_id") or "")[0]
        except Exception:
            gspans = None
    tried += [cache_key(sha, p, gspans), legacy_cache_key(sha, p)]
    for k in tried:
        if k and store.criteria_cached(k):
            return k
    return cache_key(sha, p, gspans)
