"""Step H as a tool-using agent, no sandbox (STEP_H=tools). Drop-in for criteria.build. Spec: guideline-reduce
experiments/swarm/V12_TOOLS_SPEC.md.

    in:  the whole guideline (plain text with layout, no ids), the order (allow-listed fields), its code rows (full
         descriptions)
    session: function tools the host runs against its own working tree (State): find, read, add_condition (the quote
         is checked when the condition is made), define_block, set_logic, submit (final checks). Caps: MAX_CALLS tool
         calls and MAX_SUBMITS submits, then needs_review with what is outstanding. The first passing submit is not
         accepted: the host asks for the full-policy sweep (SWEEP_NEXT) and accepts the next passing submit; if a cap
         ends the session first, the first passing tree stands. Notes say what the sweep added
    audit: a second, short session over the same state with find, read, add_condition, set_logic, submit; set_logic
         may not drop a leaf the indication already had and may not add an indication (add-only)
    out: CriteriaSet; each indication's logic with blocks expanded, ORed into the confirmed pathway's expression;
         answerable=false leaves stay in the tree (the pipeline makes them review reasons, policy B)

Checks are citation and well-formedness only: quotes printed in the guideline, ids unique and known, logic parses,
thresholds well formed, every condition used, every indication has logic.
"""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Any, Optional

from . import criteria, llm, log
from .criteria import _T, picked
from .evaluate import from_logic, leaf_ids
from .models import Code, CriteriaSet, Criterion, Expression, Narrowed, Procedure, Selection, Span
from .reduce_code import given_rule, guideline_text, not_covered, order_json, sweep_note
from .sandbox import helpers
from .spans import table

logger = log.get("reduce_tools")

MAX_CALLS = 60
MAX_SUBMITS = 4         # passing or not; the second passing submit is accepted (the first starts the sweep)
AUDIT_CALLS = 60
SWEEP_NEXT = ("passes. Now do the full-policy sweep and the self-check; submit again (same or changed) when a full pass "
              "adds nothing.")
SNAPSHOT = ("conds", "blocks", "logic", "quotes", "not_covered", "notes")
OPS = {">=", ">", "<=", "<", "=="}


# ---------------------------------------------------------------- the tools the model sees (spec section 3)

LOGIC = ("Logic syntax (same everywhere): condition ids and block names combined with `AND`, `OR`, `NOT`, parentheses "
         "and `AT_LEAST k OF (a, b, c)`. `NOT` binds tightest, then `AND`, then `OR`; use parentheses whenever you "
         "mix them.")

