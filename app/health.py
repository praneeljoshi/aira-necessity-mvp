"""Policy health: what coordinators' work on one guideline says about the guideline itself (GET /api/health/{id},
the page /experimental/health/{id}). One document per guideline, aggregated by code from what every case on it stored:

    data/results/<id>/{result, meta, status, pathways, strikes, additions, accepts, signoff}.json, data/feedback

    headline    cases checked (a result exists), signed off (signoff.view: signed), waiting on the surgeon (something
                in the ask that still counts, not signed), the median time from upload to sign-off
    removed     per requirement: how many of the cases it was on struck it, by reason chip (strikes.REASONS), the
                notes people wrote, ranked by that rate
    missing     per requirement: how many cases read "Not in the chart yet" or had it added to the ask
    outside     requirements no chart can show (answerable: false) with one sentence of why (review.outside_why)
    confused    the section a person confirmed when it differs from the one the guideline reader suggested
    flagged     line feedback on the guideline (should be a requirement, not a requirement, the logic is wrong, an
                edit), grouped by the lines and kind; strikes are not repeated here (they are `removed`)

A requirement is known across cases by its own words (spans.wording: the checked quote, else its lines): the same
words on two checklists are the same requirement of the policy. Rates count only the cases whose checklist carried
it. Read-only: nothing here writes a file or calls the model; a case that cannot be read is skipped. `note` is the
plain-text summary of removed / missing / outside / confused for the payer: about the policy's wording, never a
patient (no name, no chart id, no date of service).
"""
from __future__ import annotations

import json
import re
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

from . import accepts, feedback, review, signoff, status, store, strikes, tree
from .evaluate import compile_expr, leaf_ids
from .models import Result, Verdict
from .select import pathway_name
from .spans import expand, table, text_of, wording

DEMO_FILE = "demo.json"          # data/results/<id>/demo.json: a synthetic case (scripts/dev_server.py --seed-health)
NOTES = 3                        # notes quoted per requirement / flagged line
MIN_CASES = 5                    # a requirement on fewer checklists than this is listed after the others, and left out
                                 # of the note to the payer: one case is an anecdote, not a pattern
FLAG_KINDS = {"should_be_requirement": "Should be a requirement", "not_a_requirement": "Not a requirement",
              "logic_wrong": "The logic reads wrong", "edit": "Wording proposed"}


# ---------------------------------------------------------------- a short label, by code (as static/review.js label())


def label(w: str) -> str:
    """A 3-6 word label from a requirement's own words, the same rules as the navigator's (review.js `label`), so
    a requirement reads the same on the case page and here; the full words go on hover."""
    t = " " + re.sub(r"[;:,.]?\s*(AND|OR)\s*$", "", re.sub(r"\*", "", re.sub(r"\([^)]*\)", " ", str(w or "")))) + " "
    rw = [
        (r"\b(?:conservative management including )?(compression(?: therapy| stockings)?)\b.*?\bfor at least (\d+) months\b.*", r" \2 months of compression ", re.I),
        (r"^.*?\bsymptoms are associated with\b", " Symptoms from ", re.I),
        (r"\b(?:significantly )?interfere with activities of daily living\b", " affect daily living ", re.I),
        (r"\bare at least (\d+(?:\.\d+)?) millimeters?\b", r" ≥ \1 mm ", re.I), (r"\bat least (\d+(?:\.\d+)?) millimeters?\b", r" ≥ \1 mm ", re.I),
        (r"\bat least (\d+(?:\.\d+)?) ", r" ≥ \1 ", re.I),
    ]
    every = [(r"\bmillimeters?\b", " mm "), (r"\bin size\b", " "), (r"\bclass\b", " "), (r"\bor greater\b", " or greater ")]
    for pat, to, fl in rw:                             # the first match only, as the JS regexes without /g
        t = re.sub(pat, to, t, count=1, flags=fl)
    for pat, to in every:
        t = re.sub(pat, to, t, flags=re.I)
    fill = re.compile(r"^\s*(there is|there are|documentation of|documented|demonstrated|the patient has|the following|the|a|an)\s+", re.I)
    for _ in range(6):
        if not fill.search(t):
            break
        t = fill.sub(" ", t, count=1)
    t = re.sub(r"[,;:.]+$", "", re.sub(r"\s+", " ", t).strip())
    ws = t.split(" ")
    if len(ws) > 6:
        t = re.sub(r"\s+(of|and|or|to|with|the|a|in|for|by)$", "", " ".join(ws[:6]), flags=re.I) + "…"
    if not t:
        w = re.sub(r"\s+", " ", str(w or "")).strip().rstrip(".")
        return w if len(w) <= 40 else w[:39].rsplit(" ", 1)[0] + "…"
    return t[0].upper() + t[1:]


