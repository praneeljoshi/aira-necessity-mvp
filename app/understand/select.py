"""Steps E, F, G (code): from the narrowed guideline and the order to what gets judged.

    E  pathways gate   Pathway[] empty -> Can't check, with the guideline's own sentence
    F  code gate       each cpt (or the mapped code) -> Code; non_covered / investigational -> NOT_COVERED;
                       not_addressed or not in the table and not mapped -> Can't check
    G  indication gate    each surviving code needs >= 1 chosen pathway that governs it (lists the code, or lists no
                       codes and was chosen by name); none -> review "which <target>?" with the candidates' names
       Selection.ranges = the picked pathways' lines, in document order (shown to the person; H reads the whole guideline)
"""
from __future__ import annotations

from app.core.models import CodeGate, Narrowed, Order, Pick, Range, Selection, Span
from app.ingest.spans import in_range, table, text_of


def _pos(spans: list[Span]) -> dict[str, int]:
    return {s.id: i for i, s in enumerate(spans)}


def pathway_name(n: Narrowed, pid: str, spans: list[Span]) -> str:
    p = next((x for x in n.pathways if x.id == pid), None)
    # its label: the first line of its first range that is not a bare section heading ("POSITION STATEMENT:")
    if not p or not p.spans:
        return pid
    tbl = table(spans)
    for r in p.spans:
        for s in in_range(spans, r):
            t = s.text.strip().rstrip(":").strip()
            if t and not (t.isupper() and len(t) <= 40):
                return t
    return text_of([p.spans[0].first], tbl).rstrip(":").strip()


def select(n: Narrowed, order: Order, spans: list[Span]) -> Selection:
    tbl = table(spans)
    # E
    if not n.pathways:
        why = text_of(n.guideline.no_pathways_reason or [], tbl)
        return Selection(applies=False, reason=why or "The guideline grants no coverage pathway of its own.")
    by = {c.code: c for c in n.codes}
    cpts = list(dict.fromkeys(order.procedure.cpt))
    reasons: list[str] = []
    # F
    gates: list[CodeGate] = []
    judged: list[str] = []
    absent = [c for c in cpts if c not in by]
    if n.mapped_cpt and (absent or not cpts):
        cpts = [c for c in cpts if c in by] + [n.mapped_cpt.code]
        written = ", ".join(absent) if absent else "no code"
        reasons.append(f"The case gives {written}; the procedure was matched to {n.mapped_cpt.code} "
                       f"(“{n.mapped_cpt.description[:120]}”) from its name. Confirm the code.")
    for c in cpts:
        code = by.get(c)
        mapped = bool(n.mapped_cpt and c == n.mapped_cpt.code and c not in order.procedure.cpt)
        if code is None:
            gates.append(CodeGate(code=c, outcome="cant_check", mapped=mapped))
        elif code.tag in ("non_covered", "investigational"):
            gates.append(CodeGate(code=c, tag=code.tag, outcome="not_covered", mapped=mapped))
        elif code.tag == "not_addressed":
            gates.append(CodeGate(code=c, tag=code.tag, outcome="cant_check", mapped=mapped))
        else:
            gates.append(CodeGate(code=c, tag=code.tag, outcome="judge", mapped=mapped))
            judged.append(c)
    if not cpts:
        return Selection(applies=False, reason="The case names no procedure code, and none could be matched to the "
                                               "guideline's code table from the procedure name.", reasons=reasons)
    stop = [g for g in gates if g.outcome != "judge"]
    if stop:
        nc = [g for g in stop if g.outcome == "not_covered"]
        if nc:
            reason = "; ".join(f"CPT {g.code} is listed as {g.tag.replace('_', '-')}: “{by[g.code].description[:160]}”"
                               for g in nc)
        else:
            reason = "; ".join(f"CPT {g.code} is not in this guideline's code table" if g.tag is None else
                               f"CPT {g.code} is listed but this guideline does not decide it" for g in stop)
        return Selection(applies=True, reason=reason, code_gate=gates, reasons=reasons)
    # G
    chosen = [p for p in n.pathways if p.id in n.chosen]
    picks: list[Pick] = []
    candidates: dict[str, list[str]] = {}
    for c in judged:
        mine = [Pick(code=c, pathway=p.id, how="code" if c in p.codes else "name")
                for p in chosen if c in p.codes or not p.codes]
        if mine:
            picks += mine
        else:
            candidates[c] = [p.id for p in n.pathways if c in p.codes or not p.codes]
            names = [pathway_name(n, x, spans) for x in candidates[c]]
            what = order.procedure.target or order.procedure.as_written or "procedure"
            reasons.append(f"Which indication covers CPT {c} for this order ({what})? "
                           + (("Candidates: " + "; ".join(f"“{x[:90]}”" for x in names) + ".") if names else
                              "No section of the guideline names this code."))
    pos = _pos(spans)
    ranges: list[Range] = []
    for pid in dict.fromkeys(p.pathway for p in picks):
        p = next(x for x in n.pathways if x.id == pid)
        ranges += p.spans
    ranges = sorted({(r.first, r.last): r for r in ranges}.values(), key=lambda r: pos.get(r.first, 0))
    return Selection(applies=True, code_gate=gates, pathways=picks, ranges=ranges, reasons=reasons,
                     candidates=candidates)