TOOLS = {
    "find": {
        "description": (
            "Search the guideline for a word or phrase (case-insensitive, whitespace-tolerant; also tries each word). "
            "Returns up to 10 hits: {\"ok\": true, \"hits\": [{\"lines\": \"g0141-g0142\", \"text\": \"... the matching "
            "sentence ...\"}]}.\nUse it to: locate the exact wording before quoting it; look for exclusions, "
            "definitions, notes or cross-references printed elsewhere (\"investigational\", \"does not meet\", "
            "\"contraindicat\", \"nonhealing\", \"criteria above\", \"Note\")."),
        "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    "read": {
        "description": (
            "Return the lines from `first` to `last` (g-ids, at most 120 lines) with their ids: {\"ok\": true, "
            "\"lines\": [...]}.\nUse it to re-read a section in full, e.g. the whole list under a lead-in before "
            "deciding all/any."),
        "parameters": {"type": "object", "properties": {"first": {"type": "string"}, "last": {"type": "string"}},
                       "required": ["first", "last"]}},
    "add_condition": {
        "description": (
            "Add one leaf: one fact a nurse can check in a chart.\n"
            "- `id`: short snake_case, unique (`lvef_le_35`).\n"
            "- `quote`: the guideline's own words for this condition, copied exactly (line breaks and extra spaces do "
            "not matter). It must be printed in the guideline; the tool checks immediately.\n"
            "- `question`: how a nurse asks it of a chart, saying what the chart must show.\n"
            "- `threshold`: only when the condition sets its own number: {\"op\": \">=\", \"value\": 3, \"unit\": "
            "\"months\"} (ops `>=`, `>`, `<=`, `<`, `==`). Never for an \"e.g.\" number.\n"
            "- `answerable`: false only for what no chart can show (a contract term, a provider credential, a "
            "document that only exists after surgery). It stays in the logic and becomes a review item.\n"
            "Returns {\"ok\": true, \"id\": ..., \"lines\": \"g0141\"}, or {\"ok\": false, \"problems\": [\"quote not "
            "found\"], \"nearest\": [{\"lines\": ..., \"text\": ...}]} (copy the exact words from `nearest` and call "
            "again), or {\"ok\": false, \"problems\": [\"id already used\"]}.\n"
            "A condition is a positive statement of a situation; exclusions are added as their situation "
            "(`carotid_dissection`, quote \"carotid artery dissection\") and used under NOT in the logic."),
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "quote": {"type": "string"}, "question": {"type": "string"},
            "threshold": {"type": ["object", "null"], "properties": {
                "op": {"type": "string"}, "value": {}, "unit": {"type": ["string", "null"]}}},
            "answerable": {"type": "boolean"}},
            "required": ["id", "quote", "question"]}},
    "define_block": {
        "description": (
            "Name a reusable piece of logic made of conditions you already added (and other blocks). Use it for "
            "anything more than one indication or route shares: a conservative-care requirement, a contraindication "
            "list, an adult/child split, a repeat-testing guard. No quotes here; blocks have none of their own.\n"
            + LOGIC + "\nReturns {\"ok\": true, \"name\": ..., \"expanded\": \"<the logic with blocks expanded>\"} or "
            "{\"ok\": false, \"problems\": [\"unknown id 'x'\", \"parse error at ...\"]}."),
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "logic": {"type": "string"}},
                       "required": ["name", "logic"]}},
    "set_logic": {
        "description": (
            "Give the final logic for one indication: true exactly when the payer would approve under it. Same "
            "syntax; may use conditions and blocks. `indication`: a short id you choose for it. Call it once per "
            "indication you use; calling again replaces it.\nReturns {\"ok\": true, \"indication\": ..., \"expanded\": "
            "..., \"unused_conditions\": [...]} or the problems."),
        "parameters": {"type": "object", "properties": {"indication": {"type": "string"}, "logic": {"type": "string"}},
                       "required": ["indication", "logic"]}},
    "update_condition": {
        "description": (
            "Change a condition you already added: fix its quote (checked again, like `add_condition`), its question, "
            "its threshold or `answerable`. Only the fields you pass change. Use it when you find you quoted the wrong "
            "words, set a wrong number, or asked the question too narrowly. The logic keeps referring to it by the "
            "same id.\nReturns {\"ok\": true, \"id\": ..., \"lines\": ...} or the problems (same as `add_condition`)."),
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "quote": {"type": "string"}, "question": {"type": "string"},
            "threshold": {"type": ["object", "null"], "properties": {
                "op": {"type": "string"}, "value": {}, "unit": {"type": ["string", "null"]}}},
            "answerable": {"type": "boolean"}},
            "required": ["id"]}},
    "remove_condition": {
        "description": (
            "Remove a condition you added by mistake (it is not a condition of this indication, or it duplicates "
            "another). `why` is required: one sentence, recorded and shown to the reviewer. Any logic or block that "
            "uses it must be changed first (the tool refuses while it is still used and names where). Removing is for "
            "your own mistakes, not for trimming: when unsure whether a sentence limits approval, keep it.\n"
            "Returns {\"ok\": true, \"removed\": id} or {\"ok\": false, \"problems\": [\"still used in: set_logic "
            "ewr_first\"]}."),
        "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "why": {"type": "string"}},
                       "required": ["id", "why"]}},
    "show": {
        "description": (
            "Return the current working tree: every condition (id, quote, lines, question, threshold, answerable), "
            "every block, every indication's logic with blocks expanded, and conditions not used anywhere. Use it "
            "before `submit` and whenever you need to re-check what you built.\n"
            "Revising your own work: `set_logic` and `define_block` replace what was there when called again with the "
            "same name; `update_condition` changes a condition in place; `remove_condition` takes one out with a "
            "reason. The host records every change (old and new values) in the run log and lists removals in the "
            "result for review."),
        "parameters": {"type": "object", "properties": {}}},
    "submit": {
        "description": (
            "Finish. `indication_quotes`: the guideline sentence(s) that grant each indication you used, copied "
            "exactly (checked). `not_covered`: the guideline's words, if the order is not covered at all (then no "
            "logic is needed). `notes`: your reading in your own words: judgment calls, alternatives you considered.\n"
            "Final checks: every indication has logic; every condition is used somewhere; quotes found; logic parses.\n"
            "Returns {\"ok\": true} (done) or {\"ok\": false, \"problems\": [...]} (fix with the other tools, then "
            "submit again)."),
        "parameters": {"type": "object", "properties": {
            "indication_quotes": {"type": "array", "items": {"type": "string"}},
            "not_covered": {"type": ["string", "null"]}, "notes": {"type": "string"}},
            "required": ["indication_quotes"]}},
}

