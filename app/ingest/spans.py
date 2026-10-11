"""Step A (code): extracted text -> numbered spans. Deterministic; no model, and no decisions.

A span is one line of the extracted PDF text, verbatim: tabs expanded to four spaces, trailing whitespace stripped,
leading whitespace kept (it is the line's indent, which shows what an AND/OR governs). g-spans for the guideline,
r-spans for the chart record; ids zero-padded to at least four digits (g0001, r0001).

Not spans: blank lines (there is nothing to cite) and page breaks (form feeds). Both stay visible to the model: the
renderer prints one empty line where a run of blank lines was and a `--- page N ---` line where a page starts.
Neither carries an id, so neither can be cited.

The model cites span ids, or a range "g0031-g0033" where a sentence, heading or table row wraps over lines. Every
model-facing id list holds such citations; `expand` turns them into ids and code expands before every check.
`text_of` joins the cited lines, each with its leading whitespace dropped, with single spaces, so a wrapped
requirement reads as one sentence.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Union

from app.core.models import Range, Span

Spans = Union[list[Span], dict[str, Span]]

# ---------------------------------------------------------------- glyphs

# PDFs set bullets in the Symbol and Wingdings fonts; text extraction returns those fonts' private-use code points
# (U+F0xx), which carry no meaning to a model. Each known one maps to the one Unicode character it draws, one
# character for one, so a line's length and indent never change. Meanings were read from the mined guidelines in
# context (2,200+ lines). Code points whose drawing is not certain (U+F0BF, U+F0DC, U+F078, U+F8xx) are left as
# extracted and counted by `unmapped_glyphs`.
GLYPHS = {
    0xF0B7: "•",   # Symbol bullet: the Florida Blue list bullet (1,549 in the mined set)
    0xF0A7: "▪",   # Wingdings small square: second-level bullet
    0xF0D8: "➢",   # Wingdings arrowhead bullet
    0xF076: "❖",   # Wingdings diamond bullet
    0xF0FC: "✓",   # Wingdings check mark
    0xF02D: "–",   # Symbol minus, used as a dash bullet
    0xF020: " ",   # Symbol space
    0xF0D3: "©",   # Symbol copyright ("© CPT Only – American Medical Association")
    0xF0D2: "®",
    0xF0D4: "™",
}
_PRIVATE = re.compile(r"[-]")


def unmapped_glyphs(text: str) -> dict[str, int]:
    """Private-use characters left after the map, as {"U+F0BF": 12}: what to look at next."""
    out: dict[str, int] = {}
    for ch in _PRIVATE.findall(text.translate(GLYPHS)):
        k = f"U+{ord(ch):04X}"
        out[k] = out.get(k, 0) + 1
    return out


# ---------------------------------------------------------------- split


def split(text: str, prefix: str) -> list[Span]:
    rows: list[tuple[str, int, bool]] = []   # (line, page, a blank line came before it)
    for page, body in enumerate(text.translate(GLYPHS).split("\f"), 1):
        blank = False
        for ln in body.split("\n"):
            ln = ln.replace("\t", "    ").rstrip()
            if not ln:
                blank = True
                continue
            rows.append((ln, page, blank))
            blank = False
    width = max(4, len(str(len(rows))))
    return [Span(id=f"{prefix}{n:0{width}d}", text=t, page=p, blank_before=b) for n, (t, p, b) in enumerate(rows, 1)]


def split_guideline(text: str) -> list[Span]:
    return split(text, "g")


def split_chart(text: str) -> list[Span]:
    return split(text, "r")


# ---------------------------------------------------------------- render


def render(spans: Iterable[Span]) -> str:
    """`[g0031] text` per span, the line as extracted (its indent after the id). A `--- page N ---` line where a
    page starts and an empty line where blank lines were; neither is a span."""
    out: list[str] = []
    page = None
    for s in spans:
        if s.page != page:
            out.append(f"--- page {s.page} ---")
            page = s.page
        if s.blank_before:
            out.append("")
        out.append(f"[{s.id}] {s.text}")
    return "\n".join(out)


render_guideline = render
render_chart = render


# ---------------------------------------------------------------- lookups


def table(spans: Iterable[Span]) -> dict[str, Span]:
    return {s.id: s for s in spans}


_RANGE = re.compile(r"([gr]\d+)\s*[-–—]\s*([gr]\d+)")


def expand(ids: Iterable[str], spans: Spans) -> list[str]:
    """Citations -> span ids: "g0010-g0014" becomes the ids from g0010 to g0014 (either order). Anything that does
    not resolve is kept as given, so checks can report it."""
    order = list(spans) if isinstance(spans, dict) else [s.id for s in spans]
    pos = {x: i for i, x in enumerate(order)}
    out: list[str] = []
    for x in ids:
        x = str(x).strip()
        m = _RANGE.fullmatch(x)
        if m and m.group(1) in pos and m.group(2) in pos:
            a, b = sorted((pos[m.group(1)], pos[m.group(2)]))
            out.extend(order[a: b + 1])
        else:
            out.append(x)
    return out


def resolves(cite: str, tbl: dict[str, Span]) -> bool:
    """The citation (an id or a range) names only spans in the table."""
    ids = expand([cite], tbl)
    return bool(ids) and all(i in tbl for i in ids)


def in_range(spans: list[Span], r: Range) -> list[Span]:
    ids = [s.id for s in spans]
    if r.first not in ids or r.last not in ids:
        return []
    a, b = ids.index(r.first), ids.index(r.last)
    return spans[a: b + 1] if a <= b else []


def text_of(ids: Iterable[str], tbl: dict[str, Span]) -> str:
    """The cited lines, ranges expanded, each stripped of its indent, joined with single spaces: a requirement that
    wraps over lines reads as one sentence. Unknown ids are skipped."""
    return " ".join(tbl[i].text.strip() for i in expand(ids, tbl) if i in tbl)


def locate(quote: str, text: str) -> Optional[str]:
    """The quote found in `text` (the cited lines joined), returned as the text's own characters, or None. Only
    whitespace and a hyphen broken across a line are forgiven; case, words and punctuation must match."""
    words = (quote or "").split()
    if not words:
        return None
    pat = r"\s+".join(re.escape(w) for w in words)
    m = re.search(pat, text)
    if m:
        return m.group(0)
    joined = re.sub(r"(\w)- (\w)", r"\1\2", text)     # "inter- fere" from a line break -> "interfere"
    m = re.search(pat, joined)
    return m.group(0) if m else None


def wording(c, tbl: dict[str, Span]) -> str:
    """What a person reads for a criterion: its checked quote, else its whole cited lines."""
    return c.quote or text_of(c.refs, tbl)
