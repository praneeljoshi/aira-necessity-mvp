"""The decision as the coordinator reads it (GET /api/orders/{id}/tree, drawn by static/tree.html): the chosen part
of the guideline, line by line as printed, each requirement marked from the stored verdicts, and beside it the chart
evidence as it appears in the chart (quoted lines, the note they sit under, the page).

Everything here is resolved by code from stored spans: the guideline's lines, the criteria's checked quotes, the
judge's citations expanded to chart lines, verified dates. No model call; the model's free text (rationale) is
passed through only as a note on items that are not documented, as the queue screen already does.

Marks a line can carry (plain words on screen; the names below are the page's vocabulary):
    documented · missing · contradicted · not_needed (an alternative already documented) · confirm (a chart cannot
    show it) · clear (an exclusion that does not apply) · applies (an exclusion the chart shows) · unclear ·
    struck (a person removed it for this case, app/review/strikes.py; shown with who and why, never marks its block)
A requirement a person added to this case (app/review/additions.py) is marked like any other and carries `added` (who,
when); its lines are drawn even when they sit outside the chosen part.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from app import pipeline
from app.checklist import keys
from app.checklist import admin
from app.core import store
from app.review import additions, strikes
from app.decide.evaluate import compile_expr, path_nodes
from app.evidence.judge import quote_date
from app.core.models import Criterion, CriteriaSet, Narrowed, NodeResult, Order, Range, Result, Selection, Span, Verdict
from app.evidence.refs import find_dates
from app.understand.select import pathway_name
from app.ingest.spans import expand, in_range, resolves, table, text_of, wording

LOOKBACK = 80          # lines above a quote searched for the note it sits under (same reach as judge.DATE_LOOKBACK)


# ---------------------------------------------------------------- the tree walk: what each criterion is for


def classify(expr: Any, node: NodeResult, needed: bool, out: dict[str, dict], group: Optional[str] = None) -> None:
    """Walks the expression and its compiled node together. For every criterion id records its role (requirement /
    exclusion / part of a compound exclusion), whether the decision needed it, its own status, and for exclusions
    the exclusion's status (the `not` node)."""
    if isinstance(expr, str):
        out[expr] = {"role": "requirement", "needed": needed, "status": node.status, "group": group}
        return
    (op, arg), = expr.items()
    if op == "not":
        child, cnode = arg, node.children[0]
        if isinstance(child, str):
            out[child] = {"role": "exclusion", "needed": needed, "status": cnode.status, "excl": node.status, "group": group}
        elif isinstance(child, dict) and "all" in child:          # "X without Y": one exclusion, several parts
            gid = "+".join(_leaves(child))
            for part, pnode in zip(child["all"], cnode.children):
                for leaf, lnode in _flat(part, pnode):
                    out[leaf] = {"role": "part", "needed": needed, "status": lnode.status, "excl": node.status, "group": gid}
        elif isinstance(child, dict) and "any" in child:          # "none of the following": each item its own exclusion
            for item, inode in zip(child["any"], cnode.children):
                for leaf, lnode in _flat(item, inode):
                    s = {"MET": "NOT_MET", "NOT_MET": "MET", "INSUFFICIENT": "INSUFFICIENT"}[lnode.status]
                    out[leaf] = {"role": "exclusion", "needed": needed, "status": lnode.status, "excl": s, "group": group}
        else:
            for leaf, lnode in _flat(child, cnode):
                out[leaf] = {"role": "exclusion", "needed": needed, "status": lnode.status, "excl": node.status, "group": group}
        return
    if op == "all":
        for e, c in zip(arg, node.children):
            classify(e, c, needed, out, group)
        return
    kids = list(zip(arg["of"], node.children)) if op == "at_least" else list(zip(arg, node.children))
    k = arg["k"] if op == "at_least" else 1
    met = [c for _, c in kids if c.status == "MET"]
    gid = group or ("alt:" + "+".join(_leaves(expr)))
    on_path = {id(x) for x in path_nodes(node)}
    for e, c in kids:
        # enough alternatives documented: the rest were not needed (the case page dims them only once a person accepts
        # the documented one; review.case_view). Not yet: no option is dimmed. The closest option (on the deciding
        # path, which the ask is written from) and every other route (an exemption, "unless contraindicated", "or
        # documentation that compression is not tolerated") each need their own evidence; the others carry `route`
        if len(met) >= k:
            this_needed = needed and c.status == "MET"
        else:
            this_needed = needed
        before = set(out)
        classify(e, c, this_needed, out, gid)
        if needed and len(met) < k and not any(id(x) in on_path for x in _nodes(c)):
            for leaf in set(out) - before:
                out[leaf]["route"] = True
    for leaf in _leaves(expr):
        out[leaf]["alt"] = {"k": k, "n": len(kids), "met": len(met)}


