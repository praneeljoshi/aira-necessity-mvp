"""One readable log line per thing that happens. stderr, so it shows in the `make run` and `make cli` terminal.

    17:42:03 INFO  pipeline  ingest fl_varicose_veins_guideline.pdf: 41,796 chars (core 17,041) -> structuring
    17:42:03 INFO  llm       -> structure_guideline [gpt-5.5] 18,210 chars
    17:43:21 INFO  llm       <- structure_guideline ok 78.0s, 14,746 tokens (dropped: temperature)

LOG_LEVEL=DEBUG shows the full parameter sets and prompt sizes per attempt.
"""
from __future__ import annotations

import logging
import os
import sys

_done = False


def setup() -> None:
    global _done
    if _done:
        return
    _done = True
    level = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)-5s %(name)-9s %(message)s", datefmt="%H:%M:%S"))
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level)
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "openai", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get(name: str) -> logging.Logger:
    setup()
    return logging.getLogger(name)


def n(x: int) -> str:
    return f"{x:,}"