AUDIT_TOOLS = ("find", "read", "show", "add_condition", "set_logic", "submit")  # add-only: no update / remove / blocks


def schemas(names=tuple(TOOLS)) -> list[dict]:
    return [{"name": n, **TOOLS[n]} for n in names]


# ---------------------------------------------------------------- the host's working tree


def show(e: Any) -> str:
    """A JSON expression back as a logic string."""
    if isinstance(e, str):
        return e
    (op, arg), = e.items()
    if op == "not":
        return "NOT " + (show(arg) if isinstance(arg, str) else f"({show(arg)})")
    if op == "at_least":
        return f"AT_LEAST {arg['k']} OF (" + ", ".join(show(x) if isinstance(x, str) or "not" in x else f"({show(x)})"
                                                     for x in arg["of"]) + ")"
    j = " AND " if op == "all" else " OR "
    return j.join(show(x) if isinstance(x, str) or "not" in x or "at_least" in x else f"({show(x)})" for x in arg)


class State:
    """Conditions, blocks and logic per indication, built one tool call at a time; every result is the model's to
    read (short JSON, nothing from outside the guideline and the order)."""

    def __init__(self, spans: list[Span]):
        self.spans = [s for s in spans if s.text.strip()]
        self.tbl = table(spans)
        self.ids = [s.id for s in spans]
        self.conds: dict[str, dict] = {}
        self.blocks: dict[str, Any] = {}
        self.logic: dict[str, Any] = {}           # indication -> JSON expression (blocks not yet expanded)
        self.quotes: list[str] = []
        self.not_covered: Optional[str] = None
        self.notes = ""
        self.submits = 0
        self.done = False
        self.audit = False
        self.locked: dict[str, set[str]] = {}     # audit: indication -> leaves it may not drop
        self.last: list[str] = []                 # outstanding problems from the last submit
        self.given: Optional[str] = None          # the confirmed indication's text (None: the model finds it)
        self.first: Optional[dict] = None         # the first passing submit's tree (the sweep starts from it)
        self.sweep_cut = False                    # a cap ended the sweep
        self.changes: list[dict] = []             # every update / removal / replacement, old and new
        self.removed: list[dict] = []             # {id, quote, why}: shown to the reviewer

    # ------------------------------------------------ dispatch

    def handle(self, name: str, args: dict) -> dict:
        allowed = AUDIT_TOOLS if self.audit else tuple(TOOLS)
        if name not in allowed:
            return {"ok": False, "problems": [f"no tool '{name}' here; use {', '.join(allowed)}"]}
        return getattr(self, "t_" + name)(**{k: v for k, v in (args or {}).items()
                                             if k in TOOLS[name]["parameters"]["properties"]})

    # ------------------------------------------------ quotes

    def locate(self, quote: str) -> Optional[tuple[list[str], str]]:
        return criteria.find(quote, self.spans)

    def nearest(self, quote: str, k: int = 3) -> list[dict]:
        """The k lines (or two adjacent lines, for a wrapped sentence) sharing the most words with the quote."""
        want = set(_words(quote))
        if not want:
            return []
        cands = []
        for i, s in enumerate(self.spans):
            for j in (i, i + 1):
                if j >= len(self.spans):
                    continue
                txt = " ".join(x.text.strip() for x in self.spans[i:j + 1])
                score = len(want & set(_words(txt))) / len(want) - 0.01 * (j - i)
                cands.append((score, self.spans[i].id if i == j else f"{self.spans[i].id}-{self.spans[j].id}", txt))
        cands.sort(key=lambda c: -c[0])
        out, seen = [], set()
        for score, lines, txt in cands:
            first = lines.split("-")[0]
            if score <= 0 or first in seen:
                continue
            seen.add(first)
            out.append({"lines": lines, "text": txt})
            if len(out) == k:
                break
        return out

    # ------------------------------------------------ logic

    def parse(self, logic: str, where: str) -> tuple[Optional[Any], list[str]]:
        problems: list[str] = []
        e = from_logic(logic, problems, where) if isinstance(logic, str) else None
        if not isinstance(logic, str):
            problems.append(f"{where}: logic must be a string")
        if e is None:
            return None, problems
        for x in leaf_ids(e):
            if x not in self.conds and x not in self.blocks:
                problems.append(f"unknown id '{x}' (add it with add_condition, or define the block first)")
        return (None if problems else e), problems

    def expand(self, e: Any, blocks: Optional[dict] = None) -> Any:
        return helpers.expand(e, self.blocks if blocks is None else blocks)

    def used(self) -> set[str]:
        return {i for e in self.logic.values() for i in leaf_ids(self.expand(e))}

    # ------------------------------------------------ tools

    def t_find(self, text: str = "") -> dict:
        words = (text or "").split()
        if not words:
            return {"ok": False, "problems": ["empty search"]}
        flat, starts = criteria._flat(self.spans)
        pat = r"\s+".join(re.escape(w) for w in words)
        hits = self._hits([m.span() for m in re.finditer(pat, flat, re.I)], flat, starts)
        how = "phrase"
        if not hits and len(words) > 1:            # each word: lines holding the most of them
            how = "words"
            ws = [w.lower() for w in words if len(w) > 2] or [w.lower() for w in words]
            scored = [(sum(w in s.text.lower() for w in ws), s) for s in self.spans]
            scored = [x for x in scored if x[0]]
            scored.sort(key=lambda x: -x[0])
            hits = [{"lines": s.id, "text": s.text.strip()} for _, s in scored[:10]]
        return {"ok": True, "hits": hits, **({"matched": "some of the words, not the phrase"} if how == "words" else {})}

    def _hits(self, spans_at, flat, starts) -> list[dict]:
        out, seen = [], set()
        for a, b in spans_at:
            ids = [i for k, (st, i) in enumerate(starts)
                   if st <= b - 1 and (starts[k + 1][0] if k + 1 < len(starts) else len(flat) + 1) > a]
            if not ids or ids[0] in seen:
                continue
            seen.add(ids[0])
            out.append({"lines": ids[0] if len(ids) == 1 else f"{ids[0]}-{ids[-1]}",
                        "text": " ".join(self.tbl[i].text.strip() for i in ids)})
            if len(out) == 10:
                break
        return out

    def t_read(self, first: str = "", last: str = "") -> dict:
        if first not in self.tbl or last not in self.tbl:
            bad = [x for x in (first, last) if x not in self.tbl]
            return {"ok": False, "problems": [f"no line '{x}' (ids run {self.ids[0]}..{self.ids[-1]})" for x in bad]}
        a, b = self.ids.index(first), self.ids.index(last)
        if b < a:
            a, b = b, a
        b = min(b, a + 119)
        return {"ok": True, "lines": [f"{i} {self.tbl[i].text}" for i in self.ids[a:b + 1]],
                **({"truncated": True} if b < max(self.ids.index(first), self.ids.index(last)) else {})}

    def t_add_condition(self, id: str = "", quote: str = "", question: str = "", threshold: Any = None,
                        answerable: Any = True) -> dict:
        problems = []
        if (not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*", id or "") or (id or "").isdigit()
                or id.lower() in ("and", "or", "not", "of", "at_least")):
            problems.append("id must be short snake_case (letters, digits, _; not a bare number), not a keyword")
        elif id in self.conds or id in self.blocks:
            problems.append("id already used")
        if not (question or "").strip():
            problems.append("question is empty")
        if threshold is not None and (not isinstance(threshold, dict) or threshold.get("op") not in OPS
                                      or "value" not in threshold):
            problems.append("threshold must be {\"op\": one of >=, >, <=, <, ==, \"value\": ..., \"unit\": ...}")
        hit = self.locate(quote)
        if hit is None:
            problems.insert(0, "quote not found")
            return {"ok": False, "problems": problems, "nearest": self.nearest(quote)}
        if problems:
            return {"ok": False, "problems": problems}
        refs, text = hit
        self.conds[id] = {"quote": text, "refs": refs, "question": question.strip(), "threshold": threshold,
                          "answerable": answerable is not False, "audit": self.audit}
        return {"ok": True, "id": id, "lines": refs[0]}

    def t_define_block(self, name: str = "", logic: str = "") -> dict:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", name or ""):
            return {"ok": False, "problems": ["name must be short snake_case"]}
        if name in self.conds:
            return {"ok": False, "problems": [f"'{name}' is already a condition id"]}
        e, problems = self.parse(logic, f"block {name}")
        if e is None:
            return {"ok": False, "problems": problems}
        trial = {**self.blocks, name: e}
        try:
            flat = self.expand(name, trial)
        except helpers.TreeError as x:
            return {"ok": False, "problems": [str(x)]}
        if name in self.blocks and self.blocks[name] != e:
            self.changes.append({"tool": "define_block", "name": name, "old": show(self.blocks[name]), "new": show(e)})
        self.blocks = trial
        return {"ok": True, "name": name, "expanded": show(flat)}

    def t_set_logic(self, indication: str = "", logic: str = "") -> dict:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.\-]*", indication or ""):
            return {"ok": False, "problems": ["indication must be a short snake_case id"]}
        e, problems = self.parse(logic, f"logic for {indication}")
        if e is None:
            return {"ok": False, "problems": problems}
        try:
            flat = self.expand(e)
        except helpers.TreeError as x:
            return {"ok": False, "problems": [str(x)]}
        if self.audit:
            if indication not in self.locked:
                return {"ok": False, "problems": [f"the check may only tighten existing indications "
                                                  f"({', '.join(self.locked)}); a new indication would widen approval"]}
            lost = sorted(self.locked[indication] - set(leaf_ids(flat)))
            if lost:
                return {"ok": False, "problems": [f"the check may only tighten: this logic drops {', '.join(lost)}; "
                                                  "keep every existing condition"]}
        if indication in self.logic and self.logic[indication] != e:
            self.changes.append({"tool": "set_logic", "indication": indication, "old": show(self.logic[indication]),
                                 "new": show(e)})
        self.logic[indication] = e
        used = self.used()
        return {"ok": True, "indication": indication, "expanded": show(flat),
                "unused_conditions": [i for i in self.conds if i not in used]}

    def t_update_condition(self, id: str = "", quote: Optional[str] = None, question: Optional[str] = None,
                           threshold: Any = None, answerable: Optional[bool] = None) -> dict:
        if id not in self.conds:
            return {"ok": False, "problems": [f"no condition '{id}' (add it with add_condition)"]}
        old = self.conds[id]
        new = dict(old)
        problems = []
        if question is not None:
            if not question.strip():
                problems.append("question is empty")
            new["question"] = question.strip()
        if threshold is not None:
            if not isinstance(threshold, dict) or threshold.get("op") not in OPS or "value" not in threshold:
                problems.append("threshold must be {\"op\": one of >=, >, <=, <, ==, \"value\": ..., \"unit\": ...}")
            new["threshold"] = threshold
        if answerable is not None:
            new["answerable"] = answerable is not False
        if quote is not None:
            hit = self.locate(quote)
            if hit is None:
                return {"ok": False, "problems": ["quote not found"] + problems, "nearest": self.nearest(quote)}
            new["refs"], new["quote"] = hit
        if problems:
            return {"ok": False, "problems": problems}
        diff = {k: (old[k], new[k]) for k in new if old.get(k) != new[k]}
        if diff:
            self.changes.append({"tool": "update_condition", "id": id, "old": {k: v[0] for k, v in diff.items()},
                                 "new": {k: v[1] for k, v in diff.items()}})
        self.conds[id] = new
        return {"ok": True, "id": id, "lines": new["refs"][0]}

    def t_remove_condition(self, id: str = "", why: str = "") -> dict:
        if id not in self.conds:
            return {"ok": False, "problems": [f"no condition '{id}'"]}
        if not (why or "").strip():
            return {"ok": False, "problems": ["why is required: one sentence saying why this is not a condition"]}
        where = [f"set_logic {k}" for k, v in self.logic.items() if id in leaf_ids(v)]
        where += [f"define_block {k}" for k, v in self.blocks.items() if id in leaf_ids(v)]
        if where:
            return {"ok": False, "problems": [f"still used in: {', '.join(where)}"]}
        c = self.conds.pop(id)
        self.removed.append({"id": id, "quote": c["quote"], "why": why.strip()})
        self.changes.append({"tool": "remove_condition", "id": id, "old": c, "why": why.strip()})
        return {"ok": True, "removed": id}

    def t_show(self) -> dict:
        used = self.used()
        return {"ok": True,
                "conditions": [{"id": i, "quote": c["quote"], "lines": c["refs"][0], "question": c["question"],
                                "threshold": c["threshold"], "answerable": c["answerable"]} for i, c in self.conds.items()],
                "blocks": {k: show(v) for k, v in self.blocks.items()},
                "logic": {k: show(self.expand(v)) for k, v in self.logic.items()},
                "unused_conditions": [i for i in self.conds if i not in used]}

    def t_submit(self, indication_quotes: Any = None, not_covered: Optional[str] = None, notes: str = "") -> dict:
        self.submits += 1
        problems = []
        qs = [indication_quotes] if isinstance(indication_quotes, str) else list(indication_quotes or [])
        found = []
        for q in qs:
            hit = self.locate(q)
            if hit is None:
                problems.append(f"indication quote not found: {q[:100]!r}")
            else:
                found.append(hit[1])
        nc = None
        if not_covered:
            hit = self.locate(not_covered)
            if hit is None:
                problems.append(f"not_covered quote not found: {not_covered[:100]!r}")
            else:
                nc = hit[1]
        if not self.logic and not not_covered:
            problems.append("no indication has logic: call set_logic (or give not_covered)")
        if not qs and not not_covered and not self.audit:
            problems.append("indication_quotes is empty: quote the sentence(s) that grant each indication you used")
        used = self.used()
        unused = [i for i in self.conds if i not in used]
        if unused and self.logic:
            problems.append(f"conditions not used in any logic: {', '.join(unused)}")
        self.last = problems
        if problems:
            return {"ok": False, "problems": problems, **({"submits_left": MAX_SUBMITS - self.submits}
                                                          if not self.audit else {})}
        if self.audit:
            self.quotes += [q for q in found if q not in self.quotes]
            self.notes = (self.notes + "\n\nCheck: " + notes).strip() if notes else self.notes
        else:
            self.quotes, self.not_covered, self.notes = found, nc, notes or ""
            if self.first is None:                # the first passing tree: not accepted until the sweep
                self.first = copy.deepcopy({k: getattr(self, k) for k in SNAPSHOT})
                return {"ok": True, "accepted": False, "next": SWEEP_NEXT}
        self.done = True
        return {"ok": True}

    def first_stands(self) -> None:
        """A cap ended the sweep: the first passing tree is the answer."""
        for k, v in copy.deepcopy(self.first).items():
            setattr(self, k, v)
        self.done = True

    # ------------------------------------------------ the result

    def tree_text(self) -> str:
        """The working tree as the audit reads it."""
        return json.dumps({
            "conditions": [{"id": i, "quote": c["quote"], "question": c["question"]} for i, c in self.conds.items()],
            "blocks": {k: show(v) for k, v in self.blocks.items()},
            "logic": {k: show(v) for k, v in self.logic.items()},
            "indication_quotes": self.quotes, "notes": self.notes}, indent=1)


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (s or "").lower())


