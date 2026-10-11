"""A stub model for the FL varicose guideline and the Delgado chart. Each step's answer is built by searching span
text, so the stub stays right when the splitter renumbers spans. Spans are lines: a needle must fit on one line, and
sentences that wrap are cited as ranges ("g0049-g0054"). It records which steps were called."""
from __future__ import annotations

import json
import re

from tests.conftest import idx, rng, sid

GSV_CODES = ["36465", "36466", "36475", "36476", "36478", "36479", "36482", "36483", "37700", "37718", "37722",
             "37735", "37780", "37785"]


def _indent(s) -> int:
    return len(s.text) - len(s.text.lstrip())


def codes_of(g):
    """The code table: a row is the line a code starts on plus its indented continuation lines, cited as a range;
    the tag is read from the row's joined text ("(Non-covered)", "(Investigational)" may sit on a later line)."""
    start, end = idx(g, sid(g, "BILLING/CODING INFORMATION")), idx(g, sid(g, "LOINC Codes:"))
    out = []
    i = start
    while i < end:
        s = g[i]
        m = re.match(r"^\s*(\d{4}[0-9T]|[A-Z]\d{4})\b", s.text)
        if not m:
            i += 1
            continue
        j = i + 1
        while j < end and not g[j].blank_before and _indent(g[j]) > _indent(s):
            j += 1
        text = " ".join(x.text for x in g[i:j])
        if not any(x["code"] == m.group(1) for x in out):
            tag = "non_covered" if "Non-covered" in text else "investigational" if "Investigational" in text else "covered"
            out.append({"code": m.group(1), "tag": tag, "refs": [s.id if j == i + 1 else f"{s.id}-{g[j - 1].id}"]})
        i = j
    return out


def P(g):
    """Index of the POSITION STATEMENT heading: the stub reads the rules, not the description above them."""
    return idx(g, sid(g, "POSITION STATEMENT"))


def ps(g, needle):
    return sid(g, needle, P(g))


def before(g, needle):
    return g[idx(g, ps(g, needle)) - 1].id


def reimburse_line(g) -> str:
    """"Reimburse according to operative report." in REIMBURSEMENT INFORMATION, outside every section."""
    return sid(g, "Reimburse according to operative report")


def narrow_answer(g, procedure: dict, unanswerable: bool = False) -> dict:
    """`unanswerable`: the reimbursement line joins every pathway (always_on), so H can make it a requirement."""
    gsv, acc = ps(g, "Great or Small Saphenous Veins"), ps(g, "Accessory Saphenous Veins")
    trib, perf = ps(g, "Symptomatic Varicose Tributaries"), ps(g, "Perforator Veins")
    span = lambda first, last: [{"first": first, "last": last}]
    pathways = [
        {"id": "gsv", "spans": span(gsv, before(g, "Accessory Saphenous Veins")),
         "codes": GSV_CODES, "targets": ["great saphenous vein", "small saphenous vein"]},
        {"id": "accessory", "spans": span(acc, before(g, "Symptomatic Varicose Tributaries")),
         "codes": GSV_CODES, "targets": ["accessory saphenous vein"]},
        {"id": "tributaries", "spans": span(trib, before(g, "Perforator Veins")),
         "codes": ["36470", "36471", "37765", "37766"], "targets": ["varicose tributaries"]},
        {"id": "perforator", "spans": span(perf, before(g, "Telangiectasia")),
         "codes": ["36475", "36476", "36478", "36479", "37760", "37761"], "targets": ["perforator veins", "leg ulcer"]},
    ]
    t = (procedure.get("target") or "").lower()
    chosen = []
    if "great saphenous" in t or "small saphenous" in t:
        chosen.append("gsv")
    if "accessory" in t:
        chosen.append("accessory")
    if "perforator" in t:
        chosen.append("perforator")
    if any(c in ("37765", "37766") for c in procedure.get("cpt") or []):
        chosen.append("tributaries")
    return {"payer": {"name": "Florida Blue", "aliases": ["Blue Cross and Blue Shield of Florida"], "refs": [g[0].id]},
            "no_pathways_reason": None, "codes": codes_of(g), "pathways": pathways,
            "always_on": [{"first": reimburse_line(g), "last": reimburse_line(g)}] if unanswerable else [],
            "chosen": {"pathway_ids": chosen, "mapped_cpt": None, "why_refs": [gsv] if "gsv" in chosen else []}}


def cosmetic_range(g) -> str:
    """The closing limitation of the GSV section, three lines."""
    return rng(g, "Treatment of great or small saphenous veins by surgery, endovenous", "considered cosmetic and does not meet", P(g))


def pathway_ranges(g) -> dict[str, list[dict]]:
    """The stub's own pathway ranges (from narrow_answer), by pathway id."""
    return {p["id"]: p["spans"] for p in narrow_answer(g, {})["pathways"]}