def _nodes(n: NodeResult) -> list[NodeResult]:
    return [n] + [x for c in n.children for x in _nodes(c)]


def _leaves(e: Any) -> list[str]:
    from app.decide.evaluate import leaf_ids
    return leaf_ids(e)


def _flat(e: Any, n: NodeResult) -> list[tuple[str, NodeResult]]:
    if isinstance(e, str):
        return [(e, n)]
    (op, arg), = e.items()
    if op == "not":
        return _flat(arg, n.children[0])
    kids = arg["of"] if op == "at_least" else arg
    return [x for c, cn in zip(kids, n.children) for x in _flat(c, cn)]


# ---------------------------------------------------------------- the decision as an outline (the case page's Tree view)

_FLIP = {"MET": "NOT_MET", "NOT_MET": "MET", "INSUFFICIENT": "INSUFFICIENT"}
_WORST = ["contradicted", "open", "ask", "met"]          # weakest first: what keeps a case from being ready


def _show(status: str, blockers: list[dict]) -> str:
    """A node's status in the outline's words. MET -> met, NOT_MET -> contradicted; INSUFFICIENT -> waiting on the
    ask when every requirement holding it up is in the message to the surgeon, else not shown yet."""
    if status == "MET":
        return "met"
    if status == "NOT_MET":
        return "contradicted"
    open_ = [x for x in blockers if x["status"] == "open"]
    return "ask" if blockers and not open_ and any(x["status"] == "ask" for x in blockers) else "open"


def _live_leaves(n: dict) -> list[dict]:
    if "criterion" in n:
        return [] if n.get("dim") or not n.get("counted", True) else [n]
    return [x for k in n["kids"] for x in _live_leaves(k)]


def outline(expr: Any, node: NodeResult, reqs: dict[str, dict], dim: Optional[str] = None, neg: bool = False) -> dict:
    """One expression and its compiled node as the outline the case page draws: groups in words, leaves by id. Each
    node's `status` (met · ask · open · contradicted) is the compiled status read from the requirement's side (an
    exclusion's `not` flips it), so the root says why the case is or is not ready. A leaf reads as the navigator
    does: the requirement's own `proof` / `in_ask` from case_view. `dim` is "not_needed" for an option made unneeded
    by another one already met, "other_option" for an option that is not the one being completed. Under a `not`
    nothing is dimmed: every part of an exclusion is read."""
    if isinstance(expr, str):
        r = reqs.get(expr)
        s = _FLIP[node.status] if neg else node.status
        if r is not None and not dim and r.get("counted", True):
            st = "met" if r.get("proof") else "contradicted" if (s == "NOT_MET" or r.get("mark") in ("contradicted", "applies")) \
                else "ask" if r.get("in_ask") else "open"
        else:
            st = {"MET": "met", "NOT_MET": "contradicted", "INSUFFICIENT": "open"}[s]
        return {"criterion": expr, "status": st, "dim": dim, "counted": r.get("counted", True) if r is not None else True}
    (op, arg), = expr.items()
    s = _FLIP[node.status] if neg else node.status
    if op == "not":
        inner = node.children[0]
        if isinstance(arg, dict) and ("any" in arg or "all" in arg):
            (iop, iarg), = arg.items()
            kids = [outline(e, c, reqs, dim, not neg) for e, c in zip(iarg, inner.children)]
            shape = "none" if iop == "any" else "not_all"     # "none of these" · "not all of these together"
        else:
            kids, shape = [outline(arg, inner, reqs, dim, not neg)], "none"
        out = {"op": shape, "kids": kids, "dim": dim}
    elif op == "all":
        out = {"op": "all", "kids": [outline(e, c, reqs, dim, neg) for e, c in zip(arg, node.children)], "dim": dim}
    else:
        es = arg["of"] if op == "at_least" else arg
        k = arg["k"] if op == "at_least" else 1
        met = sum(c.status == "MET" for c in node.children)
        on_path = {id(x) for x in path_nodes(node)}
        kids = []
        for e, c in zip(es, node.children):
            d, route = dim, False
            if not d and not neg:
                # set aside only once a person accepted the documented option (case_view's `dim` on the requirement;
                # None there means not yet); with nothing documented no option is dimmed: each other route needs
                # its own evidence
                if met >= k and c.status != "MET":
                    if not any(reqs.get(x) is not None and "dim" in reqs[x] and reqs[x]["dim"] is None for x in _leaves(e)):
                        d = "not_needed"
                elif met < k and not any(id(x) in on_path for x in _nodes(c)):
                    route = True
            kid = outline(e, c, reqs, d, neg)
            if route:
                kid["route"] = True
            kids.append(kid)
        out = {"op": op, "k": k, "kids": kids, "dim": dim}
    out["n"] = len(out["kids"])
    out["status"] = _show(s, _live_leaves(out))
    return out


