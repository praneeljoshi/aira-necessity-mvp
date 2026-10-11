"""python -m app.cli <chart.pdf> [guideline_id]   check one chart against one guideline on file (default: the first)
python -m app.cli add <guideline.pdf> [id]      put a guideline PDF on file (code only: spans, no model call)
python -m app.cli wipe [--all]                  forget CLI checks; --all forgets browser checks too"""
import hashlib
import sys
from pathlib import Path

from . import log, pipeline, store
from .pdf import pdf_to_text


def add(p: Path, gid: str | None = None) -> str:
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    gid = pipeline.add_guideline(pdf_to_text(p), p.name, sha, gid)
    print(f"on file as {gid} (data/guidelines/{gid}/spans.json)")
    return gid


def show(r) -> None:
    print(f"\n=== {r.determination} · {r.queue} ===\n{r.reason}")
    if r.pathway_used:
        print(f"Sections judged: {', '.join(r.pathway_used)}  (confidence {r.confidence:.2f})")
    if r.checklist:
        print("\nChecklist:")
        mark = {"MET": "✓", "NOT_MET": "✗", "INSUFFICIENT": "?"}
        for c in r.checklist:
            print(f"  {mark[c.status]} {c.text[:150]}")
            for q in c.quotes:
                print(f"      “{q.text[:120]}”{'  — ' + q.date if q.date else ''}  [{q.span}]")
    if r.review_reasons:
        print("\nReview:")
        for x in r.review_reasons:
            print(f"  - {x}")
    print("\nASK:\n" + r.ask)
    print(f"\nrun log: data/runs/{r.run_id}/   result: data/results/{r.order_id}/")


def main():
    log.setup()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "add":
        if len(sys.argv) < 3:
            print(__doc__); sys.exit(1)
        add(Path(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else None)
        return
    if sys.argv[1] == "wipe":
        c = store.wipe(everything="--all" in sys.argv[2:])
        print(f"forgot {c['charts']} chart(s), {c['results']} result(s), {c['runs']} run folder(s); guidelines untouched")
        return
    p = Path(sys.argv[1])
    gid = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else None
    if not gid:
        lib = store.list_guidelines()
        if not lib:
            print("No guideline on file. Run: python -m app.cli add guideline.pdf")
            sys.exit(1)
        gid = lib[0]["id"]
        print(f"(no guideline given; checking against {gid})")
    r = pipeline.run(pdf_to_text(p), p.stem, gid, filename=p.name, source="cli")
    show(r)


if __name__ == "__main__":
    main()
