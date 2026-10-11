"""Known-structure hints (STRUCTURE_HINTS=1, default off). Pure code, no model.

For a payer we know, step H (loose and loose-next: the main prompt and the audit) gets a short block on that payer's
guideline layout; for a clinic chart format we know, A2 (app/ingest/sections.py) and the judge (app/evidence/judge.py) get a block on
where evidence lives in that clinic's charts. Unknown payer or clinic, two files matching, or the flag off: no block,
and the prompt is exactly the shipped one.

A hint file is `<DIR>/payers/<name>.md` or `<DIR>/clinics/<name>.md`:

    ---
    match:
      - Florida Blue
      - BCBSFL
    where: first 40 lines
    ---
    The text injected into the prompt.

`match`: literal strings, case-insensitive; the file matches when ANY appears in the searched lines. `where`: how many
of the document's first lines are searched (`first N lines`; 40 when absent): the guideline's for a payer, the chart's
for a clinic. The shipped prompts are hashed and frozen, so there is no placeholder: `inject` puts the block in the
rendered text just before the guideline / chart heading.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.core import log
from app.core.models import Span

logger = log.get("hints")

DIR = Path(os.environ.get("STRUCTURE_HINTS_DIR") or Path(__file__).resolve().parents[2] / "prompts" / "hints")
LINES = 40

PAYER_TITLE = "## What this payer's guidelines look like"
CLINIC_TITLE = "## What this clinic's charts look like"
GUIDELINE_HEADING = "## The guideline"
CHART_HEADING = "## Chart"


@dataclass(frozen=True)
class Hint:
    name: str
    match: tuple[str, ...]
    lines: int
    text: str
    sha: str

    @property
    def id(self) -> str:
        """`<name>.<sha8 of the file>`: what goes into a cache key, so an edited hint never serves an old result."""
        return f"{self.name}.{self.sha[:8]}"


def enabled() -> bool:
    return os.environ.get("STRUCTURE_HINTS", "0") == "1"


def parse(raw: str, name: str) -> Optional[Hint]:
    """A hint file's front matter and body; None (logged) when the front matter is missing or names no match."""
    m = re.match(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?(.*)\Z", raw, re.S)
    if not m:
        logger.warning("hint %s: no front matter; ignored", name)
        return None
    head, body = m.group(1), m.group(2).strip()
    match: list[str] = []
    lines, key = LINES, None
    for line in head.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s*-\s*(.+?)\s*$", line)
        if item and key == "match":
            match.append(item.group(1).strip("\"'"))
            continue
        kv = re.match(r"^(\w+)\s*:\s*(.*?)\s*$", line)
        if not kv:
            continue
        key, val = kv.group(1).lower(), kv.group(2)
        if key == "match" and val:          # inline list: match: [a, b]
            match += [x.strip().strip("\"'") for x in val.strip("[]").split(",") if x.strip()]
        elif key == "where":
            n = re.search(r"\d+", val)
            lines = int(n.group(0)) if n else LINES
    match = [x for x in match if x]
    if not match or not body:
        logger.warning("hint %s: no match strings or no body; ignored", name)
        return None
    return Hint(name=name, match=tuple(match), lines=lines, text=body,
                sha=hashlib.sha256(raw.encode()).hexdigest())


def load(kind: str) -> list[Hint]:
    """Every hint file of a kind ("payers" or "clinics"), by file name."""
    d = DIR / kind
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.glob("*.md")):
        h = parse(p.read_text(), p.stem)
        if h is not None:
            out.append(h)
    return out


def find(kind: str, spans: list[Span]) -> Optional[Hint]:
    """The one hint of `kind` whose match strings appear in the document's first lines; None when the flag is off,
    nothing matches, or more than one file matches (conservative: logged, no block)."""
    if not enabled() or not spans:
        return None
    hits = []
    for h in load(kind):
        head = "\n".join(s.text for s in spans[:h.lines]).lower()
        if any(m.lower() in head for m in h.match):
            hits.append(h)
    if len(hits) > 1:
        logger.warning("structure hints: %d %s files match (%s); using none", len(hits), kind,
                       ", ".join(h.name for h in hits))
        return None
    return hits[0] if hits else None


def payer_hint(gspans: list[Span]) -> tuple[Optional[str], str]:
    """(the payer hint's name, its text) for a guideline; (None, "") when none applies."""
    h = find("payers", gspans)
    return (h.name, h.text) if h else (None, "")


def clinic_hint(rspans: list[Span]) -> tuple[Optional[str], str]:
    """(the clinic hint's name, its text) for a chart; (None, "") when none applies."""
    h = find("clinics", rspans)
    return (h.name, h.text) if h else (None, "")


def payer_id(gspans: list[Span]) -> Optional[str]:
    h = find("payers", gspans)
    return h.id if h else None


def clinic_id(rspans: list[Span]) -> Optional[str]:
    h = find("clinics", rspans)
    return h.id if h else None


def inject(prompt: str, heading: str, title: str, text: str) -> str:
    """The rendered prompt with `title` + `text` as a section just before the first line that is exactly `heading`.
    No text: the prompt unchanged (byte-identical). Heading not found: unchanged, logged."""
    if not text:
        return prompt
    m = re.search(rf"(?m)^{re.escape(heading)}[ \t]*$", prompt)
    if not m:
        logger.warning("structure hints: heading %r not in the prompt; no hint injected", heading)
        return prompt
    return prompt[:m.start()] + f"{title}\n{text}\n\n" + prompt[m.start():]


def for_guideline(prompt: str, text: str) -> str:
    return inject(prompt, GUIDELINE_HEADING, PAYER_TITLE, text)


def for_chart(prompt: str, text: str) -> str:
    return inject(prompt, CHART_HEADING, CLINIC_TITLE, text)
