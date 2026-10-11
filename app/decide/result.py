"""Steps K and L (code): compile each code's pathways over the verdicts, decide, and write the ask, the packet and
the checklist from resolved spans only.

Queues: ready = MET with no review reasons · review = everything else with a determination · cant_check = no
pathways, a code that stops, no guideline.
"""
from __future__ import annotations

from typing import Optional

from app.decide import templates as T
from app.decide.evaluate import compile_expr, leaves, missing, path_nodes, rank, weakest
from app.evidence.judge import is_duration, quote_date
from app.core.models import (CheckItem, CriteriaSet, Miss, Narrowed, NodeResult, Order, PacketItem, Quote, Result, Selection,
                     Span, Verdict)
from app.understand.select import pathway_name
from app.ingest.spans import expand, resolves, table, text_of, wording

REVIEW_CONFIDENCE = 0.70


def _payer(n: Narrowed) -> str:
    return n.guideline.payer.name or "the payer"


def _quotes(v: Optional[Verdict], rt: dict[str, Span], duration: bool) -> list[Quote]:
    """One quote per citation: the cited lines joined (a range reads as one sentence). A quote's date is the verified
    date the judge gave for that span (judge.quote_date)."""
    if not v:
        return []
    ids = v.for_ if v.status != "NOT_MET" else v.against
    ids = [c for c in (ids or v.for_ or v.against) if resolves(c, rt)]
    if not ids:
        return []

    def when(cite: str) -> Optional[str]:
        return quote_date(v, cite, rt)

    pick = [ids[0]]
    if len(ids) > 1 and (duration or v.status == "INSUFFICIENT") and when(ids[-1]) != when(ids[0]):
        pick.append(ids[-1])
    return [Quote(span=c, text=text_of([c], rt), date=when(c)) for c in pick]


def _stop(order: Order, n: Optional[Narrowed], gid: str, determination: str, reason: str, ask: str,
          reasons: list[str], run_id: Optional[str]) -> Result:
    return Result(order_id=order.id, guideline_id=gid, determination=determination, reason=reason, queue="cant_check",
                  ask=ask, review_reasons=reasons, run_id=run_id)



def _items(x: NodeResult) -> list[tuple[list[str], str, str]]:
    """([criterion ids], status, prefix) rows for one node on the deciding path.

    not(requirement)      one row: the requirement, prefixed "Must not apply"
    not(all(a, b))        a compound exclusion ("X without Y"): one row per part, each its own criterion
    not(any(a, b, ...))   a list ("none of the following"): one row per item; when it fails, only the items the
                          chart shows (NOT_MET) or cannot rule out (INSUFFICIENT)"""
    if x.type != "not":
        return [([x.criterion or ""], x.status, "")]
    child = x.children[0]
    if child.type == "leaf":
        return [([child.criterion or ""], x.status, "Must not apply: ")]
    if child.type == "all":          # a compound exclusion ("X without Y"): each part is its own criterion and row
        flip = {"MET": "NOT_MET", "NOT_MET": "MET", "INSUFFICIENT": "INSUFFICIENT"}
        return [([l.criterion or ""], flip[l.status], "Must not apply: ") for l in leaves(child)]
    rows: list[tuple[list[str], str, str]] = []
    for k in child.children:
        sub = [([l.criterion or "" for l in leaves(k)], k.status)]
        for ids, kst in sub:
            item = {"MET": "NOT_MET", "NOT_MET": "MET", "INSUFFICIENT": "INSUFFICIENT"}[kst]
            rows.append((ids, item, "Must not apply: "))
    if x.status != "MET":
        want = "NOT_MET" if x.status == "NOT_MET" else "INSUFFICIENT"
        rows = [r for r in rows if r[1] == want] or rows
    return rows