def _lines_in(g, r: dict) -> list:
    ids = [s.id for s in g]
    a, b = ids.index(r["first"]), ids.index(r["last"])
    return g[a: b + 1]


def extra_criteria(g, pid: str) -> tuple[list[dict], str]:
    """Two criteria for a pathway other than gsv: the first two non-heading lines of its first range (ids
    `<pid>_1`, `<pid>_2`, quote = the line's stripped text) and the logic string joining them (v1.2's H shape)."""
    ranges = pathway_ranges(g)[pid]
    first = _lines_in(g, ranges[0])
    body = [s for s in first[1:] if s.text.strip()]
    crit = [{"id": f"{pid}_{i + 1}", "refs": [s.id], "quote": s.text.strip(), "question": "Documented?"}
            for i, s in enumerate(body[:2])]
    return crit, " AND ".join(c["id"] for c in crit)


def asked_pathways(prompt: str) -> tuple[str, ...]:
    """The pathway ids the H prompt asks for: the `- `<pid>`: “…” (lines …)` lines app.checklist.criteria renders."""
    m = re.search(r"## The confirmed indication\(s\)\n\n(.*?)\n\n## ", prompt, re.S)
    found = tuple(dict.fromkeys(re.findall(r"^- `(\w+)`: ", m.group(1) if m else "", re.M)))
    return found or ("gsv",)


def unanswerable_criteria(g, pathways) -> list[dict]:
    """Two requirements no chart can show (answerable: false): the section's own "meets the definition of medical
    necessity" (the plan's judgement) and the reimbursement line (outside the section)."""
    lead = {"gsv": "Treatment of the great or small saphenous veins by surgery", "accessory": "Treatment of accessory saphenous veins by surgery"}
    pid = next((p for p in pathways if p in lead), None)
    out = [{"id": "op_report", "refs": [reimburse_line(g)], "quote": "Reimburse according to operative report",
            "answerable": False, "question": "Is the operative report on file? (claim time; not answerable from a chart)"}]
    if pid:
        i = idx(g, ps(g, lead[pid]))                  # the words wrap onto the next two lines in both sections
        out.insert(0, {"id": "necessity", "refs": [f"{g[i + 1].id}-{g[i + 2].id}"],
                       "quote": "meets the definition of medical necessity", "answerable": False,
                       "question": "Does the plan judge it medically necessary? (the plan's judgement; not answerable from a chart)"})
    return out


def criteria_answer(g, pathways=("gsv",), unanswerable: bool = False) -> dict:
    """v1.2's H answer {notes, criteria, logic[{pathway, logic}]}: the gsv checklist as always; any other asked pathway
    adds two criteria and a logic string (extra_criteria). `unanswerable` ANDs unanswerable_criteria onto every
    asked pathway's logic."""
    d = _gsv_criteria(g) if "gsv" in pathways else {"notes": "", "criteria": [], "logic": []}
    for pid in pathways:
        if pid == "gsv":
            continue
        crit, logic = extra_criteria(g, pid)
        d["criteria"] += crit
        d["logic"].append({"pathway": pid, "logic": logic})
    if unanswerable:
        extra = unanswerable_criteria(g, pathways)
        d["criteria"] += extra
        for e in d["logic"]:
            e["logic"] = f"({e['logic']}) AND " + " AND ".join(c["id"] for c in extra)
    return d


def _gsv_criteria(g) -> dict:
    p = P(g)
    reflux = rng(g, "There is demonstrated saphenous reflux", "class C2* or greater", p)
    size = ps(g, "The varicosities are at least 3 millimeters")
    ulcer, thromb = ps(g, "1. Ulceration secondary"), ps(g, "2. Recurrent superficial")
    hem = ps(g, "3. Hemorrhage")
    sym = rng(g, "4. Persistent pain", "improved the symptoms.", p)
    crit = [
        {"id": "reflux", "refs": [reflux], "quote": "There is demonstrated saphenous reflux", "question": "Reflux on duplex?"},
        {"id": "ceap", "refs": [reflux], "quote": "CEAP (Clinical-Etiology-Anatomy-Pathophysiology) class C2* or greater", "threshold": {"op": ">=", "value": "C2", "unit": "CEAP class"}, "question": "CEAP C2+?"},
        {"id": "size", "refs": [size], "quote": "The varicosities are at least 3 millimeters in size", "threshold": {"op": ">=", "value": 3, "unit": "mm"}, "question": "Varicosities >= 3 mm?"},
        {"id": "ulcer", "refs": [ulcer], "quote": "Ulceration secondary to venous stasis", "question": "Ulcer?"},
        {"id": "thromb", "refs": [thromb], "quote": "Recurrent superficial thrombophlebitis", "question": "Thrombophlebitis?"},
        {"id": "hem", "refs": [hem], "quote": "Hemorrhage or recurrent bleeding episodes from a ruptured superficial varicosity", "question": "Bleeding?"},
        {"id": "symptoms", "refs": [sym], "quote": "Persistent pain, swelling, itching, burning, or other symptoms are associated with saphenous reflux", "question": "Persistent symptoms from reflux?"},
        {"id": "adl", "refs": [sym], "quote": "the symptoms significantly interfere with activities of daily living", "question": "Interfere with daily living?"},
        {"id": "compression", "refs": [sym], "quote": "conservative management including compression therapy for at least 3 months has not improved the symptoms", "threshold": {"op": ">=", "value": 3, "unit": "months"},
         "question": "Compression >= 3 months without improvement, with dates?"},
    ]
    return {"notes": "GSV indication", "criteria": crit,
            "logic": [{"pathway": "gsv", "logic": "reflux AND ceap AND size AND (ulcer OR thromb OR hem OR (symptoms AND adl AND compression))"}]}


