# Known-structure hints

Read by `app/hints.py`, only when `STRUCTURE_HINTS=1` (default off). This folder ships empty: QA writes the hint
files in `experiments/structure_hints/` on the guideline-reduce worktree and the lead engineer copies them here.

- `payers/<name>.md`: how one payer's guidelines are laid out and what each section means. Injected into step H
  (loose and loose-next; the main prompt and the audit) as `## What this payer's guidelines look like`, just
  before `## The guideline`.
- `clinics/<name>.md`: where evidence lives in one clinic's charts. Injected into step A2 (`chart_sections`) and
  the judge (`judge_chart`) as `## What this clinic's charts look like`, just before `## Chart`.

Each file is a small front-matter block, then the text to inject:

```
---
match:
  - Florida Blue
  - BCBSFL
where: first 40 lines
---
Clinical conditions almost always live in POSITION STATEMENT; BILLING/CODING and REIMBURSEMENT are admin unless ...
```

- `match`: literal strings, case-insensitive. The file applies when ANY of them appears in the searched lines.
- `where`: `first N lines` of the guideline (payers) or the chart (clinics); 40 when absent.
- If two files of a kind match, none is used (logged). No match: the prompt is exactly the shipped one.
- The file's name and a hash of its bytes go into the cache keys (H's prompt version; A2's sections.json), so
  editing a hint never serves a result built with the old one.

This README is not a hint (it has no front matter and sits outside `payers/` and `clinics/`).