def decide(order: Order, n: Narrowed, sel: Selection, cs: Optional[CriteriaSet], verdicts: dict[str, Verdict],
           jreasons: dict[str, list[str]], gspans: list[Span], rspans: list[Span], run_id: Optional[str] = None) -> Result:
    gid = n.guideline.id
    payer = _payer(n)
    who = T.salutation(order.procedure.surgeon)
    patient = order.patient_name or "this patient"
    proc = T.procedure_phrase(order)
    gt, rt = table(gspans), table(rspans)
    pre = list(sel.reasons)
    if n.problems:
        pre.append("Part of the guideline could not be read cleanly for this order; open “How this was decided” "
                   "before relying on it.")

    # E and F
    if not sel.applies:
        return _stop(order, n, gid, "CANT_CHECK", sel.reason,
                     f"Can't check this order against {payer}'s guideline. It says: “{T.short(sel.reason, 300)}”", pre, run_id)
    stopped = [g for g in sel.code_gate if g.outcome != "judge"]
    if stopped:
        nc = [g for g in stopped if g.outcome == "not_covered"]
        if nc:
            by = {c.code: c for c in n.codes}
            listed = "; ".join(f"{g.code} as {g.tag.replace('_', '-')} (“{T.short(by[g.code].description, 160)}”)" for g in nc)
            return _stop(order, n, gid, "NOT_COVERED", sel.reason, T.not_covered(who, patient, proc, payer, listed), pre, run_id)
        return _stop(order, n, gid, "CANT_CHECK", sel.reason, f"Can't check this order: {sel.reason}.", pre, run_id)

    # G with nothing picked: ask which section
    if not sel.pathways:
        opts = [pathway_name(n, p, gspans) for c in sel.candidates for p in sel.candidates[c]]
        return Result(order_id=order.id, guideline_id=gid, determination="INSUFFICIENT", queue="review",
                      reason="The order does not say which indication of the guideline it falls under.",
                      review_reasons=pre, ask=T.which_section(who, patient, proc, payer, list(dict.fromkeys(opts))),
                      run_id=run_id)

    # K
    crit = cs.criterion_map() if cs else {}
    expr = {e.pathway: e.expr for e in (cs.expressions if cs else [])}
    trees: dict[str, NodeResult] = {}
    for pid in dict.fromkeys(p.pathway for p in sel.pathways):
        if pid in expr:
            trees[pid] = compile_expr(expr[pid], verdicts)
    reasons = pre[:]
    if cs and cs.status == "needs_review":
        reasons.append("The requirements for this indication could not be fully built from the guideline; read the "
                       "section under “How this was decided” before relying on the checklist.")
    no_tree = [p for p in dict.fromkeys(x.pathway for x in sel.pathways) if p not in trees]
    if no_tree:
        reasons.append("No requirements were built for: " + "; ".join(f"“{pathway_name(n, p, gspans)[:90]}”" for p in no_tree) + ".")
    per_code: list[tuple[str, NodeResult]] = []
    for code in dict.fromkeys(p.code for p in sel.pathways):
        mine = [(p.pathway, trees[p.pathway]) for p in sel.pathways if p.code == code and p.pathway in trees]
        if mine:
            per_code.append(min(mine, key=lambda x: rank(x[1])))   # several pathways for one code: weakest decides
    if not per_code:
        return Result(order_id=order.id, guideline_id=gid, determination="INSUFFICIENT", queue="review",
                      reason="No requirements could be built for this order.", review_reasons=reasons,
                      ask="Nothing to send yet: the requirements could not be built. Open “How this was decided”.",
                      run_id=run_id)
    deciding = weakest([t for _, t in per_code])
    dpid = next(p for p, t in per_code if t is deciding)
    status = deciding.status
    used = list(trees)

    # checklist over every judged pathway's deciding path
    checklist: list[CheckItem] = []
    confirm: list[str] = []          # the reasons that only ask a person to confirm, outside the chart, what no chart shows
    seen: set[str] = set()
    nodes_on_path = [x for t in trees.values() for x in path_nodes(t)]
    for x, (ids, st, prefix) in [(x, it) for x in nodes_on_path for it in _items(x)]:
        cid = ids[0]
        if cid in seen:
            continue
        seen.add(cid)
        c = crit.get(cid)
        text = prefix + " ".join(wording(crit[i], gt).rstrip(".") if i in crit else i for i in ids)
        v = verdicts.get(cid)
        checklist.append(CheckItem(criterion=cid, text=text, status=st,
                                   quotes=_quotes(v, rt, bool(c and is_duration(c.threshold, c)))))
        reasons += jreasons.get(cid, [])
        if c and not c.answerable:
            confirm.append(f"“{T.short(text, 120).rstrip('.')}” cannot be shown by a case; confirm it before submitting.")
            reasons.append(confirm[-1])
    if deciding.confidence < REVIEW_CONFIDENCE:
        # never a percentage on screen: the number is internal (it decides this reason, nothing a person reads)
        reasons.append(f"The check is less certain than usual on this case; read the quoted "
                       f"notes before submitting.")
    reasons = list(dict.fromkeys(reasons))

    # misses and the ask
    misses: list[Miss] = []
    lines: list[str] = []
    says: list[str] = []
    unmet = False
    for x, (ids, st, prefix) in [(x, it) for x in missing(deciding) for it in _items(x)]:
        cid = ids[0]
        c = crit.get(cid)
        text = " ".join(wording(crit[i], gt).rstrip(".") if i in crit else i for i in ids)
        v = verdicts.get(cid)
        if st == "NOT_MET":
            unmet = True
            q = _quotes(v, rt, False)
            said = (T.chart_says(q[0].text) + (f" ({T.fmt_date(q[0].date)})." if q[0].date else ".")) if q \
                else "the case says otherwise."
            req = [f"“{T.clip(text)}”" + (" (must not apply)" if prefix else "") + f" — {said}"]
        else:
            req = T.request_lines(c, text, payer, bool(c and is_duration(c.threshold, c)), exclusion=bool(prefix))
            for q in _quotes(v, rt, True):
                says.append(T.chart_says(q.text).replace("the case", "the case on " + T.fmt_date(q.date), 1)
                            if q.date else T.chart_says(q.text))
        misses.append(Miss(criterion=cid, ask=T.join_request(req)))
        lines += req
    if status == "MET":
        dates = [q.date for i in checklist if i.status == "MET" for q in i.quotes if q.date]
        ask = f"Nothing to ask. The notes from {T.dates_phrase(dates)} document what {payer} needs."
    else:
        have = [i.text for i in checklist if i.status == "MET"]
        ask = T.addendum(who, patient, proc, payer, lines, says, unmet, have)
    packet = [PacketItem(criterion=i.criterion, text=i.text, quotes=i.quotes) for i in checklist if i.status == "MET"]
    name = pathway_name(n, dpid, gspans)
    sentence = {"MET": f"Everything required under “{T.short(name, 90)}” is documented.",
                "INSUFFICIENT": f"{len(misses)} requirement(s) under “{T.short(name, 90)}” are not documented yet.",
                "NOT_MET": f"The case contradicts a requirement under “{T.short(name, 90)}”."}[status]
    queue = "ready" if status == "MET" and not reasons else "review"
    return Result(order_id=order.id, guideline_id=gid, determination=status, reason=sentence, pathway_used=used,
                  confidence=round(deciding.confidence, 4), queue=queue, review_reasons=reasons,
                  confirm_reasons=list(dict.fromkeys(confirm)), misses=misses,
                  packet=packet, ask=ask, checklist=checklist, run_id=run_id)

