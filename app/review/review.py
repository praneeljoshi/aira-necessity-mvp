"""What the review page reads (GET /api/review/{chart_id}): one document for every state of a check.

    running   the status record only; from the checklist stage until the judge's evidence is in, `preview`
              (preview_view): the confirmed indication's lines, then its requirements' words, never a status
    paused    at pick_code (an order with 2+ codes, before C; app/understand/onecode.py): gate {kind: "pick_code", needs, codes,
              endpoint, split_endpoint}; else
    paused    the gate: the order as the chart words it, every code at the code gate, every section of the
              guideline the coordinator can confirm (its first lines as printed), the model's own picks
    failed    the status record (the failed stage carries the error)
    done      the case: the result, the guideline drawn from tree.build, the requirements in guideline order with
              the position of each quote inside its line and the chart's evidence for each (the page is the
              guideline; the chart appears only as evidence attached to the requirements); a requirement a person
              struck for this case stays in place, marked "struck" with who and why (app/review/strikes.py); one a person
              added carries `added` (app/review/additions.py); `rest` = every other line of the guideline, in order, so
              any of it can be selected and asked about (app/review/ask.py); `source` = the part of the policy each
              requirement's lines come from (source_of), flagged `other` when it is not the confirmed section;
              `why_outside` = for one no chart can show (mark confirm), one sentence of why (outside_why): the page
              offers "Confirmed outside the chart" (an accept: who and when, counted toward sign-off)
              each requirement carries `accepted` (app/review/accepts.py: the accept that still counts, else None) and
              `counted` (it is one the case is built from: not an alternative another option made unneeded);
              `progress` counts them (accepted / to ask / struck / open, `can_sign`), and `packet_accepted` /
              `message` are the packet and the message to the surgeon assembled from accepted items only
    every     `version` (signoff.fingerprint of the case as drawn; sent back with a sign-off), `strike_reasons` (the chips the strike form offers, app/review/strikes.REASONS), `strikes` (strikes.json, undone ones included), `accepts`, `additions` (additions.json, likewise), `probes` (the
              lines asked about, probes.json) and `signoff` (app/review/signoff.view: not_ready / needed / signed, the
              record, whether it went stale, the active strikes and additions the signer sees)
              `code` (the case's one code, else null), `focus` {code, procedure_short, pathway_name, guideline_title}
              once the code is known (pathway_name null until confirmed), `pick_code` (pick_code.json) and `split`
              (split.json: [{from, to, code, by, at}]) — one code, one pathway (app/understand/onecode.py)

Everything here is resolved by code from stored spans and stored results; no model call. Where this module names
things a coordinator reads (section names, marks), the words are the guideline's own or tree.WORDS.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from app import pipeline
from app.checklist import keys
from app.checklist import admin
from app.core import status, store
from app.review import accepts, additions, signoff, strikes, tree
from app.decide import templates as T
from app.decide.evaluate import compile_expr
from app.evidence.judge import is_duration, quote_date
from app.core.models import CriteriaSet, Narrowed, Order, Result, Selection, Span, Verdict
from app.understand.select import pathway_name
from app.ingest.spans import expand, in_range, resolves, table, text_of, wording

LEAD_LINES = 6          # lines of a section shown at the gate: its heading and lead-in
BODY_LINES = 80         # lines of a section shown side by side when two sections are compared
WHY_QUOTES = 3          # chart lines shown under a section as "why it might fit"


# ---------------------------------------------------------------- stored pieces


def confirmation(chart_id: str) -> Optional[dict]:
    """pathways.json (the confirmed section), through store.load_confirmation when the store has it."""
    f = getattr(store, "load_confirmation", None)
    if f is not None:
        return f(chart_id)
    p = store.RESULTS / chart_id / "pathways.json"
    return json.loads(p.read_text()) if p.exists() else None


def selection(chart_id: str) -> Optional[Selection]:
    p = store.RESULTS / chart_id / "selection.json"
    return Selection.model_validate_json(p.read_text()) if p.exists() else None


def chart_exists(chart_id: str) -> bool:
    return bool(store.chart_meta(chart_id)) or status.load_status(chart_id) is not None \
        or (store.RESULTS / chart_id / "result.json").exists()


def order_view(chart_id: str, st: Optional[dict] = None) -> dict:
    o = store.load_order(chart_id)
    if o:
        return {"patient_name": o.patient_name, "procedure_text": o.procedure.as_written, "cpt": o.procedure.cpt,
                "payer": o.payer, "target": o.procedure.target, "surgeon": o.procedure.surgeon}
    so = dict((st or {}).get("order") or {})
    return {"patient_name": so.get("patient_name"), "procedure_text": so.get("procedure_text"), "cpt": so.get("cpt") or [],
            "payer": so.get("payer"), "target": so.get("target"), "surgeon": so.get("surgeon")}


def guideline_view(gid: Optional[str]) -> dict:
    row = next((g for g in store.list_guidelines() if g["id"] == gid), {}) if gid else {}
    return {"id": gid or "", "title": row.get("filename") or gid or "", "payer": row.get("payer") or "",
            "sha": row.get("sha256") or "", "name": row.get("title_text") or "", "number": row.get("number") or "",
            "issuer": row.get("issuer") or row.get("payer") or ""}


def _state(st: Optional[dict], has_result: bool) -> str:
    s = (st or {}).get("state")
    if s in ("paused", "failed", "running"):
        return s
    return "done" if has_result else (s or "running")


def _lines(spans: list[Span], ids: list[str], blank: bool = False) -> list[dict]:
    tbl = table(spans)
    out = []
    for i in expand(ids, tbl):
        s = tbl.get(i)
        if s is None:
            continue
        row = {"id": s.id, "text": s.text, "page": s.page}
        if blank:
            row["blank_before"] = s.blank_before
        out.append(row)
    return out


# ---------------------------------------------------------------- the gate


def gate_view(chart_id: str, st: Optional[dict] = None) -> Optional[dict]:
    """The pause at the section stage, for the person to confirm. None when there is nothing to show (no selection
    stored, or the section the check was narrowed under cannot be found)."""
    st = st if st is not None else status.load_status(chart_id)
    conf = confirmation(chart_id)
    resume = (st or {}).get("resume") or {}
    key = resume.get("key") or (conf or {}).get("narrowed_key")
    sel = selection(chart_id)
    if not key or sel is None:
        return None
    n, _ = store.load_criteria(key)
    o = store.load_order(chart_id)
    gid = (st or {}).get("guideline_id") or (conf or {}).get("guideline_id") or (n.guideline.id if n else None)
    if n is None or o is None or not gid:
        return None
    gspans, _, _ = store.load_guideline_spans(gid)
    try:
        rspans = store.load_chart_spans(chart_id)
    except FileNotFoundError:
        rspans = []
    gt = table(gspans)
    # paused at the gate: the suggestion is this run's (selection.json, written at the pause); pathways.json is the
    # record of a past confirmation and only speaks for a run that was answered (a re-check pauses again)
    answered = conf and not resume
    suggested = [{"code": p["code"], "pathway": p["pathway"]} for p in conf["suggested"]] if answered \
        else [{"code": p.code, "pathway": p.pathway} for p in sel.pathways]
    by_code = {c.code: c for c in n.codes}
    codes = []
    for g in sel.code_gate:
        c = by_code.get(g.code)
        codes.append({"code": g.code, "tag": g.tag, "outcome": g.outcome, "mapped": g.mapped,
                      "description": c.description if c else "", "lines": _lines(gspans, c.refs) if c else []})
    judged = [g.code for g in sel.code_gate if g.outcome == "judge"]
    sugg_ids = {p["pathway"] for p in suggested}
    pathways = []
    for p in n.pathways:
        all_lines = [s for rg in p.spans for s in in_range(gspans, rg)]
        first = in_range(gspans, p.spans[0]) if p.spans else []
        shown = first[:LEAD_LINES]
        pathways.append({"id": p.id, "name": pathway_name(n, p.id, gspans), "codes": p.codes, "targets": p.targets,
                         "suggested": p.id in sugg_ids,
                         "for_codes": [c for c in judged if not p.codes or c in p.codes],
                         "pages": sorted({s.page for s in all_lines}),
                         "lines": [{"id": s.id, "text": s.text, "page": s.page, "blank_before": s.blank_before} for s in shown],
                         "more": max(0, len(all_lines) - len(shown)), "n_lines": len(all_lines),
                         "body": [{"id": s.id, "text": s.text, "page": s.page, "blank_before": s.blank_before} for s in all_lines[:BODY_LINES]],
                         "why": why_fits(p, o, rspans, p.id in sugg_ids),
                         "shares_codes": [c for c in (o.procedure.cpt if o else []) if c in (p.codes or [])]})
    # sections that look alike (the same codes): the page offers to compare their text side by side
    for x in pathways:
        x["alike"] = [y["id"] for y in pathways if y is not x and x["codes"] and sorted(y["codes"]) == sorted(x["codes"])]
    return {"none_chosen": not suggested, "suggested": suggested,
            "order": {"as_written": o.procedure.as_written, "cpt": o.procedure.cpt, "target": o.procedure.target,
                      "patient_name": o.patient_name, "payer": o.payer, "lines": _lines(rspans, o.refs)},
            "codes": codes, "pathways": pathways, "stopped": [c for c in codes if c["outcome"] != "judge"]}


def why_fits(p, o: Order, rspans: list[Span], suggested: bool) -> list[dict]:
    """Distinctive chart lines for a section, for the person confirming it: lines that name one of the section's own
    targets (its vein or side, its indication: "great saphenous vein", "leg ulcer"), the order lines step B read
    first. A line that only repeats the order's code is not evidence for one section over another (every section
    listing the code shares it); the page shows that as a chip ("Shares code 36475", `shares_codes`). Code only, no
    model call; a reading aid, like tree.note_heading. At most WHY_QUOTES."""
    rt = table(rspans)
    order_ids = [i for i in expand(o.refs, rt) if i in rt] if o else []
    targets = [t.lower() for t in (p.targets or []) if len(t) > 3]
    hit = lambda t: any(x in t.lower() for x in targets)
    pick = [i for i in order_ids if hit(rt[i].text)]
    for s in rspans:
        if len(pick) >= WHY_QUOTES:
            break
        if s.id not in pick and hit(s.text):
            pick.append(s.id)
    return [{"id": i, "text": rt[i].text.strip(), "page": rt[i].page, "heading": tree.note_heading(rspans, i),
             "order": i in order_ids} for i in pick[:WHY_QUOTES]]


def nofit(chart_id: str) -> Optional[dict]:
    """nofit.json: a person judged at the gate that no section of the guideline fits this order."""
    p = store.RESULTS / chart_id / "nofit.json"
    return json.loads(p.read_text()) if p.exists() else None


def check_picks(chart_id: str, picks: list[dict]) -> Optional[str]:
    """The same rules pipeline.resume applies, so a bad body is answered before a thread starts: every pathway must
    be a section of the guideline, every code one the order went through the code gate with. None when fine."""
    if not picks:
        return "pick at least one section"
    st = status.load_status(chart_id) or {}
    conf = confirmation(chart_id)
    key = (st.get("resume") or {}).get("key") or (conf or {}).get("narrowed_key")
    sel = selection(chart_id)
    if not key or sel is None:
        return None                     # nothing to check against here; pipeline.resume decides
    n, _ = store.load_criteria(key)
    if n is None:
        return None
    pids = {p.id for p in n.pathways}
    codes = {g.code for g in sel.code_gate}
    bad_p = sorted({str(p.get("pathway")) for p in picks if p.get("pathway") not in pids})
    bad_c = sorted({str(p.get("code")) for p in picks if p.get("code") not in codes})
    out = []
    if bad_p:
        out.append("not a section of this guideline: " + ", ".join(bad_p))
    if bad_c:
        out.append("not a code in this order: " + ", ".join(bad_c))
    return "; ".join(out) or None


# ---------------------------------------------------------------- the case


def _find(quote: Optional[str], text: str) -> Optional[tuple[int, int]]:
    """Where the quote sits in `text` (the cited lines joined), as [start, end). Whitespace and a hyphen broken
    across a line are forgiven, as spans.locate does; case, words and punctuation must match."""
    words = (quote or "").split()
    if not words:
        return None
    pat = r"\s+".join(r"(?:-\s)?".join(re.escape(ch) for ch in w) for w in words)
    m = re.search(pat, text)
    return (m.start(), m.end()) if m else None


def highlights(quote: Optional[str], ids: list[str], gt: dict[str, Span]) -> list[dict]:
    """The quote's position inside each cited line: the lines are stripped and joined with one space (text_of);
    the match is cut at line boundaries and shifted by each line's indent. No quote, or a quote not found: the
    whole stripped text of every line."""
    lines = [gt[i] for i in expand(ids, gt) if i in gt]
    stripped = [s.text.strip() for s in lines]
    indents = [len(s.text) - len(s.text.lstrip()) for s in lines]
    hit = _find(quote, " ".join(stripped))
    if hit is None:
        return [{"id": s.id, "start": ind, "end": ind + len(t)} for s, t, ind in zip(lines, stripped, indents) if t]
    start, end = hit
    out, off = [], 0
    for s, t, ind in zip(lines, stripped, indents):
        a, b = max(start, off), min(end, off + len(t))
        if a < b:
            out.append({"id": s.id, "start": a - off + ind, "end": b - off + ind})
        off += len(t) + 1
    return out


def evidence(v: Optional[Verdict], rspans: list[Span], rt: dict[str, Span]) -> list[dict]:
    """Every citation the judge gave, for and against, as it appears in the chart."""
    if not v:
        return []
    out = []
    for side, cites in (("for", v.for_), ("against", v.against)):
        for c in cites:
            if not resolves(c, rt):
                continue
            ids = expand([c], rt)
            out.append({"span": c, "side": side, "lines": ids, "text": text_of([c], rt), "date": quote_date(v, c, rt),
                        "heading": tree.note_heading(rspans, ids[0]), "page": rt[ids[0]].page})
    return out


CONTRADICTED = {"contradicted", "applies", "part_shown"}


def order_evidence(evs: list[dict], mark: str, duration: bool) -> list[dict]:
    """The quote shown first, the rest behind "more": a contradicted requirement leads with the strongest "against"
    quote (the judge lists them most important first); anything else with the first "for" quote; a duration leads
    with the start note (earliest verified date) and the latest note comes next, so the span of time is the first
    two quotes. Undated quotes keep their order after the dated ones."""
    lead, tail = ("against", "for") if mark in CONTRADICTED else ("for", "against")
    first = [e for e in evs if e["side"] == lead]
    rest = [e for e in evs if e["side"] != lead]
    if duration and lead == "for":
        dated = sorted((e for e in first if e.get("date")), key=lambda e: e["date"])
        undated = [e for e in first if not e.get("date")]
        if len(dated) >= 2:
            dated = [dated[0], dated[-1]] + dated[1:-1]
        first = dated + undated
    return first + rest


def _criteria_for_case(sha: str, o: Optional[Order], conf: Optional[dict],
                       chart_id: Optional[str] = None) -> tuple[Optional[Narrowed], Optional[CriteriaSet]]:
    """The narrowed guideline (the C cache for this order) and the criteria the result was judged with: the copy
    pinned in the case's own folder (data/results/<chart_id>/criteria.json) when there is one; for an older case
    with none, under the confirmed section's own key when a person confirmed one, else the C cache's."""
    n, cs = (None, None)
    if o:
        n, cs = store.load_criteria(keys.case_order_key(sha, o.procedure, chart_id))
    hk = (conf or {}).get("h_key")
    if hk:
        n2, cs2 = store.load_criteria(hk)
        n, cs = n or n2, cs2 or cs
    pinned = store.load_case_criteria(chart_id) if chart_id else None
    return n, pinned or cs


def case_view(chart_id: str) -> dict:
    from app import main as _main               # main imports review_api at import; never at module top here

    rec = store.load_result(chart_id)
    r = Result.model_validate(rec["result"])
    verdicts = {k: Verdict.model_validate(v) for k, v in (rec.get("verdicts") or {}).items()}
    gid = (rec.get("meta") or {}).get("guideline_id") or r.guideline_id
    o = store.load_order(chart_id)
    conf = confirmation(chart_id)
    gspans, sha, _ = store.load_guideline_spans(gid)
    rspans = store.load_chart_spans(chart_id)
    gt, rt = table(gspans), table(rspans)
    n, cs = _criteria_for_case(sha, o, conf, chart_id)
    crit = cs.criterion_map() if cs else {}
    base = cs
    cs, pruned = admin.split(chart_id, cs, r.pathway_used or [])          # admin leaves set aside (app/checklist/admin.py)
    verdicts, _ = admin.verdicts(chart_id, base, verdicts)
    cs, _ = strikes.split(chart_id, cs, gspans, r.pathway_used or [])      # decided without the struck ones
    cs, verdicts, _, added = additions.extend(chart_id, cs, verdicts, {}, r.pathway_used or [])  # and with the added
    if added:
        crit = {**crit, **{c.id: c for c in cs.criteria if c.id in added}}
    t = tree.build(chart_id)
    detail = _main._detail(chart_id)
    items_t = {it["criterion"]: it for b in t["blocks"] for it in b.get("items", [])}

    info: dict[str, dict] = {}
    if cs:
        expr = {e.pathway: e.expr for e in cs.expressions}
        for pid in r.pathway_used or []:
            if pid in expr:
                tree.classify(expr[pid], compile_expr(expr[pid], verdicts), True, info)
    pos = {s.id: i for i, s in enumerate(gspans)}
    reqs = []
    for cid, inf in info.items():
        c, v = crit.get(cid), verdicts.get(cid)
        it = items_t.get(cid)
        mark = it["mark"] if it else tree.mark_of(inf, c, v)
        refs = expand(c.refs, gt) if c else []
        duration = bool(c and is_duration(c.threshold, c))
        reqs.append({"criterion": cid, "words": wording(c, gt) if c else cid, "mark": mark, "say": tree.WORDS[mark],
                     "bad": mark in tree.BAD, "role": inf["role"], "excl": inf.get("excl"), "block": it.get("block") if it else None,
                     "refs": refs, "highlights": highlights(c.quote if c else None, refs, gt), "duration": duration,
                     "evidence": order_evidence(evidence(v, rspans, rt), mark, duration),
                     "added": additions.summary(added[cid]) if cid in added else None})
    for cid, it in items_t.items():          # struck for this case: in place, words marked, who and why, no evidence
        if it["mark"] != "struck" or cid in info:
            continue
        c = crit.get(cid)
        refs = it["refs"]
        reqs.append({"criterion": cid, "words": it["words"], "mark": "struck", "say": it["say"], "bad": False,
                     "role": it["role"], "block": it.get("block"), "refs": refs,
                     "highlights": highlights(c.quote if c else None, refs, gt), "duration": False, "evidence": [],
                     "struck": it["struck"]})
    reqs.sort(key=lambda x: min((pos[i] for i in x["refs"] if i in pos), default=10 ** 9))
    jr = rec.get("jreasons") or {}
    for x in reqs:                           # where in the policy each one comes from
        x["source"] = source_of(x["refs"], n, r.pathway_used or [], gspans)
        # step J's review reasons belong to their requirement (notes for and against, measurements on both sides of
        # a threshold …): the page says them there, not in a block under the header
        x["reasons"] = list(jr.get(x["criterion"]) or [])
        x["why_outside"] = outside_why(x["words"], x["source"]) if x["mark"] == "confirm" else None
    # accepts: a requirement's basis is the run, the checklist, its id and the verdict it is shown with
    run_id, key = r.run_id, cs.key if cs else None
    bases = {x["criterion"]: accepts.basis(run_id, key, x["criterion"], verdicts.get(x["criterion"])) for x in reqs}
    took = accepts.current(chart_id, bases)
    for x in reqs:
        x["basis"] = bases[x["criterion"]]
        a = took.get(x["criterion"]) if x["mark"] != "struck" else None
        # Accept means proof: only a requirement the chart documents is accepted; one the chart does not document
        # yet (or contradicts) is added to the ask instead, the same record, and never counts as accepted
        rec_ = {k: a.get(k) for k in ("id", "by", "at")} if a else None
        # an exclusion (or a part of one) is proof when the chart shows it does not apply to this patient (the
        # exclusion's own status is MET); a requirement when the chart documents it
        x["proof"] = x.get("excl") == "MET" if x.get("role") in ("exclusion", "part") and x["mark"] != "struck" \
            else x["mark"] not in tree.BAD
        if a and a.get("as"):            # decided together with an identical requirement (merge_groups): the person's choice
            x["proof"] = a["as"] == "accept"
        x["accepted"] = rec_ if x["proof"] else None
        x["in_ask"] = None if x["proof"] else rec_
        x["counted"] = x["mark"] not in ("not_needed", "other_option")
        # another route to the same requirement while no option is documented yet (an exemption, "unless
        # contraindicated"): counted, with its own evidence to find; never dimmed as "another option"
        x["route"] = bool((info.get(x["criterion"]) or {}).get("route"))
    # an option made unneeded by a documented one is set aside (dimmed) only once a person accepted that one
    for x in reqs:
        if x["mark"] not in ("not_needed", "other_option"):
            continue
        g = (info.get(x["criterion"]) or {}).get("group")
        sib = [y for y in reqs if y is not x and g and (info.get(y["criterion"]) or {}).get("group") == g and y["counted"] and y["mark"] != "struck"]
        x["dim"] = x["mark"] if any(y.get("accepted") for y in sib) else None
        if x["dim"] is None:
            x["say"] = "Another option has evidence; accept it to set this one aside"
    merge_groups(reqs, gt, pos)
    prog = progress_of(reqs, r)
    # the logic itself, per judged section after strikes and additions, compiled into the outline the Tree view draws
    exprs = {e.pathway: e.expr for e in cs.expressions} if cs else {}
    logic = tree.outline_case([(pid, pathway_name(n, pid, gspans) if n else pid, exprs[pid]) for pid in r.pathway_used or [] if pid in exprs],
                              verdicts, {x["criterion"]: x for x in reqs})
    acc ={x["criterion"] for x in reqs if x["accepted"]}
    in_ask = {x["criterion"] for x in reqs if x["in_ask"]}
    packet_acc = [{"criterion": p.criterion, "label": p.text,
                   "quotes": [{"quote": packet_quote(q.span, rspans, rt), "source": T.fmt_date(q.date) if q.date else "",
                               "note": tree.note_heading(rspans, expand([q.span], rt)[0]) if resolves(q.span, rt) else ""}
                              for q in p.quotes]}
                  for p in r.packet if p.criterion in acc]
    message = ""
    took_miss = [m for m in r.misses if m.criterion in in_ask]
    if took_miss and o:
        bad = {x["criterion"] for x in reqs if x["mark"] in ("contradicted", "applies", "part_shown")}
        payer = (n.guideline.payer.name if n else "") or "the payer"
        message = T.addendum(T.salutation(o.procedure.surgeon), o.patient_name or "this patient", T.procedure_phrase(o),
                             payer, [m.ask for m in took_miss], [], any(m.criterion in bad for m in took_miss),
                             [x["words"] for x in reqs if x["accepted"] and x["mark"] == "documented"])
    rest = rest_of(t, gspans)

    # admin leaves pruned for this case: never asked, counted or signed for; listed at the foot of the page
    set_aside = []
    for cid, why in pruned.items():
        c = crit.get(cid)
        refs = expand(c.refs, gt) if c else []
        set_aside.append({"criterion": cid, "words": wording(c, gt) if c else cid, "refs": refs, "why": why,
                          "source": source_of(refs, n, r.pathway_used or [], gspans)})
    set_aside.sort(key=lambda x: min((pos[i] for i in x["refs"] if i in pos), default=10 ** 9))

    return {"set_aside": set_aside, "result": detail.get("result"), "ask": detail.get("ask", ""), "packet": detail.get("packet", []),
            "surgeon": detail.get("surgeon"), "tree": t, "requirements": reqs, "rest": rest,
            "chart": {"filename": store.chart_meta(chart_id).get("filename"), "pages": len({s.page for s in rspans})},
            "confirmation": conf, "h_key": (conf or {}).get("h_key"), "progress": prog,
            "packet_accepted": packet_acc, "message": message, "logic": logic}


def _first_words(text: str, n: int = 5) -> str:
    """The first few words of a cited line, list glyphs and numbering set aside, for a citation with no heading."""
    t = re.sub(r"^\s*(?:[•·\-–*]|\d+[.)]|[a-z][.)])\s*", "", text or "").strip()
    w = t.split()
    return " ".join(w[:n]).rstrip(",;:") + ("…" if len(w) > n else "")


def source_of(refs: list[str], n: Optional[Narrowed], pids: list[str], gspans: list[Span]) -> Optional[dict]:
    """Where a requirement's lines sit in the policy, as a plain citation under its words: the policy's own heading
    for that part and the page ("Cited: Great or Small Saphenous Veins, p. 2", "Cited: Reimbursement information,
    p. 7"), or, with no heading, the cited line's first words in quotes. `line` is the line the citation points at
    (the page scrolls there), `pathway` the indication cited, if any (the page names it by the gate's own label),
    `other` is true when it lies outside the confirmed indication (a warm dot, no
    commentary). Code only, from the step C ranges and the spans; the first line outside the confirmed indication
    decides. None without lines or a narrowed guideline."""
    from app.review.ask import heading_above              # ask imports this module's callers; never at module top

    pos = {s.id: i for i, s in enumerate(gspans)}
    ids = [i for i in refs if i in pos]
    if not ids or n is None:
        return None

    def inside(rgs, i: str) -> bool:
        return any(r.first in pos and r.last in pos and pos[r.first] <= pos[i] <= pos[r.last] for r in rgs)

    def cite(part: Optional[str], line: str, other: bool, pathway: Optional[str] = None) -> dict:
        page = gspans[pos[line]].page
        name = part or f"“{_first_words(gspans[pos[line]].text)}”"
        return {"other": other, "part": part, "page": page, "line": line, "pathway": pathway,
                "say": f"Cited: {name}" + (f", p. {page}" if page is not None else "")}

    pw = {p.id: p for p in n.pathways}
    mine = [p for p in pids if p in pw]
    home = next((p for p in mine if all(inside(pw[p].spans, i) for i in ids)), None)
    if home:
        return cite(pathway_name(n, home, gspans), ids[0], False, home)
    out = next(i for i in ids if not any(inside(pw[p].spans, i) for p in mine))
    sib = next((p for p in n.pathways if p.id not in mine and inside(p.spans, out)), None)
    if sib and not inside(n.guideline.always_on, out):
        return cite(pathway_name(n, sib.id, gspans), out, True, sib.id)
    return cite(heading_above(gspans, pos[out]), out, True)


# why a chart cannot show a requirement, in one sentence: by what its words are about (the first that matches), then
# the part of the policy it comes from. A reading aid made by code, like tree.note_heading; never a ruling.
_OUTSIDE = [
    (re.compile(r"medical(ly)? necess|judg|discretion|case[- ]by[- ]case|appropriate", re.I),
     "This is the plan's judgement, not something a case records."),
    (re.compile(r"\bFDA\b|approved|cleared|device|label", re.I), "This is a fact about the device, kept outside the case."),
    (re.compile(r"credential|certif|accredit|licens|board|facility|registry|participat", re.I),
     "This is about the provider or the facility, not something a case records."),
    (re.compile(r"reimburs|operative report|claim|bill|report(ed)? (under|with|only)|\bcodes?\b", re.I),
     "This is settled when the claim is paid, after the procedure; a case can't show it beforehand."),
    (re.compile(r"benefit|contract|\bmember|\bplan\b|coverage", re.I), "This depends on the member's plan, not something a case records."),
]


def outside_why(words: str, source: Optional[dict] = None) -> str:
    for pat, say in _OUTSIDE:
        if pat.search(words or ""):
            return say
    part = ((source or {}).get("part") or "").lower()
    for pat, say in _OUTSIDE:
        if part and pat.search(part):
            return say
    return "A case doesn't record this; confirm it with the plan or the practice."


_END = re.compile(r"[.!?][\"”’)]*$")


def packet_quote(cite: str, rspans: list[Span], rt: dict[str, Span], reach: int = 2) -> str:
    """A packet quote reads as whole sentences: the cited lines, carried on through up to `reach` following lines of
    the same note until a sentence ends; if none ends there, the quote stops cleanly with an ellipsis. Runs of spaces
    from a table become " · ". The words are still the chart's own, resolved from the citation by code."""
    if not resolves(cite, rt):
        return ""
    ids = expand([cite], rt)
    pos = {x.id: i for i, x in enumerate(rspans)}
    text = text_of(ids, rt)
    i = pos[ids[-1]]
    for j in range(i + 1, min(len(rspans), i + 1 + reach)):
        if _END.search(text.strip()) or rspans[j].blank_before:
            break
        nxt = rspans[j].text.strip()
        cut = re.search(r"^(.*?[.!?])(\s|$)", nxt)
        text += " " + (cut.group(1) if cut else nxt)
        if cut:
            break
    text = re.sub(r"\s{3,}", " · ", text.strip())
    text = re.sub(r"\s+", " ", text)
    return text if _END.search(text) else text.rstrip(" ,;:·") + "…"


_JOIN = re.compile(r"^(?:[\W_]|\b(?:and|or)\b)*$", re.I)       # whitespace, punctuation, and / or / AND / ;


_ITEM = re.compile(r"^\s*(?:[•▪➢❖–\-]|\d+\.|[a-z]\.)\s")      # as the page starts a new paragraph (static/review.js ITEM)


def rest_of(t: dict, gspans: list[Span]) -> list[dict]:
    """Every line of the guideline the drawn sections (and code rows) do not show, in order: `case.rest`."""
    shown = {ln["id"] for sec in t.get("sections", []) for ln in sec["lines"]} | \
            {ln["id"] for cd in t.get("codes", []) for ln in cd.get("lines", [])}
    return [{"id": sp.id, "text": sp.text, "page": sp.page, "blank_before": sp.blank_before} for sp in gspans if sp.id not in shown]


PREVIEW_STAGES = ("checklist", "record", "read", "verify")


def preview_view(chart_id: str, st: Optional[dict]) -> Optional[dict]:
    """What the case page may draw while a confirmed check runs, before the judge's evidence (the owner's progressive
    page). While H builds: {phase: "guideline", guideline: {tree: {sections, codes, blocks: []}, rest: []}}, the
    confirmed indication's lines as tree.layout draws them, unfolded (no rest). Once the checklist exists (draft.json
    carries it; stages record / read / verify): {phase: "highlights", guideline: {tree, rest}, marks}: the same
    layout with each requirement's block (`blocks` [{id, lines, items: [{criterion}]}], no status) and `rest` as
    case.rest, and `marks` = the requirements' word runs exactly as case.requirements carries them (criterion, refs,
    block, highlights, same, near: review.highlights + merge_groups). No status, verdicts, packet, counts, asks or
    set-aside list. None in any other state or stage."""
    if not st or st.get("state") != "running" or st.get("current") not in PREVIEW_STAGES:
        return None
    d = store.load_case_draft(chart_id)
    if d is None:
        return None
    run_id, sel, cs = d
    if run_id and st.get("run_id") and run_id != st["run_id"]:
        return None                      # another run's draft
    gid = st.get("guideline_id")
    if not gid:
        return None
    used = [p.pathway for p in sel.pathways]
    used = list(dict.fromkeys(used))
    gspans, _, _ = store.load_guideline_spans(gid)
    gt = table(gspans)
    if cs is None:
        t = tree.layout(chart_id, gid, sel, used, {}, [], None, use_pinned=False)
        return {"phase": "guideline", "guideline": {"tree": _neutral_tree(t), "rest": []}}
    t = tree.layout(chart_id, gid, sel, used, {}, [], cs, use_pinned=False)
    crit = cs.criterion_map()
    pos = {s.id: i for i, s in enumerate(gspans)}
    reqs = []
    for b in t["blocks"]:
        for it in b["items"]:
            if it["mark"] == "struck":
                continue
            c = crit.get(it["criterion"])
            refs = it["refs"]
            reqs.append({"criterion": it["criterion"], "words": it["words"], "refs": refs, "block": b["id"],
                         "highlights": highlights(c.quote if c else None, refs, gt), "counted": True})
    reqs.sort(key=lambda x: min((pos[i] for i in x["refs"] if i in pos), default=10 ** 9))
    merge_groups(reqs, gt, pos)
    marks = [{k: x[k] for k in ("criterion", "refs", "block", "highlights", "same", "near") if k in x} for x in reqs]
    return {"phase": "highlights", "guideline": {"tree": _neutral_tree(t), "rest": rest_of(t, gspans)}, "marks": marks}


def _neutral_tree(t: dict) -> dict:
    """tree.layout's drawing data with every status left out: sections (lines with id, text, page, blank_before,
    kind, block), codes, and blocks as {id, lines, items: [{criterion}]}."""
    return {"sections": t["sections"], "codes": t["codes"],
            "blocks": [{"id": b["id"], "lines": b["lines"], "items": [{"criterion": it["criterion"]} for it in b["items"]
                                                                      if it["mark"] != "struck"]} for b in t["blocks"]]}


def merge_groups(reqs: list[dict], gt: dict, pos: dict) -> None:
    """We don't judge, the human does: requirements whose quoted words are identical (the same highlights, or the same
    words) are ONE item (`same`: their ids, first first), decided together; ones that overlap or sit back to back
    (only whitespace, punctuation, and / or between) show as one continuous highlight and one row (`near`: the first
    id of each identical group in the run). Both are set only on requirements the case is built from."""
    live = [x for x in reqs if x.get("counted")]
    par = {x["criterion"]: x["criterion"] for x in live}

    def find(i):
        while par[i] != i:
            i = par[i]
        return i
    seen: dict = {}
    for x in live:
        hs = frozenset((h["id"], h["start"], h["end"]) for h in x["highlights"]) or frozenset(x["refs"])
        for key in ((hs,) if hs else ()) + (("w", re.sub(r"[^a-z0-9]+", " ", x["words"].lower()).strip()),):
            j = seen.setdefault(key, x["criterion"])
            par[find(x["criterion"])] = find(j)
    order = {x["criterion"]: n for n, x in enumerate(reqs)}
    by = {x["criterion"]: x for x in live}
    units: dict[str, list[str]] = {}
    for x in live:
        units.setdefault(find(x["criterion"]), []).append(x["criterion"])
    units = {ms[0]: sorted(ms, key=order.get) for ms in units.values()}            # keyed by the first id

    def joined(h1, h2):                       # h1 first; overlapping, or only a joiner between them
        if h1["id"] == h2["id"]:
            if h1["start"] > h2["start"]:
                h1, h2 = h2, h1
            return h2["start"] < h1["end"] or bool(_JOIN.match(gt[h1["id"]].text[h1["end"]:h2["start"]]))
        a, b = (h1, h2) if pos.get(h1["id"], -1) < pos.get(h2["id"], -1) else (h2, h1)
        # the next line must carry on the same item: a new bullet or number starts another requirement
        return pos.get(b["id"], -2) == pos.get(a["id"], -3) + 1 and not _ITEM.match(gt[b["id"]].text) and bool(_JOIN.match(gt[a["id"]].text[a["end"]:] + gt[b["id"]].text[:b["start"]]))
    heads = sorted(units, key=order.get)
    hl = {u: [h for m in units[u] for h in by[m]["highlights"] if h["id"] in gt] for u in heads}
    cp = {u: u for u in heads}

    def cfind(i):
        while cp[i] != i:
            i = cp[i]
        return i
    for i, u in enumerate(heads):
        for v in heads[i + 1:]:
            if any(joined(a, b) for a in hl[u] for b in hl[v]):
                cp[cfind(v)] = cfind(u)
    for u in heads:
        run = [v for v in heads if cfind(v) == cfind(u)]
        for i in units[u]:
            if len(units[u]) > 1:
                by[i]["same"] = units[u]
            if len(run) > 1:
                by[i]["near"] = run


def progress_of(reqs: list[dict], r: Result) -> dict:
    """How far the case is built. Of the requirements it is built from: the ones the chart documents (`total`), how
    many of those a person accepted, how many are struck, and the ones the chart does not document yet or
    contradicts (`asks`), of which `in_ask` were added to the message to the surgeon and `to_ask` not yet (`to_ask_by`:
    missing / contradicted / applies). `of` = every counted requirement not struck (the "4 of 6 accepted"). `open` =
    documented ones not accepted yet. A case can be signed off when its result is ready, every documented requirement
    is accepted and nothing is in the ask or left to ask."""
    counted = [x for x in reqs if x.get("counted", x["mark"] not in ("not_needed", "other_option"))]
    live = [x for x in counted if x["mark"] != "struck"]
    struck = [x for x in counted if x["mark"] == "struck"]
    proof = [x for x in live if x.get("proof", x["mark"] not in tree.BAD)]
    asks = [x for x in live if not x.get("proof", x["mark"] not in tree.BAD)]
    open_ = [x["criterion"] for x in proof if not x.get("accepted")]
    in_ask = sum(1 for x in asks if x.get("in_ask") and (x.get("same") or [x["criterion"]])[0] == x["criterion"])
    # what is still to ask, split by why: not in the chart (or can't tell), contradicted, or an exclusion that applies
    kind = {"missing": "missing", "unclear": "missing", "contradicted": "contradicted", "part_shown": "contradicted",
            "not_covered": "contradicted", "applies": "applies"}
    by = {"missing": 0, "contradicted": 0, "applies": 0}
    for x in asks:
        if not x.get("in_ask") and (x.get("same") or [x["criterion"]])[0] == x["criterion"]:
            by[kind.get(x["mark"], "missing")] += 1
    one = lambda x: x["criterion"] == (x.get("same") or [x["criterion"]])[0]          # identical requirements count once
    return {"total": sum(map(one, proof)), "of": sum(map(one, live)), "to_ask_by": by,
            "accepted": sum(1 for x in proof if x.get("accepted") and one(x)), "struck": sum(map(one, struck)),
            "in_ask": in_ask, "to_ask": sum(map(one, asks)) - in_ask, "open": open_, "asks": [x["criterion"] for x in asks],
            "can_sign": signoff.ready(r.model_dump()) and not open_ and not asks}


def lane(chart_id: str) -> dict:
    """What the rail needs to put a finished case in the "In the ask" lane: how many requirements are in the ask and
    since when (the earliest still in it); `removed_missing` = removals of requirements not in the chart. Cheap when nobody accepted anything yet (no accepts.json)."""
    o = store.load_order(chart_id)
    surgeon = o.procedure.surgeon if o else None
    st = status.load_status(chart_id) or {}
    base = {"surgeon": surgeon, "section": section_names(chart_id), "updated_at": st.get("ended_at") or st.get("started_at")}
    # removals of requirements the chart did not document: the rail row keeps saying so, signed or not
    base["removed_missing"] = len(signoff.gap_strikes(chart_id))
    if not accepts.active(chart_id):
        return {"in_ask": 0, "in_ask_since": None, **base}
    try:
        reqs = case_view(chart_id)["requirements"]
    except Exception:                                   # a half-written case: the rail must not fail
        return {"in_ask": 0, "in_ask_since": None, **base}
    ats = sorted(x["in_ask"]["at"] for x in reqs if x.get("in_ask") and x["in_ask"].get("at"))
    return {"in_ask": sum(1 for x in reqs if x.get("in_ask")), "in_ask_since": ats[0] if ats else None, **base}


def section_names(chart_id: str) -> list[str]:
    """The section(s) a person confirmed for this case, by name (what tells two checks of one patient apart)."""
    conf = confirmation(chart_id)
    if not conf or not conf.get("confirmed"):
        return []
    n, _ = store.load_criteria(conf.get("narrowed_key") or "")
    try:
        gspans = store.load_guideline_spans(conf["guideline_id"])[0]
    except (FileNotFoundError, KeyError):
        return []
    return list(dict.fromkeys(pathway_name(n, p["pathway"], gspans) if n else p["pathway"] for p in conf["confirmed"]))


def progress(chart_id: str) -> dict:
    return case_view(chart_id)["progress"]


# ---------------------------------------------------------------- what is copied: the payer packet, and the internal audit note


def pretty_heading(h: Optional[str]) -> str:
    """A note heading as a person names it, as the page does (review.js prettyHeading): "Visit Date: September 30,
    2025 | Attending: … | Type: Follow-Up" -> "Follow-Up visit, September 30, 2025"; "7. PHYSICAL EXAM" -> "Physical Exam"."""
    if not h:
        return ""
    out = []
    for part in h.split(" › "):
        m = re.match(r"^Visit Date:\s*([^|]+?)\s*(?:\|.*?)?(?:\|\s*Type:\s*(.+))?$", part, re.I)
        if m:
            out.append((m.group(2).strip() + " visit, " if m.group(2) else "Visit of ") + m.group(1).strip())
            continue
        part = re.sub(r"^\d+\.\s+", "", part)
        out.append(re.sub(r"\b([A-Z]{2,})(?=[\sA-Z&/-]*$)", lambda w: w.group(1)[0] + w.group(1)[1:].lower(), part))
    return " › ".join(out)


def _day(at: Optional[str]) -> str:
    try:
        return T.fmt_date((at or "")[:10]) if at else ""
    except ValueError:
        return ""


def _dot(w: Optional[str]) -> str:
    return re.sub(r"\.$", "", str(w or ""))


def _head(order: dict) -> str:
    return f"{order.get('patient_name') or ''}, {order.get('procedure_text') or ''} ({', '.join(order.get('cpt') or [])}), {order.get('payer') or ''}"


def packet_text(order: dict, case: dict, so: dict) -> str:
    """The payer packet: the accepted requirements with their chart quotes (note and date), what was confirmed outside
    the chart and by whom, and the signer when signed off. Nothing about removals: those are internal (audit_note)."""
    reqs = {x["criterion"]: x for x in case.get("requirements") or []}
    lines = [f"Prior authorization — {_head(order)}", "Supporting documentation:"]
    for i, p in enumerate(case.get("packet_accepted") or [], 1):
        lines.append(f"{i}. {_dot(p.get('label'))}.")
        qs = p.get("quotes") or []
        for q in qs:
            bits = [b for b in (pretty_heading(q.get("note")), q.get("source")) if b]
            lines.append(f'   "{q.get("quote")}"' + (f"\n   — {', '.join(bits)}" if bits else ""))
        r = reqs.get(p.get("criterion")) or {}
        if not qs and r.get("mark") == "confirm" and r.get("accepted"):
            a = r["accepted"]
            lines.append(f"   Confirmed outside the case by {a.get('by') or 'a person'}" + (f", {_day(a.get('at'))}" if a.get("at") else "") + ".")
    rec = so.get("record") or {}
    if so.get("state") == "signed":
        lines.append(f"Signed off by {rec.get('by')} on {_day(rec.get('at'))}.")
    return "\n".join(lines)


def audit_note(chart_id: str, order: dict, so: dict) -> str:
    """The internal audit note (never sent to the payer): every requirement removed for this case, with the reason,
    who and when, and whether the chart documented it; the lines added; who signed off and whether they checked the
    removals. Empty when nothing was removed or added."""
    from app.review.tree import BAD
    gone, added = strikes.active(chart_id), additions.active(chart_id)
    if not gone and not added:
        return ""
    lines = [f"Audit note (internal, not for the payer) — {_head(order)}"]
    if gone:
        lines.append("Removed for this case:")
        for k in gone:
            lab, note = strikes.LABELS.get(k.get("code") or ""), str(k.get("reason") or "").strip()
            why = (f"{lab}: “{note}”" if note and note != lab else lab) if lab else note
            who = f" (removed by {k.get('by')}" + (f", {_day(k.get('at'))}" if k.get("at") else "") + ")" if k.get("by") else ""
            gap = " — this requirement was not documented in the case." if k.get("was") in BAD else ""
            lines.append(f"- “{_dot(k.get('words'))}”: {why}{who}{gap}")
    if added:
        lines.append("Added for this case:")
        for x in added:
            lines.append(f"- “{_dot(x.get('words'))}”" + (f" (added by {x.get('by')}" + (f", {_day(x.get('at'))}" if x.get("at") else "") + ")" if x.get("by") else ""))
    rec = so.get("record") or {}
    if so.get("state") == "signed":
        n = so.get("gaps") or 0
        lines.append(f"Signed off by {rec.get('by')} on {_day(rec.get('at'))}"
                     + (f"; they checked the {n} requirement{'s' if n > 1 else ''} removed while not in the case." if n else "."))
    return "\n".join(lines)


# ---------------------------------------------------------------- the one document


def review_doc(chart_id: str) -> Optional[dict]:
    """None when neither a status nor a result exists for the id."""
    from app.review import ask, feedback

    st = status.load_status(chart_id)
    has_result = (store.RESULTS / chart_id / "result.json").exists()
    if st is None and not has_result:
        return None
    state = _state(st, has_result)
    gid = (st or {}).get("guideline_id")
    if not gid and has_result:
        rec = store.load_result(chart_id)
        gid = (rec.get("meta") or {}).get("guideline_id") or rec["result"].get("guideline_id")
    conf = confirmation(chart_id)
    from app.understand import onecode
    pc = onecode.load(chart_id)
    if onecode.waiting(st):          # one code, one pathway: which code first (app/understand/onecode.py); C has not run
        g = next((s.get("gate") for s in st["stages"] if s["id"] == "order"), None) or {}
        gate = {"kind": "pick_code", "needs": g.get("needs"), "codes": (pc or {}).get("codes") or g.get("codes") or [],
                "endpoint": f"/api/review/{chart_id}/code", "split_endpoint": f"/api/review/{chart_id}/split"}
    else:
        gate = gate_view(chart_id, st) if state == "paused" or conf else None
    case = case_view(chart_id) if has_result else None
    # the version of the case this document shows (signoff.fingerprint: result, meta, strikes, additions, accepts);
    # the page sends it with a sign-off, which the server refuses when the case has changed since
    version = signoff.fingerprint(chart_id) if has_result else None
    order = order_view(chart_id, st)
    so = dict(signoff.view(chart_id), progress=case["progress"] if case else None,
              can_sign=bool(case and case["progress"]["can_sign"])) if state == "done" else {
        "state": "not_ready", "ready": False, "signed": False, "record": signoff.load(chart_id), "stale": False,
        "strikes": [], "additions": [], "gaps": 0}
    if case is not None:
        # what the page copies: the payer packet (accepted items, the signer; no removals) and, apart, the audit note
        case["packet_text"] = packet_text(order, case, so)
        case["audit_note"] = audit_note(chart_id, order, so)
    code = onecode.case_code(chart_id)
    if case is not None:
        case["code"] = code
    focus = onecode.focus(chart_id, section_names(chart_id) if conf else [],
                          (lambda g: g["name"] or g["title"] or None)(guideline_view(gid)))
    doc = {"chart_id": chart_id, "state": state, "version": version, "status": st, "order": order,
            "code": code, "focus": focus, "pick_code": pc, "split": onecode.load(chart_id, "split.json") or [],
            "guideline": guideline_view(gid), "gate": gate, "case": case, "confirmation": conf,
            "feedback": feedback.list_for(chart_id), "strikes": strikes.load(chart_id),
            "strike_reasons": [{"code": c, "label": w} for c, w in strikes.REASONS],
            "additions": additions.load(chart_id), "probes": ask.probes(chart_id), "accepts": accepts.load(chart_id),
            "nofit": (lambda x: x if x and x.get("guideline_id") == gid else None)(nofit(chart_id)),
            "guidelines": [{"id": g["id"], "payer": g.get("payer") or "", "title": g.get("filename") or g["id"],
                            "name": g.get("title_text") or "", "number": g.get("number") or "", "issuer": g.get("issuer") or ""}
                           for g in store.list_guidelines() if g["id"] != gid],
            "signoff": so}
    pv = preview_view(chart_id, st) if state == "running" else None
    if pv is not None:
        doc["preview"] = pv          # the progressive case page, before the judge's evidence (absent once finished)
    return doc