def outline_case(sections: list[tuple[str, str, Any]], verdicts: dict[str, Verdict], reqs: dict[str, dict]) -> dict:
    """The case's logic for the Tree view: one outline per judged section (after strikes and additions), and the
    root: the weakest section's status and how many requirements the case is waiting on (not dimmed, not met)."""
    out = [{"pathway": pid, "name": name, "tree": outline(e, compile_expr(e, verdicts), reqs)} for pid, name, e in sections]
    waiting = list(dict.fromkeys(x["criterion"] for s in out for x in _live_leaves(s["tree"]) if x["status"] != "met"))
    status = min((s["tree"]["status"] for s in out), key=_WORST.index, default="open")
    return {"status": status, "waiting": waiting, "sections": out}


def mark_of(info: dict, c: Optional[Criterion], v: Optional[Verdict]) -> str:
    if c is not None and not c.answerable:
        return "confirm"
    if not info["needed"]:
        return "other_option" if info.get("other_option") else "not_needed"
    st = info["status"]
    if info["role"] == "requirement":
        return {"MET": "documented", "INSUFFICIENT": "missing", "NOT_MET": "contradicted"}[st]
    if info["role"] == "part":
        return {"MET": "part_shown", "NOT_MET": "part_clear", "INSUFFICIENT": "unclear"}[st]
    return {"MET": "applies", "NOT_MET": "clear", "INSUFFICIENT": "unclear"}[st]


WORDS = {
    "documented": "Documented", "missing": "Not in the case yet", "contradicted": "The case says otherwise",
    "not_needed": "Not needed: another option is documented", "other_option": "Another option; not the one being completed", "confirm": "Confirm outside the case",
    "clear": "Does not apply here", "applies": "Applies: the case shows this", "unclear": "Can't tell from the case",
    "part_shown": "The case shows this part", "part_clear": "This part is ruled out",
    "not_covered": "Listed as not covered", "unchecked": "Not checked",
    "struck": "Removed for this case",
}
BAD = {"missing", "contradicted", "applies", "unclear", "not_covered"}


# ---------------------------------------------------------------- chart evidence as it appears in the chart


_SIGNED = re.compile(r"\bsigned\b", re.I)
_MONTHS = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
_DATED = re.compile(rf"\b{_MONTHS}\b.*\b(19|20)\d{{2}}\b|\b\d{{1,2}}/\d{{1,2}}/\d{{2,4}}\b|^visit date", re.I)
_SECTION = re.compile(r"^\d+\.\s+[A-Z][A-Z &/-]{3,}$")      # "7. DIAGNOSTIC IMAGING & TESTING REPORTS"
_COLUMNS = re.compile(r"\S\s{3,}\S")                        # a table row: two columns set apart by spaces


def _heading_like(s: Span) -> bool:
    t = s.text.strip()
    if not t or _SIGNED.search(t) or len(t) > 140 or t.startswith(("•", "-", "–", "▪")):
        return False
    if _SECTION.match(t) or _DATED.search(t) and (s.blank_before or t.lower().startswith("visit date")):
        return True
    if _COLUMNS.search(t):
        return False
    if t.endswith(":") and len(t) < 70:
        return True
    return s.blank_before and len(t) < 110 and not t.endswith(".")


def note_heading(rspans: list[Span], first_id: str) -> str:
    """The note a quoted line sits under: the nearest heading-like line above it and, when that one carries no date,
    the dated note heading or numbered chart section above it ("Visit Date: … Follow-Up › Interval History")."""
    pos = {s.id: i for i, s in enumerate(rspans)}
    i = pos.get(first_id)
    if i is None or _SECTION.match(rspans[i].text.strip()):      # the quote starts with the section heading itself
        return ""
    found: list[str] = []
    for j in range(i - 1, max(-1, i - LOOKBACK - 1), -1):
        s = rspans[j]
        if not _heading_like(s):
            continue
        t = re.sub(r"\s+", " ", s.text.strip()).rstrip(":")
        outer = bool(_DATED.search(t) or _SECTION.match(t))
        if not found or outer:
            found.append(t)
        if outer:
            break
    return " › ".join(reversed(found))