# ---------------------------------------------------------------- the sessions


def given_step(text: str, ind: Optional[str] = None) -> str:
    """The instructions with step 1 (find the indication) replaced by the given-pathway rule (reduce only this
    pathway, against the whole policy; it is under "The confirmed indication" in the message)."""
    a, b = text.index("1. Find the indication(s)"), text.index("2. Add every condition")
    rule = given_rule(ind).replace("\n", " ").strip()
    return (text[:a] + "1. " + rule + " It is under \"The confirmed indication\" in the message. Quote the sentence"
            " that grants it when you submit.\n" + text[b:])


def confirmed(n: Narrowed, pid: str, spans: list[Span], given: Optional[str]) -> Optional[str]:
    """The confirmed indication's text: given (the runner's heading arm), else the confirmed pathway's own lines (the
    product), else None (the model finds it)."""
    if given:
        return given
    from .spans import in_range
    p = next((x for x in n.pathways if x.id == pid), None)
    if p is None or not p.spans:
        return None
    return "\n".join(s.text for r in p.spans for s in in_range(spans, r))


def instructions(payer: str, given: Optional[str] = None) -> str:
    """`given`: the confirmed indication's text (None: the model finds it)."""
    out = llm.prompt("reduce/tools", payer=payer or "the payer")
    if given:
        out = given_step(out, given)
    out += "\n\n" + llm.prompt("reduce/plan") + "\n\n" + llm.prompt("reduce/sweep")
    if os.environ.get("PITFALLS", "0") == "1":
        out += "\n\n" + llm.prompt("reduce/pitfalls")
    return out


