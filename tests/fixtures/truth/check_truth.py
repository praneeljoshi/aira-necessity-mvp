"""Validate a hand-built ground-truth guideline against its PDF.

    python tests/fixtures/truth/check_truth.py tests/fixtures/truth/<slug>.json <guideline.pdf>

Schema (app.core.models.Guideline); every criterion and exclusion text verbatim in the PDF (whitespace, hyphenation and
quote marks normalised); leaf ids exist; every criterion used; every scope code appears in the PDF. Exit 1 on problems.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.core.models import Guideline  # noqa: E402
from app.ingest.pdf import pdf_to_text  # noqa: E402


def norm(s: str) -> str:
    s = s.replace("­", "").replace("\f", " ")
    s = re.sub(r"[‘’‚′]", "'", s)
    s = re.sub(r"[“”„″]", '"', s)
    s = re.sub(r"[‐-―−]", "-", s)
    s = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", s)          # hyphenation across a line break
    s = re.sub(r"[-•●○■□▪◦‣]", " ", s)          # bullet glyphs
    return re.sub(r"\s+", " ", s).strip().lower()


def leaves(n) -> list[str]:
    if n.type == "leaf":
        return [n.criterion]
    if n.type == "not":
        return leaves(n.child)
    return [x for c in n.children for x in leaves(c)]


def main(fixture: str, pdf: str) -> int:
    problems: list[str] = []
    g = Guideline.model_validate_json(Path(fixture).read_text())
    text = norm(pdf_to_text(Path(pdf)))
    nospace = text.replace(" ", "")
    ids = [c.id for c in g.criteria]
    if len(ids) != len(set(ids)):
        problems.append("duplicate criterion ids")
    for c in g.criteria:
        t = norm(c.text)
        if not t or (t not in text and t.replace(" ", "") not in nospace):
            problems.append(f"criterion '{c.id}' text not verbatim in the PDF: {c.text[:90]!r}")
    for e in g.exclusions:
        t = norm(e.text)
        if t not in text and t.replace(" ", "") not in nospace:
            problems.append(f"exclusion text not verbatim in the PDF: {e.text[:90]!r}")
    used: set[str] = set()
    for s in g.scenarios:
        for leaf in leaves(s.requires):
            used.add(leaf)
            if leaf not in ids:
                problems.append(f"scenario '{s.id}': unknown criterion '{leaf}'")
        for code in s.applies_to_cpt:
            if code not in g.scope.cpt:
                problems.append(f"scenario '{s.id}': code {code} not in scope.cpt")
    for i in ids:
        if i not in used:
            problems.append(f"criterion '{i}' used by no scenario")
    for code in g.scope.cpt:
        if code.lower() not in text:
            problems.append(f"scope code {code} does not appear in the PDF")
    if g.status == "ok" and not g.scenarios:
        problems.append("status ok but no scenarios")
    for p in problems:
        print("PROBLEM", p)
    print(f"{fixture}: {len(g.criteria)} criteria, {len(g.scenarios)} pathways, {len(g.scope.cpt)} codes, "
          f"{len(g.exclusions)} exclusions, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
