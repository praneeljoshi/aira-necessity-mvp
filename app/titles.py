"""What a guideline is called on screen: its own title and number, read by code from its first lines, never the
file name (that is only the last fallback). A display aid, like tree.note_heading; nothing is decided from it.

    title    "Subject: Treatments for Varicose Veins/Venous" + "Insufficiency" -> "Treatments for Varicose Veins /
             Venous Insufficiency"; an NCD's title is the line after its "National Coverage Determination (NCD) N"
    number   a Florida Blue style number "02-33000-31" -> "Medical Coverage Guideline 02-33000-31";
             "National Coverage Determination (NCD) 20.8.3" -> "National Coverage Determination 20.8.3"
    issuer   the payer named in step C's guideline.json, else the first line when it names an agency ("Centers for
             Medicare & Medicaid Services" -> "CMS")
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .models import Span

HEAD = 14                     # lines read from the top of the document
SHORT = {"Centers for Medicare & Medicaid Services": "CMS", "Blue Cross and Blue Shield of Florida": "Florida Blue",
         "BCBSF": "Florida Blue"}


def _clean(t: str) -> str:
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\s*/\s*", " / ", t)


def read(spans: list[Span], payer: Optional[str], filename: str) -> dict:
    lines = [s.text.strip() for s in spans[:HEAD]]
    title = number = None
    for i, t in enumerate(lines):
        m = re.match(r"^Subject:\s*(.+)$", t, re.I)
        if m and not title:
            parts = [m.group(1)]
            for nxt in lines[i + 1: i + 3]:            # a subject that wraps: the next short line that is not a heading
                if nxt and not nxt.isupper() and len(nxt) < 70 and not re.match(r"^\w[\w ]*:", nxt):
                    parts.append(nxt)
                else:
                    break
            title = _clean(" ".join(parts))
        m = re.search(r"National Coverage Determination \(NCD\)\s*([\d.]+)", t)
        if m and not number:
            number = f"National Coverage Determination {m.group(1)}"
            if not title and i + 1 < len(lines) and lines[i + 1]:
                title = _clean(lines[i + 1])
        if re.fullmatch(r"\d{2}-\d{5}-\d{2}", t) and not number:
            number = f"Medical Coverage Guideline {t}"
    issuer = payer or (lines[0] if lines and re.search(r"Services|Administration|Blue|Health", lines[0]) else None)
    issuer = SHORT.get(issuer or "", issuer)
    stem = re.sub(r"[_-]+", " ", Path(filename or "").stem).strip()
    return {"title": title or (stem[:1].upper() + stem[1:] if stem else ""), "number": number or "",
            "issuer": issuer or "", "known": bool(title)}


@lru_cache(maxsize=64)
def _cached(sha: str, gid: str, payer: Optional[str]) -> dict:
    from . import store
    spans, _, filename = store.load_guideline_spans(gid)
    return read(spans, payer, filename)


def of(gid: str, sha: str, payer: Optional[str]) -> dict:
    """The label for a guideline on file, cached by its sha256 (the same file always reads the same)."""
    try:
        return dict(_cached(sha, gid, payer))
    except FileNotFoundError:
        return {"title": gid, "number": "", "issuer": payer or "", "known": False}