def user_message(order: str, codes: str, text: str, indication: Optional[str] = None) -> str:
    ind = f"## The confirmed indication\n{indication}\n" if indication else ""
    return f"## The order\n{order}\n{ind}## Codes on the order\n{codes}\n## The guideline\n{text}"


def codes_json(codes: list[Code]) -> str:
    """The order's code rows with their full descriptions (no truncation)."""
    return json.dumps([{"code": c.code, "tag": c.tag, "description": c.description} for c in codes], indent=1)


def session(st: State, run_id: str, msg: str, payer: str, model: str) -> tuple[list[str], dict]:
    """The main session: (outstanding problems, usage)."""
    def done():
        return st.done or st.submits >= MAX_SUBMITS
    usage = llm.call_tools(run_id, "criteria_tools", instructions(payer, st.given), msg, schemas(), st.handle, done,
                           model=model, max_calls=MAX_CALLS)
    problems = []
    if not st.done and st.first is not None:      # a cap ended the sweep: the first passing tree stands
        logger.warning("tools: the sweep did not finish (%s); the first passing tree stands",
                       "call cap" if usage["capped"] else f"{st.submits} submits")
        st.first_stands()
        st.sweep_cut = True
    if not st.done:
        why = ("the tool-call cap was reached" if usage["capped"] else f"{st.submits} submits failed"
               if st.submits >= MAX_SUBMITS else "the model stopped without a successful submit")
        problems.append(f"not finished: {why}")
        problems += st.last
    return problems, usage