def judge_answer(r, override=None) -> dict:
    s = lambda n: sid(r, n)
    reflux = rng(r, "Reflux at saphenofemoral junction 2.4", "reflux along thigh and calf")
    begin = rng(r, "Begin conservative management", "daily, leg elevation")
    cont = rng(r, "Reports consistent daily use", "stockings since the March visit")
    v = {
        "reflux": {"status": "MET", "for": [reflux], "dates": [{"span": reflux, "date": "March 25, 2025"}]},
        "ceap": {"status": "MET", "for": [s("CEAP clinical class C4a (pigmentation")]},
        "size": {"status": "MET", "for": [s("Unchanged varicosities medial left thigh")],
                 "measurements": [{"value": "6", "unit": "mm", "span": s("Unchanged varicosities medial left thigh")}]},
        "ulcer": {"status": "NOT_MET", "against": [s("No ulceration.")]},
        "thromb": {"status": "NOT_MET", "against": [s("Denies history of DVT")]},
        "hem": {"status": "NOT_MET", "against": [s("Denies history of DVT")]},
        "symptoms": {"status": "MET", "for": [s("Symptoms unchanged to slightly worse")]},
        "adl": {"status": "MET", "for": [s("cannot stand for a full shift")]},
        "compression": {"status": "MET", "for": [begin, cont],
                        "dates": [{"span": begin, "date": "March 18, 2025"}, {"span": cont, "date": "July 22, 2025"}]},
    }
    for k, x in (override or {}).items():
        v[k] = x
    return {"verdicts": [{"criterion": k, "confidence": 0.95, "rationale": f"{k} per chart", **x} for k, x in v.items()]}


def order_answer(r, target="left great saphenous vein", cpt=("36475",)) -> dict:
    return {"patient_name": "Maria Elena Delgado", "payer": "Florida Blue PPO",
            "procedure": {"cpt": list(cpt), "as_written": "Endovenous radiofrequency ablation, left great saphenous vein",
                          "target": target, "surgeon": "Dr. Elena Vasquez, MD, FACS"},
            "refs": [sid(r, "ablation, left great saphenous vein"), rng(r, "36475 — Endovenous ablation", "first vein treated")]}


_STOP = {"there", "which", "their", "these", "those", "following", "criteria", "documentation", "least", "other",
         "treatment", "when", "have", "been", "with", "that", "does", "meet", "definition", "medical", "necessity"}
_LEAD = re.compile(r"(one or more of the following|any of the following|either)\b", re.I)
_ITEM = re.compile(r"^\s*([•▪➢❖–\-]|\d+\.|[a-z]\.)\s+")