# ---------------------------------------------------------------- reading one case


def _json(p: Path) -> Optional[Any]:
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except (ValueError, OSError):
        return None


def _gid_of(d: Path) -> Optional[str]:
    meta, res = _json(d / "meta.json") or {}, _json(d / "result.json") or {}
    conf, st = _json(d / "pathways.json") or {}, _json(d / "status.json") or {}
    return meta.get("guideline_id") or res.get("guideline_id") or conf.get("guideline_id") or st.get("guideline_id")


def _ts(s: Optional[str]) -> Optional[float]:
    try:
        return time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")) if s else None
    except ValueError:
        return None


def _leaf_sides(e: Any, neg: bool = False, out: Optional[dict] = None) -> dict[str, bool]:
    """{leaf: under an odd number of nots}: an exclusion "missing" from the chart is not a gap in the chart."""
    out = {} if out is None else out
    if isinstance(e, str):
        out.setdefault(e, neg)
        return out
    (op, arg), = e.items()
    if op == "not":
        return _leaf_sides(arg, not neg, out)
    for x in (arg["of"] if op == "at_least" else arg):
        _leaf_sides(x, neg, out)
    return out


class _Case:
    """What one finished case on the guideline contributes; `ok` is False when it cannot be read."""

    def __init__(self, cid: str, gspans, gt, sha: str, cache: dict):
        self.cid, self.ok, self.reqs = cid, False, {}
        rec = store.load_result(cid)
        r = Result.model_validate(rec["result"])
        o = store.load_order(cid)
        conf = review.confirmation(cid)
        ck = (pipeline_key(sha, o, cid) if o else None, (conf or {}).get("h_key"))
        if ck not in cache:
            cache[ck] = review._criteria_for_case(sha, o, conf, cid)
        n, cs = cache[ck]
        cs = store.load_case_criteria(cid) or cs           # the set this case was judged with, when pinned
        self.n, self.cs, self.result, self.conf = n, cs, r, conf
        if cs is None:
            return
        verdicts = {k: Verdict.model_validate(v) for k, v in (rec.get("verdicts") or {}).items()}
        crit = cs.criterion_map()
        pids = r.pathway_used or []
        exprs = {e.pathway: e.expr for e in cs.expressions}
        info: dict[str, dict] = {}
        sides: dict[str, bool] = {}
        for pid in pids:
            if pid in exprs:
                tree.classify(exprs[pid], compile_expr(exprs[pid], verdicts), True, info)
                _leaf_sides(exprs[pid], False, sides)
        bases = {cid_: accepts.basis(r.run_id, cs.key, cid_, verdicts.get(cid_)) for cid_ in info}
        for x in additions_active(cid, cs.key):        # an added requirement's accept counts against its own basis
            for c in x.get("criteria") or []:
                v = (x.get("verdicts") or {}).get(c["id"])
                bases[c["id"]] = accepts.basis(r.run_id, cs.key, c["id"], Verdict.model_validate(v) if v else None)
        took = accepts.current(cid, bases)
        self.in_ask = [k for k, a in took.items() if a.get("mark") in tree.BAD]
        struck = {x["criterion"]: x for x in strikes.active(cid) if x.get("criteria_key") == cs.key}
        for k, inf in info.items():
            c = crit.get(k)
            if c is None:
                continue
            words = wording(c, gt)
            if struck.get(k) and struck[k].get("words") != words:
                struck.pop(k)
            refs = expand(c.refs, gt)
            mark = tree.mark_of(inf, c, verdicts.get(k))
            self.reqs[words] = {"criterion": k, "words": words, "refs": refs, "answerable": c.answerable,
                                "mark": mark, "negated": sides.get(k, False), "struck": struck.get(k),
                                "in_ask": k in self.in_ask, "accepted": took.get(k),
                                "source": review.source_of(refs, n, pids, gspans)}
        self.ok = True