def quotes_of(v: Optional[Verdict], rspans: list[Span], rt: dict[str, Span], limit: int = 4) -> list[dict]:
    """Every citation the judge gave for its status (for when documented or partly so, against when contradicted),
    resolved to the chart's own lines, with its verified date (judge.quote_date), the note heading and the page."""
    if not v:
        return []
    cites = v.for_ if v.status != "NOT_MET" else v.against
    cites = [c for c in (cites or v.for_ or v.against) if resolves(c, rt)]
    out = []
    for c in cites[:limit]:
        ids = expand([c], rt)
        out.append({"span": c, "text": text_of([c], rt), "date": quote_date(v, c, rt), "heading": note_heading(rspans, ids[0]),
                    "page": rt[ids[0]].page, "lines": ids})
    return out


# ---------------------------------------------------------------- the guideline, line by line


def _lines(gspans: list[Span], first: str, last: str) -> list[Span]:
    from app.core.models import Range
    return in_range(gspans, Range(first=first, last=last))


def build(chart_id: str) -> dict:
    rec = store.load_result(chart_id)
    r = Result.model_validate(rec["result"])
    sel = Selection.model_validate(rec["selection"])
    verdicts = {k: Verdict.model_validate(v) for k, v in (rec.get("verdicts") or {}).items()}
    gid = (rec.get("meta") or {}).get("guideline_id") or r.guideline_id
    return layout(chart_id, gid, sel, r.pathway_used or [], verdicts, [m.criterion for m in r.misses])