def audit(st: State, run_id: str, msg: str, payer: str, model: str) -> tuple[list[str], list[str], dict]:
    """The add-only check: (loopholes, problems, usage). Leaves may be added, never dropped."""
    st.audit, st.done, st.submits = True, False, 0
    st.locked = {k: set(leaf_ids(st.expand(v))) for k, v in st.logic.items()}
    before = set(st.conds)
    text = llm.prompt("reduce/tools_audit", tree=st.tree_text()) + "\n\n" + msg
    usage = llm.call_tools(run_id, "criteria_tools_audit", instructions(payer, st.given), text, schemas(AUDIT_TOOLS),
                           st.handle, lambda: st.done or st.submits >= 2, model=model, max_calls=AUDIT_CALLS)
    said = st.notes.split("\n\nCheck: ", 1)[1] if "\n\nCheck: " in st.notes else ""
    loopholes = [ln.strip("-• ").strip() for ln in said.splitlines()
                 if ln.strip() and ln.strip("-• .").strip().lower() not in ("none found", "none", "nothing found")][:20]
    problems = []
    unused = [i for i in st.conds if i not in before and i not in st.used()]
    if unused:   # found by the check but not wired in: a person decides where it goes
        problems.append(f"the check added {', '.join(unused)} but did not use it in the logic")
    return loopholes, problems, usage


