"""Reading facts out of text the code has already resolved: dates, numbers, and loose matching for checks."""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

_MONTHS = {m: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november",
     "december"])}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_DATE_RE = re.compile(
    r"\b(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<y>\d{4})\b"
    r"|\b(?P<m2>\d{1,2})[/-](?P<d2>\d{1,2})[/-](?P<y2>\d{2,4})\b"
    r"|\b(?P<y3>\d{4})-(?P<m3>\d{2})-(?P<d3>\d{2})\b"
    r"|\b(?P<d4>\d{1,2})\s+(?P<mon4>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?,?\s+(?P<y4>\d{4})\b", re.I)


def _to_iso(m: re.Match) -> Optional[str]:
    try:
        if m.group("mon"):
            mon = _MONTHS.get(m.group("mon").lower()[:4]) or _MONTHS.get(m.group("mon").lower()[:3])
            return date(int(m.group("y")), mon, int(m.group("d"))).isoformat()
        if m.group("m2"):
            y = int(m.group("y2"))
            y = y + 2000 if y < 100 else y
            return date(y, int(m.group("m2")), int(m.group("d2"))).isoformat()
        if m.group("y3"):
            return date(int(m.group("y3")), int(m.group("m3")), int(m.group("d3"))).isoformat()
        mon = _MONTHS.get(m.group("mon4").lower()[:4]) or _MONTHS.get(m.group("mon4").lower()[:3])
        return date(int(m.group("y4")), mon, int(m.group("d4"))).isoformat()
    except ValueError:
        return None


def find_dates(s: str) -> list[str]:
    """Every date written in `s`, as ISO strings, in order of appearance."""
    return [d for m in _DATE_RE.finditer(s) if (d := _to_iso(m))]


def months_between(a: str, b: str) -> float:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days / 30.4375


_DASHES = "‐‑‒–—―−"


def normalize(s: str) -> str:
    """Whitespace, dash, quote and punctuation-insensitive form used only for matching."""
    s = s.lower()
    for d in _DASHES:
        s = s.replace(d, "-")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"[^a-z0-9]+", "", s)


def contains(text: str, needle: str) -> bool:
    n = normalize(needle)
    return bool(n) and n in normalize(text)


def written_in(lines: list[str], needle: str, depth: int = 3) -> bool:
    """`needle` is written in the lines, read loosely (`contains`), even where it wraps onto the next line(s). A chart
    printed in two columns interleaves them ("Plan Name: AARP Medicare Advantage Choice   Plan ID: H0062-001-000" /
    "PPO"), so joining whole lines is not enough: a column cell (split on runs of 3+ spaces) is also read on into any
    cell of the next line or two."""
    if not normalize(needle):
        return False
    if contains(" ".join(lines), needle):
        return True
    cells = [[c for c in re.split(r"\s{3,}", ln.strip()) if c] for ln in lines]
    n = normalize(needle)
    for i in range(len(cells)):
        heads = [normalize(c) for c in cells[i]]
        for j in range(i + 1, min(i + depth, len(cells))):
            heads = [h + normalize(c) for h in heads for c in cells[j]]
            if any(n in h for h in heads):
                return True
    return False


def number_in(text: str, value: str) -> bool:
    """The value is written in the text as a number ("5" in "5 mm", "5.0" in "5.0mm", not in "15")."""
    try:
        v = float(str(value).replace(",", "").strip())
    except ValueError:
        return contains(text, str(value))
    for m in re.finditer(r"(?<![\d.])\d+(?:,\d{3})*(?:\.\d+)?", text):
        try:
            if abs(float(m.group(0).replace(",", "")) - v) < 1e-9:
                return True
        except ValueError:
            continue
    return False


def to_float(value) -> Optional[float]:
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