def layout(chart_id: str, gid: str, sel: Selection, used: list[str], verdicts: dict[str, Verdict], misses: list[str],
           draft: Optional[CriteriaSet] = None, use_pinned: bool = True) -> dict:
    """The guideline as the case page draws it, from a Selection, the judged pathways and the verdicts. `build` passes
    a finished case's; review.preview_view a running check's (no verdicts; `draft` = the checklist so far, or None
    with use_pinned False while H builds: sections with no blocks)."""
    o = store.load_order(chart_id)
    gspans, sha, gname = store.load_guideline_spans(gid)
    rspans = store.load_chart_spans(chart_id)
    gt, rt = table(gspans), table(rspans)
    n: Optional[Narrowed] = None
    cs: Optional[CriteriaSet] = None
    if o:
        n, cs = store.load_criteria(keys.case_order_key(sha, o.procedure, chart_id))
    conf = store.load_confirmation(chart_id)        # a section confirmed by a person: its requirements live under the H key
    if conf and conf.get("h_key"):
        cs = store.load_criteria(conf["h_key"])[1] or cs
    cs = store.load_case_criteria(chart_id) or cs   # the exact set this case was judged with (older cases: none)
    if not use_pinned:
        cs = draft
    crit = cs.criterion_map() if cs else {}
    base = cs
    cs, _ = admin.split(chart_id, cs, used)        # admin leaves set aside (app/checklist/admin.py), before strikes
    verdicts, _ = admin.verdicts(chart_id, base, verdicts)
    cs, struck = strikes.split(chart_id, cs, gspans, used)   # a person's strikes on this case
    # lines a person added to this case's checklist, with the verdicts their ask judged (app/review/additions.py)
    cs, verdicts, _, added = additions.extend(chart_id, cs, verdicts, {}, used)
    if added:
        crit = {**crit, **{c.id: c for c in cs.criteria if c.id in added}}
    out: dict[str, Any] = {"guideline": {"id": gid, "title": gname, "payer": n.guideline.payer.name if n else ""},
                           "sections": [], "blocks": [], "codes": [], "candidates": [], "misses": [], "counts": {}}

    # the tree walk over every judged pathway
    info: dict[str, dict] = {}
    if cs:
        expr = {e.pathway: e.expr for e in cs.expressions}
        for pid in used:
            if pid in expr:
                classify(expr[pid], compile_expr(expr[pid], verdicts), True, info)
    items: dict[str, dict] = {}
    for cid, inf in info.items():
        c, v = crit.get(cid), verdicts.get(cid)
        mark = mark_of(inf, c, v)
        items[cid] = {"criterion": cid, "words": wording(c, gt) if c else cid, "role": inf["role"], "group": inf.get("group"),
                      "mark": mark, "say": WORDS[mark], "bad": mark in BAD, "excl": inf.get("excl"), "alt": inf.get("alt"),
                      "refs": expand(c.refs, gt) if c else [], "quotes": quotes_of(v, rspans, rt) if mark not in ("not_needed", "other_option") else [],
                      "note": (v.rationale if v and mark in BAD and v.rationale and not v.rationale.startswith("A case cannot") else "")}
        if cid in added:
            items[cid]["added"] = additions.summary(added[cid])
    # struck for this case: still on the page, in the guideline's words, with who removed it and why; no quotes
    if struck and base:
        bexpr = {e.pathway: e.expr for e in base.expressions}
        binfo: dict[str, dict] = {}
        for pid in used:
            if pid in bexpr:
                classify(bexpr[pid], compile_expr(bexpr[pid], verdicts), True, binfo)
        for cid, sk in struck.items():
            c = crit.get(cid)
            if c is None or cid in items:
                continue
            w = sk.get("removed_with")
            say = WORDS["struck"] if not w else f"Removed with “{(wording(crit[w], gt) if w in crit else w).rstrip('.')}”"
            items[cid] = {"criterion": cid, "words": wording(c, gt), "role": (binfo.get(cid) or {}).get("role", "requirement"),
                          "group": None, "mark": "struck", "say": say, "bad": False, "excl": None, "alt": None,
                          "refs": expand(c.refs, gt), "quotes": [], "note": "",
                          "struck": {k: sk.get(k) for k in ("id", "code", "reason", "by", "at", "removed_with")}}

    # blocks: criteria whose lines overlap are read together (one bullet holding "A, AND B, AND C")
    pos = {s.id: i for i, s in enumerate(gspans)}
    spans_of = {cid: sorted(pos[x] for x in it["refs"] if x in pos) for cid, it in items.items()}
    blocks: list[dict] = []
    for cid in sorted(items, key=lambda c: (spans_of[c] or [10 ** 9])[0]):
        if not spans_of[cid]:
            continue
        a, b = spans_of[cid][0], spans_of[cid][-1]
        for blk in blocks:
            if a <= blk["last"] and b >= blk["first"]:
                blk["first"], blk["last"] = min(blk["first"], a), max(blk["last"], b)
                blk["items"].append(cid)
                break
        else:
            blocks.append({"first": a, "last": b, "items": [cid]})
    for i, blk in enumerate(blocks):
        its = [items[c] for c in blk["items"]]
        live = [x for x in its if x["mark"] != "struck"] or its       # a struck requirement does not mark the block
        worst = next((m for m in ("contradicted", "applies", "missing", "unclear", "part_shown") if any(x["mark"] == m for x in live)), None)
        if worst is None and all(x["mark"] == "struck" for x in live):
            worst = "struck"
        if worst is None:
            marks = {x["mark"] for x in live}
            worst = "documented" if "documented" in marks else "clear" if ("clear" in marks or "part_clear" in marks) else \
                "confirm" if "confirm" in marks else "other_option" if "other_option" in marks else "not_needed"
        # a compound exclusion ("X without Y") reads as one row: it applies only when every part is shown
        groups = {x["group"] for x in live if x["role"] == "part" and x["mark"] != "struck"}
        excl = None
        if groups:
            st = next((x["excl"] for x in live if x["role"] == "part"), None)
            needed = all(x["mark"] not in ("not_needed", "other_option") for x in live)
            excl = {"MET": "clear", "NOT_MET": "applies", "INSUFFICIENT": "unclear"}.get(st) if needed else "not_needed"
            worst = excl or worst
        blk.update(id=f"b{i}", lines=[gspans[j].id for j in range(blk["first"], blk["last"] + 1)], mark=worst, say=WORDS[worst],
                   bad=worst in BAD, compound=bool(groups), items=its)
        for it in its:
            it["block"] = blk["id"]
    out["blocks"] = [{k: v for k, v in b.items() if k not in ("first", "last")} for b in blocks]
    line_block = {lid: b["id"] for b in out["blocks"] for lid in b["lines"]}

    # the chosen part of the guideline, every line, in document order: requirements marked, the rest dimmed. Ranges a
    # few lines apart are read as one piece (the lines between them dimmed as not part of this check); a range that
    # starts mid-list brings the lead-in above it along, so a bullet is never shown without its sentence.
    heads = set()
    if n:
        for p in n.pathways:
            if p.id in (used) and p.spans:
                heads.add(p.spans[0].first)
    always = {a.first for a in n.guideline.always_on} if n else set()
    pieces: list[dict] = []
    extra = []                                       # an addition's lines, wherever they are in the guideline
    for x in {id(a): a for a in added.values()}.values():
        ids_ = [i for i in x.get("spans") or [] if i in pos]
        if ids_:
            extra.append(Range(first=min(ids_, key=pos.get), last=max(ids_, key=pos.get)))
    added_firsts = {rg.first for rg in extra}
    for rg in sorted((x for x in list(sel.ranges) + extra if x.first in pos and x.last in pos), key=lambda x: pos[x.first]):
        a, b = pos[rg.first], pos[rg.last]
        if pieces and a - pieces[-1]["last"] <= 4:
            pieces[-1]["gaps"] += list(range(pieces[-1]["last"] + 1, a))
            pieces[-1]["last"] = max(pieces[-1]["last"], b)
            pieces[-1]["firsts"].append(rg.first)
        else:
            pieces.append({"first": a, "last": b, "gaps": [], "firsts": [rg.first]})
    for pc in pieces:
        ctx: list[int] = []
        first = gspans[pc["first"]]
        if re.match(r"^\s*([•▪➢❖–\-]|\d+\.|[a-z]\.)\s", first.text):
            j = pc["first"] - 1
            while j >= 0 and len(ctx) < 4 and gspans[j].id not in line_block:
                ctx.insert(0, j)
                if gspans[j].blank_before:
                    break
                j -= 1
        label = next((pathway_name(n, p.id, gspans) for p in (n.pathways if n else []) if p.spans and p.spans[0].first in pc["firsts"]), None)
        if label is None and always & set(pc["firsts"]):
            label = "Applies to every request under this guideline"
        if label is None and added_firsts & set(pc["firsts"]):
            label = "Added to this case's checklist"
        lines = []
        for j in ctx + list(range(pc["first"], pc["last"] + 1)):
            sp = gspans[j]
            kind = "context" if j in ctx else "gap" if j in pc["gaps"] else "heading" if sp.id in heads else \
                "req" if sp.id in line_block else "other"
            if kind == "other" and sp.id in pc["firsts"] and not re.match(r"^\s*[•▪➢❖–\-]", sp.text):
                kind = "heading"
            lines.append({"id": sp.id, "text": sp.text, "page": sp.page, "blank_before": sp.blank_before, "kind": kind,
                          "block": line_block.get(sp.id)})
        out["sections"].append({"first": gspans[pc["first"]].id, "last": gspans[pc["last"]].id, "label": label or "",
                                "page_from": gspans[pc["first"]].page, "page_to": gspans[pc["last"]].page, "lines": lines})

    # a code that stopped the check: the table row as printed
    if n:
        by = {c.code: c for c in n.codes}
        stop = any(g.outcome != "judge" for g in sel.code_gate)       # a stopped check lists every code on the order
        for g in sel.code_gate:
            c = by.get(g.code)
            if (g.outcome != "judge" or stop) and c:
                out["codes"].append({"code": g.code, "tag": g.tag, "outcome": g.outcome, "mapped": g.mapped,
                                     "lines": [{"id": s.id, "text": s.text, "page": s.page} for x in c.refs for s in
                                               [gt[i] for i in expand([x], gt) if i in gt]]})
    # no section chosen: the candidates, each with the first lines of its text
    if n and not sel.pathways and sel.candidates:
        for code, pids in sel.candidates.items():
            for pid in pids:
                p = next((x for x in n.pathways if x.id == pid), None)
                if p and p.spans:
                    lines = _lines(gspans, p.spans[0].first, p.spans[0].last)[:5]
                    out["candidates"].append({"code": code, "name": pathway_name(n, pid, gspans), "targets": p.targets,
                                              "lines": [{"id": s.id, "text": s.text, "page": s.page} for s in lines]})
    # what to fix first: the misses, in guideline order
    miss_ids = set(misses)
    out["misses"] = [{"criterion": c, "block": items[c].get("block"), "words": items[c]["words"], "mark": items[c]["mark"], "say": items[c]["say"]}
                     for c in sorted(miss_ids & set(items), key=lambda c: (spans_of[c] or [10 ** 9])[0])]
    marks = [it["mark"] for it in items.values()]
    out["counts"] = {m: marks.count(m) for m in set(marks)}
    out["chart"] = {"filename": store.chart_meta(chart_id).get("filename"), "pages": len({s.page for s in rspans})}
    return out
