"""PDF -> text. No OCR (known break)."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader


class EmptyPdfText(Exception):
    pass


def pdf_to_text(path: Path) -> str:
    text = ""
    if shutil.which("pdftotext"):
        try:
            text = subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True,
                                  timeout=60).stdout
        except Exception:
            text = ""
    if len(text.strip()) < 200:
        try:
            text = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
        except Exception:
            text = ""
    if len(text.strip()) < 50:
        raise EmptyPdfText("No extractable text; scanned PDFs are not supported (no OCR).")
    return text