def _words(t: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{5,}", t.lower()) if w not in _STOP}


def selected_lines(prompt: str) -> list[tuple[str, str]]:
    """The (id, text) pairs app.review.ask renders under "## The selected guideline lines"."""
    m = re.search(r"## The selected guideline lines\n\n(.*?)\n\n## ", prompt, re.S)
    return re.findall(r"^\[(g\d+)\] (.*)$", m.group(1) if m else "", re.M)


def ask_answer(r, prompt: str) -> dict:
    """A plausible, deterministic answer for highlight-to-ask: the selected lines grouped into sentences (a new one
    at a bullet or number, or after a line ending in . ; : AND OR); a short title-like or all-caps group is a heading,
    a code-table row is billing; the rest are parts. A lead-in ("one or more of the following", "either") turns the
    parts after it into alternatives: "A and either B or C" is all(A, any(B, C)). Each part's verdict comes from the
    chart line sharing the most words with it: two or more -> MET, a line opening "No" / "Denies" -> NOT_MET, else
    INSUFFICIENT citing the closest line."""
    lines = selected_lines(prompt)
    groups: list[list[tuple[str, str]]] = []
    for i, t in lines:
        prev = groups[-1][-1][1].rstrip() if groups else ""
        if not groups or _ITEM.match(t) or re.search(r"([.;:]|\bAND|\bOR)$", prev):
            groups.append([(i, t)])
        else:
            groups[-1].append((i, t))
    text = lambda g: " ".join(t.strip() for _, t in g)
    is_head = lambda g: (text(g).isupper() or (len(text(g).split()) <= 6 and not re.search(r"[.;]", text(g))
                                                and not _ITEM.match(g[0][1])))
    is_bill = lambda g: bool(re.match(r"^\s*(\d{4}[0-9A-Z]|[A-Z]\d{4})\b", g[0][1])) or "CPT" in text(g)
    body = [g for g in groups if not is_head(g) and not is_bill(g)]
    if not body:
        kind = "billing" if any(is_bill(g) for g in groups) else "heading"
        return {"chart_can_show": False, "kind": kind, "parts": [], "logic": None, "verdicts": []}
    parts, lead_at = [], None
    for g in body:
        if _LEAD.search(text(g)) and g is not body[-1]:
            lead_at = len(parts)
            continue
        ref = g[0][0] if len(g) == 1 else f"{g[0][0]}-{g[-1][0]}"
        quote = _ITEM.sub("", g[0][1]).strip().rstrip(";,").strip()
        parts.append({"id": f"p{len(parts) + 1}", "refs": [ref], "quote": quote, "question": "Documented?"})
    ids = [p["id"] for p in parts]
    if lead_at is not None and len(ids) - lead_at >= 2:
        alts = {"any": ids[lead_at:]}
        logic = {"all": ids[:lead_at] + [alts]} if lead_at else alts
    else:
        logic = {"all": ids} if len(ids) > 1 else ids[0]
    verdicts = []
    for p, g in zip(parts, [g for g in body if not (_LEAD.search(text(g)) and g is not body[-1])]):
        want = _words(text(g))
        best = max(r, key=lambda s: (len(want & _words(s.text)), -int(s.id[1:])))
        n = len(want & _words(best.text))
        neg = re.match(r"^\s*(no|denies)\b", best.text.strip(), re.I)
        if n and neg:
            verdicts.append({"criterion": p["id"], "status": "NOT_MET", "confidence": 0.9, "rationale": "stub", "against": [best.id]})
        elif n >= 2:
            verdicts.append({"criterion": p["id"], "status": "MET", "confidence": 0.98, "rationale": "stub", "for": [best.id]})
        else:
            verdicts.append({"criterion": p["id"], "status": "INSUFFICIENT", "confidence": 0.6, "rationale": "stub",
                             "for": [best.id] if n else []})
    return {"chart_can_show": True, "kind": "requirement", "parts": parts, "logic": logic, "verdicts": verdicts}


def sections_answer(r) -> dict:
    """Everything before the planned-procedure block is the record; the block itself is the order."""
    plan = idx(r, sid(r, "PLANNED PROCEDURE"))
    return {"sections": [{"title": "record", "label": "evidence", "spans": [{"first": r[0].id, "last": r[plan - 1].id}]},
                         {"title": "PLANNED PROCEDURE", "label": "order", "spans": [{"first": r[plan].id, "last": r[-1].id}]}]}


class Stub:
    def __init__(self, g, r, **kw):
        self.g, self.r, self.kw, self.calls, self.prompts = g, r, kw, [], []

    def __call__(self, run_id, step, prompt, schema, **_):
        self.calls.append(step)
        self.prompts.append((step, prompt))
        if step == "detect_order":
            d = order_answer(self.r, **self.kw.get("order", {}))
        elif step == "narrow_guideline":
            d = narrow_answer(self.g, self._procedure(prompt), self.kw.get("unanswerable", False))
        elif step == "criteria_guideline":
            d = criteria_answer(self.g, asked_pathways(prompt), self.kw.get("unanswerable", False))
            for c in self.kw.get("extra_criteria") or []:     # more criteria (e.g. admin ones), ANDed onto every logic
                d["criteria"].append(c)
                for e in d["logic"]:
                    e["logic"] = f"({e['logic']}) AND {c['id']}"
        elif step == "chart_sections":
            d = self.kw.get("sections") or sections_answer(self.r)
        elif step == "criteria_audit":
            d = self.kw.get("audit", {})
        elif step == "judge_chart":
            d = judge_answer(self.r, self.kw.get("verdicts"))
        elif step == "ask_guideline":
            a = self.kw.get("ask")
            d = a(prompt) if callable(a) else a if a is not None else ask_answer(self.r, prompt)
        else:
            raise AssertionError(step)
        return schema.model_validate(d)

    @staticmethod
    def _procedure(prompt: str) -> dict:
        m = re.search(r"## The request\n\n(\{.*?\n\})", prompt, re.S)
        return json.loads(m.group(1)) if m else {}