def pipeline_key(sha: str, o, chart_id: Optional[str] = None) -> str:
    from .pipeline import case_order_key
    return case_order_key(sha, o.procedure, chart_id)


def additions_active(cid: str, key: str) -> list[dict]:
    from . import additions
    return [x for x in additions.active(cid) if x.get("criteria_key") == key]


# ---------------------------------------------------------------- the document


def _dur(seconds: float) -> str:
    h = seconds / 3600
    if h < 1:
        return f"{max(1, round(seconds / 60))} min"
    if h < 36:
        return f"{round(h)} h" if h >= 10 else f"{h:.1f} h".replace(".0 h", " h")
    d = h / 24
    return f"{d:.1f} days".replace(".0 days", " days")


def wilson(k: int, n: int, z: float = 1.96) -> float:
    """The lower end of the rate's 95% interval (Wilson): the order of the lists, so 2 of 3 does not outrank 20 of
    30. The page shows the plain counts."""
    if not n:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    return (p + z * z / (2 * n) - z * ((p * (1 - p) + z * z / (4 * n)) / n) ** 0.5) / d


def _top(counter: Counter, n: int = NOTES) -> list[dict]:
    return [{"text": t, "count": c} for t, c in counter.most_common(n)]


def build(gid: str) -> Optional[dict]:
    """The health document for one guideline; None when the guideline is not on file."""
    if not store.guideline_exists(gid):
        return None
    gspans, sha, _ = store.load_guideline_spans(gid)
    gt = table(gspans)
    gv = review.guideline_view(gid)
    root = Path(store.RESULTS)
    dirs = sorted(d for d in root.iterdir() if d.is_dir() and _gid_of(d) == gid) if root.exists() else []

    cache: dict = {}
    cases: list[_Case] = []
    started: list[float] = []
    demo = 0
    paused = 0
    for d in dirs:
        if (d / DEMO_FILE).exists():
            demo += 1
        st = status.load_status(d.name) or {}
        if st.get("state") == "paused":
            paused += 1
        if not (d / "result.json").exists():
            continue
        try:
            c = _Case(d.name, gspans, gt, sha, cache)
        except Exception:                               # a half-written case never breaks the page
            continue
        c.status = st
        cases.append(c)
        t = _ts(st.get("started_at"))
        if t:
            started.append(t)

    # headline
    signed, waiting, to_sign = [], 0, []
    for c in cases:
        so = signoff.view(c.cid)
        if so["state"] == "signed":
            signed.append(c)
            a, b = _ts(c.status.get("started_at")), _ts((so.get("record") or {}).get("at"))
            if a and b and b >= a:
                to_sign.append(b - a)
        elif c.ok and c.in_ask:
            waiting += 1
    med = statistics.median(to_sign) if to_sign else None

    # per requirement, by its words
    on: dict[str, list[_Case]] = defaultdict(list)
    for c in cases:
        for w in c.reqs:
            on[w].append(c)

    def meta_of(w: str, cs_: list[_Case]) -> dict:
        srcs = [c.reqs[w].get("source") or {} for c in cs_]
        part = Counter(x.get("part") or "" for x in srcs).most_common(1)[0][0]
        src = next(x for x in srcs if (x.get("part") or "") == part)
        return {"words": w, "label": label(w), "section": src.get("part") or "", "other": bool(src.get("other")),
                "page": src.get("page"), "cases": len(cs_)}

    removed = []
    missing = []
    outside = []
    for w, cs_ in on.items():
        hit = [c for c in cs_ if c.reqs[w]["struck"]]
        if hit:
            codes = Counter((c.reqs[w]["struck"].get("code") or "other") for c in hit)
            notes = Counter()
            for c in hit:
                s = c.reqs[w]["struck"]
                txt = (s.get("reason") or "").strip()
                if txt and txt != strikes.LABELS.get(s.get("code") or ""):
                    notes[txt] += 1
            removed.append({**meta_of(w, cs_), "count": len(hit), "rate": len(hit) / len(cs_),
                            "reasons": [{"code": k, "label": strikes.LABELS.get(k, "Other"), "count": n}
                                        for k, n in codes.most_common()],
                            "notes": _top(notes), "example": hit[-1].cid})
        if all(c.reqs[w]["answerable"] for c in cs_):
            gap = [c for c in cs_ if not c.reqs[w]["negated"] and (c.reqs[w]["mark"] == "missing" or c.reqs[w]["in_ask"])]
            if gap:
                missing.append({**meta_of(w, cs_), "count": len(gap), "rate": len(gap) / len(cs_),
                                "in_ask": sum(1 for c in gap if c.reqs[w]["in_ask"]), "example": gap[-1].cid})
        else:
            m = meta_of(w, cs_)
            conf = [c for c in cs_ if c.reqs[w]["accepted"]]
            gone = [c for c in cs_ if c.reqs[w]["struck"]]
            outside.append({**m, "why": review.outside_why(w, cs_[-1].reqs[w].get("source")),
                            "confirmed": len(conf), "struck": len(gone), "example": cs_[-1].cid})
    order = lambda x: (x["cases"] < MIN_CASES, -wilson(x["count"], x["cases"]), -x["rate"], x["label"])
    removed.sort(key=order)
    missing.sort(key=order)
    outside.sort(key=lambda x: (-x["cases"], x["label"]))

    # sections confused: suggested -> confirmed, where they differ
    pairs: dict[tuple, list[str]] = defaultdict(list)
    n_conf = 0
    for d in dirs:
        conf = _json(d / "pathways.json")
        if not conf or not conf.get("confirmed"):
            continue
        n_conf += 1
        sug = sorted({p["pathway"] for p in conf.get("suggested") or []})
        got = sorted({p["pathway"] for p in conf["confirmed"]})
        if sug == got:
            continue
        nk = conf.get("narrowed_key") or ""
        key = (nk, tuple(sug), tuple(got))
        pairs[key].append(d.name)
    named: dict[tuple, dict] = {}
    for (nk, sug, got), ids in pairs.items():
        n = store.load_criteria(nk)[0] if nk else None
        name = lambda p: pathway_name(n, p, gspans) if n else p
        frm = "; ".join(name(p) for p in sug) or "Nothing suggested"
        to = "; ".join(name(p) for p in got)
        k = (frm, to)
        if k not in named:
            named[k] = {"from": frm, "to": to, "count": 0, "example": None, "none_suggested": not sug}
        named[k]["count"] += len(ids)
        named[k]["example"] = ids[-1]
    confused = sorted(named.values(), key=lambda x: (-x["count"], x["from"], x["to"]))

    # lines coordinators flagged
    groups: dict[tuple, dict] = {}
    for it in feedback.search(gid):
        if it.get("side") != "guideline" or it.get("kind") not in FLAG_KINDS or it.get("strike"):
            continue
        spans = [s for s in it.get("spans") or [] if s in gt]
        if not spans:
            continue
        k = (it["kind"], tuple(spans))
        g = groups.setdefault(k, {"kind": it["kind"], "say": FLAG_KINDS[it["kind"]], "lines": spans,
                                  "quote": re.sub(r"^[•▪➢❖◦·\-–]\s*", "", text_of(spans, gt)), "page": gt[spans[0]].page, "count": 0,
                                  "_notes": Counter(), "_props": Counter(), "example": None, "added": 0})
        g["count"] += 1
        g["example"] = it.get("chart_id")
        if it.get("addition"):
            g["added"] += 1
        else:
            t = (it.get("text") or "").strip()
            if t:
                g["_notes"][t] += 1
        p = (it.get("proposal") or "").strip()
        if p:
            g["_props"][p] += 1
    flagged = []
    for g in groups.values():
        g["notes"], g["proposals"] = _top(g.pop("_notes")), _top(g.pop("_props"), 2)
        flagged.append(g)
    flagged.sort(key=lambda x: (-x["count"], list(FLAG_KINDS).index(x["kind"])))

    span = None
    if started:
        span = {"from": time.strftime("%Y-%m-%d", time.localtime(min(started))),
                "to": time.strftime("%Y-%m-%d", time.localtime(max(started)))}
    doc = {"guideline": {"id": gid, "name": gv["name"] or gv["title"], "number": gv["number"], "issuer": gv["issuer"],
                         "payer": gv["payer"]},
           "headline": {"cases": len(cases), "signed": len(signed), "waiting": waiting, "paused": paused,
                        "to_signoff": med, "to_signoff_say": _dur(med) if med is not None else None,
                        "n_timed": len(to_sign)},
           "removed": removed, "missing": missing, "outside": outside,
           "confused": confused, "confirmations": n_conf, "flagged": flagged, "span": span,
           "demo": {"cases": demo, "of": len(dirs)} if demo else None,
           "reasons": [{"code": c, "label": w} for c, w in strikes.REASONS]}
    doc["note"] = note(doc)
    return doc


