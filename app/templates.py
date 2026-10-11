"""What the coordinator reads (step L text). Vocabulary: requirement / documented / ask / packet; never criterion,
verdict, confidence, pathway, span. The ask never decides for the patient: NOT_COVERED and NOT_MET ask the surgeon
to review, name what the guideline says, and end with a question. No text here predicts a payer's decision
("will deny", "denied"): a gap is described as what the policy asks for (tests/test_templates.py)."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .models import Criterion, Order, Threshold

OP_WORDS = {"gte": "at least", "gt": "more than", "lte": "at most", "lt": "less than", "eq": "exactly"}
TIME = {"month", "months", "week", "weeks", "day", "days", "year", "years"}


def fmt_date(iso: Optional[str], year: bool = True) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso)
    return f"{d.strftime('%B')} {d.day}" + (f", {d.year}" if year else "")


def dates_phrase(isos: list[str]) -> str:
    ds = sorted(set(i for i in isos if i))
    if not ds:
        return "the case"
    one_year = len({d[:4] for d in ds}) == 1
    parts = [fmt_date(d, year=not one_year) for d in ds]
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return text + (f", {ds[0][:4]}" if one_year else "")


def short(text: str, n: int = 220) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def salutation(name: Optional[str]) -> str:
    """'Dr. Elena Vasquez, MD, FACS' -> 'Dr. Vasquez'; nothing -> 'Doctor'."""
    if not name or not name.strip():
        return "Doctor"
    core = re.sub(r"^(dr\.?|doctor)\s+", "", name.split(",")[0].strip(), flags=re.I)
    last = core.split()[-1] if core.split() else ""
    return f"Dr. {last}" if last else "Doctor"


def clip(q: str) -> str:
    """A quote's own end, tidied for showing inside quotation marks: trailing periods and a dangling ',' ';' ':' are
    dropped ("endovenous radiofrequency,." -> "endovenous radiofrequency"); nothing else in it changes, case included."""
    return re.sub(r"[\s.,;:]+$", "", (q or "").strip())


def item(words: str, need: str) -> str:
    """One line of an ask: the guideline's words as quoted, then what is needed. The quote is never placed inside a
    sentence of ours, so the line reads the same whatever the quote's shape."""
    return f"“{clip(words)}” — {need}"


def join_request(parts: list[str]) -> str:
    """A Miss's ask: its request pieces on one line."""
    return " ".join(x.strip() for x in parts if x and x.strip())


def procedure_phrase(order: Order) -> str:
    p = order.procedure
    if p.as_written:
        return p.as_written if not p.cpt else f"{p.as_written}, {'/'.join(p.cpt)}"
    return "CPT " + ", ".join(p.cpt) if p.cpt else "the planned procedure"


def request_lines(c: Optional[Criterion], text: str, payer: str, duration: bool, exclusion: bool = False) -> list[str]:
    """What to ask for, shaped by the requirement's threshold: the guideline's words, then what is needed."""
    t: Optional[Threshold] = c.threshold if c else None
    if exclusion:
        return [f"“{clip(text)}” (must not apply) — a note showing it does not apply to this patient."]
    if t and duration:
        thing = "compression stockings" if "compression" in text.lower() else "the treatment"
        using = "wearing them" if "compression" in text.lower() else "it"
        return [item(text, f"the date {thing} began, what was used, and whether symptoms improved after "
                           f"{OP_WORDS[t.op]} {t.value} {t.unit or 'months'} of {using}.")]
    if t:
        num = re.fullmatch(r"-?\d+(\.\d+)?", str(t.value).strip()) is not None
        if num:
            return [item(text, f"the measured value ({payer} requires {OP_WORDS[t.op]} {t.value} {t.unit or ''}".rstrip() + ").")]
        return [item(text, f"the documented {t.unit or 'class'} ({payer} requires {t.value} or greater).")]
    return [item(text, "a note that documents it.")]


def not_covered(who: str, patient: str, proc: str, payer: str, listed: str) -> str:
    return (f"{who} — could you review {patient}'s planned {proc} before I submit it? {payer}'s guideline lists "
            f"{listed}. I have not said anything to the patient. Should I submit it as written, or did you intend a "
            f"different procedure or code?")


def which_section(who: str, patient: str, proc: str, payer: str, options: list[str]) -> str:
    opts = "; ".join(f"“{short(o, 90)}”" for o in options)
    return (f"{who} — for {patient}'s prior auth ({proc}, {payer}), which of these is the procedure for? {opts}. "
            f"{payer}'s guideline has different requirements for each.")


def addendum(who: str, patient: str, proc: str, payer: str, lines: list[str], says: list[str], unmet: bool,
             have: list[str]) -> str:
    if unmet:
        out = [f"{who} — could you review {patient}'s prior auth ({proc}, {payer}) before I submit it?", ""]
    else:
        out = [f"{who} — for {patient}'s prior auth ({proc}, {payer}), could you add an addendum with:", ""]
    out += [f"{i}. {x}" for i, x in enumerate(lines, 1)]
    out.append("")
    if unmet:
        if have:
            out.append("The case does document: " + "; ".join(clip(t) for t in have) + ".")
        out.append("If something has changed since that note, an addendum would document it. If not, how would you "
                   "like to proceed? I have not sent anything to the payer or said anything to the patient.")
    elif says:
        says = _once(says)
        what = says[0] if len(says) == 1 else ", ".join(says[:-1]) + " and " + says[-1]
        gap = {1: "it does not give", 2: "neither gives"}.get(len(says), "none of them gives")
        many = len(lines) > 1
        out.append(f"{what[0].upper() + what[1:]}, but {gap} what {payer}'s guideline asks for. Could you add a note that "
                   f"shows {'these' if many else 'this'}? Thanks.")
    else:
        many = len(lines) > 1
        out.append(f"The case does not address {'these' if many else 'this'} yet. Could you add a note that shows "
                   f"{'them' if many else 'it'}? Thanks.")
    return quote_once("\n".join(out))


_SAYS = re.compile(r"says “([^”]*)”")


def chart_says(q: str) -> str:
    """How a chart quote is shown in an ask: 'the chart says “…”'."""
    return f"the case says “{clip(short(q))}”"


def _once(says: list[str]) -> list[str]:
    """'the chart … says “q”' items, each quote once (the first kept)."""
    out, seen = [], set()
    for x in says:
        m = _SAYS.search(x)
        k = m.group(1) if m else x
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out


def quote_once(text: str) -> str:
    """One draft shows a chart quote once: a later 'says “<same quote>”' reads 'says the same (quoted above)'."""
    seen: set[str] = set()

    def one(m: re.Match) -> str:
        if m.group(1) in seen:
            return "says the same (quoted above)"
        seen.add(m.group(1))
        return m.group(0)
    return _SAYS.sub(one, text)