def to_criteria(st: State) -> list[Criterion]:
    return [Criterion(id=i, refs=c["refs"], quote=c["quote"], answerable=c["answerable"], question=c["question"],
                      threshold=criteria._threshold(_T(**c["threshold"])) if c["threshold"] else None)
            for i, c in st.conds.items()]


def expression(st: State, pid: str) -> Optional[Expression]:
    """Each indication's logic, blocks expanded; several are ORed (the chart decides which route)."""
    ex = [st.expand(e) for e in st.logic.values()]
    if not ex:
        return None
    return Expression(pathway=pid, expr=ex[0] if len(ex) == 1 else {"any": ex})


# ---------------------------------------------------------------- build (the drop-in)


def build(spans: list[Span], n: Narrowed, sel: Selection, key: str, run_id: str,
          procedure: Optional[Procedure] = None, extra: Optional[dict] = None,
          indication: Optional[str] = None) -> CriteriaSet:
    want = picked(sel)
    on = {c for p in n.pathways if p.id in want for c in p.codes} | {x.code for x in sel.code_gate}
    codes = [c for c in n.codes if c.code in on] or n.codes
    payer = n.guideline.payer.name if n.guideline and n.guideline.payer else ""
    ind = "\n\n".join(x for x in (confirmed(n, pid, spans, indication) for pid in want) if x) or None
    msg = user_message(order_json(procedure, extra), codes_json(codes), guideline_text(spans), ind)
    model = llm.pick_models()[0]
    st = State(spans)
    st.given = ind
    problems, u1 = session(st, run_id, msg, payer, model)
    swept = ("Sweep: cut off by a cap; the first passing tree stands" if st.sweep_cut else
             sweep_note(set(st.first["conds"]), set(st.conds), []) if st.first and st.done else "")
    loopholes, u2 = [], None
    if st.done and st.logic:
        try:
            loopholes, p2, u2 = audit(st, run_id, msg, payer, model)
            problems += p2
        except Exception as x:          # the check only adds; the first reading stands without it
            logger.warning("tools audit failed: %s", x)
            problems.append(f"audit failed: {type(x).__name__}")
    nc, nc_note = not_covered(st.not_covered, bool(st.logic or st.quotes))
    if nc:
        problems.append(nc)
    exprs = [e for e in (expression(st, pid) for pid in want) if e is not None]
    used = {i for e in exprs for i in leaf_ids(e.expr)}
    notes = [st.notes, nc_note, swept]
    if u2 and u2.get("capped"):
        logger.warning("tools audit hit its %d-call cap", AUDIT_CALLS)
        notes.append(f"The check hit its {AUDIT_CALLS}-call cap.")
    if st.quotes:
        notes.append("Indication used: " + " | ".join(st.quotes))
    if len(st.logic) > 1:
        notes.append("Routes (ORed): " + "; ".join(f"{k}: {show(v)}" for k, v in st.logic.items()))
    cs = CriteriaSet(key=key, criteria=[c for c in to_criteria(st) if c.id in used], expressions=exprs,
                     notes="\n\n".join(x for x in notes if x), loopholes=loopholes,
                     status="needs_review" if problems else "ok", problems=problems, run_id=run_id)
    cs.removed_conditions = st.removed
    if st.changes:
        llm._log(run_id, "criteria_tools-changes", {"changes": st.changes})
    spend = {"main": u1, **({"audit": u2} if u2 else {})}
    llm._log(run_id, "criteria_tools-cost", spend)
    logger.info("criteria (tools) %s: %d criteria, %d route(s), %d loophole(s), %s, %d+%d tool calls, $%.2f", key,
                len(cs.criteria), len(st.logic), len(loopholes), cs.status, u1["calls"], (u2 or {}).get("calls", 0),
                sum(v["dollars"] for v in spend.values()))
    return cs