# ---------------------------------------------------------------- the note to the payer


def _q(w: str, n: int = 140) -> str:
    w = re.sub(r"\s+", " ", w).strip()
    return "“" + (w if len(w) <= n else w[: n - 1].rsplit(" ", 1)[0] + "…") + "”"


def _where(x: dict) -> str:
    return f" ({x['section']})" if x.get("section") else ""


def note(doc: dict) -> str:
    """Plain text for the payer: findings on the policy's wording from removed, missing, outside and confused. It
    names requirements and sections by the policy's own words and counts checks; it never names a patient, a case or
    a date of service."""
    g, h = doc["guideline"], doc["headline"]
    title = " ".join(x for x in [g.get("issuer") or g.get("payer"), g.get("number")] if x)
    out = [f"Policy feedback: {g.get('name') or g.get('id')}" + (f" ({title})" if title else ""), ""]
    out.append(f"Our coordinators checked {h['cases']} prior-authorization request{'s' if h['cases'] != 1 else ''} "
               "against this policy. These are the places where its wording was hard to apply. They are about the "
               "policy text only, offered in case they help a future revision.")
    top = [x for x in doc["removed"] if x["cases"] >= MIN_CASES][:5]
    if top:
        out += ["", "Requirements reviewers found did not apply to the request"]
        for x in top:
            why = x["reasons"][0]["label"].lower() if x["reasons"] and x["reasons"][0]["code"] != "other" else ""
            out.append(f"- {_q(x['words'])}{_where(x)}: set aside in {x['count']} of {x['cases']} checks"
                       + (f", most often as “{why}”." if why else "."))
    gap = [x for x in doc["missing"] if x["cases"] >= MIN_CASES][:5]
    if gap:
        out += ["", "Requirements most often not yet documented when first checked"]
        for x in gap:
            out.append(f"- {_q(x['words'])}{_where(x)}: {x['count']} of {x['cases']} checks. "
                       "A note on what documentation satisfies it would help.")
    if doc["outside"]:
        out += ["", "Requirements a medical record cannot show"]
        for x in doc["outside"][:5]:
            out.append(f"- {_q(x['words'])}{_where(x)}: {x['why']} Could the policy say how it is confirmed?")
    if doc["confused"]:
        out += ["", "Sections that were hard to tell apart"]
        for x in doc["confused"][:5]:
            frm = "no section" if x.get("none_suggested") else f"“{x['from']}”"
            out.append(f"- Read first as {frm}, applied as “{x['to']}”: {x['count']} "
                       f"time{'s' if x['count'] != 1 else ''}.")
        out.append("Clearer criteria for which indication applies would help.")
    if len(out) <= 3:
        out += ["", "Nothing stood out yet."]
    return "\n".join(out) + "\n"
