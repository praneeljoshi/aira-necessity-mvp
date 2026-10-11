# Brief: hand-built ground-truth guideline trees

You are building **ground truth**: what a careful nurse-reviewer would say a payer guideline requires, as a JSON tree a
program can evaluate. Another system turns these PDFs into trees automatically; your fixtures are the answer key it will
be scored against. Your work must be independent of it.

## Independence (hard rules)
Do NOT open, list or grep any of these: `data/guidelines/generated/`, `data/runs/`, `GUIDELINE_FINDINGS.md`,
`GUIDELINE_VALIDATION.md`, `prompts/slice_guideline.md`, `prompts/reduce_guideline.md`, anything under `/private/tmp`.
Do not run `app.cli ingest` or any model call. Work from the PDF only.

## Be persistent
This is slow, careful work and it is the whole job. Read every word of the coverage section, not a skim. Re-read each
"AND"/"OR"/"one of"/"all of"/"at least two"/"none of"/"except" and nesting level twice. Do not stop at a first draft:
after building, re-walk the PDF top to bottom and check every requirement sentence is in your tree or deliberately
left out (and say why in the notes). Keep going until the validation script passes with zero problems. If a document
is long, work section by section; do not summarise or sample.

## Read the PDF
`pdftotext -layout <pdf> -` (poppler is installed), or
`.venv/bin/python -c "from pathlib import Path; from app.pdf import pdf_to_text; print(pdf_to_text(Path('<pdf>')))"`.
Run from the repo root.

## Format: the app's `Guideline` schema (`app/models.py`)
Model your file on the hand-built example `data/guidelines/bcbsfl-02-33000-31.json` (read it first; read
`app/models.py` for the schema). Write `tests/fixtures/truth/<slug>.json` where slug is given in your task.

- `payer`, `payer_aliases`, `title`, `guideline_number`, `effective_date` as printed. `payer` is the issuing
  organization (not "Medical Policy").
- `plan_types` (lines of business it applies to) and `excluded_plans` (plans that follow another document), as written.
- `criteria`: one per distinct requirement a chart could document. `text` is copied **verbatim** from the PDF (exact
  words of that requirement only; a sentence holding two requirements becomes two criteria, each with its own exact
  substring). `question`: how a nurse would ask it of a chart. `threshold` when there is a number:
  `{"kind": "number"|"duration_months"|"enum", "op": "gte"|"lte"|"gt"|"lt"|"eq", "value": ..., "unit": ...}`;
  durations of a treatment trial or of symptoms go in months (`duration_months`); ages, BMI, scores, sizes are
  `number`. `answerable: false` for what no chart can show (provider credentials, facility accreditation, criteria held
  in InterQual/MCG/another document, benefit/contract terms). `refs` may be empty.
- `scenarios`: one per coverage pathway (each indication / procedure / population / initial-vs-repeat the document
  grants coverage for). `applies_to_cpt`: codes from the document's code table that pathway governs (empty list = all
  codes). `requires`: the tree, nested exactly as the document nests it:
  `{"type":"all","children":[...]}`, `{"type":"any",...}`, `{"type":"not","child":...}`, leaf
  `{"type":"leaf","criterion":"<id>"}`. "At least 2 of A,B,C" = any of the pairs. "None of the following" =
  not(any(...)). A block of general requirements that applies to every pathway goes inside each pathway's `all`, never
  as its own pathway. A NOTE that waives a requirement is an `any` at that requirement.
- `scope.cpt`: every CPT/HCPCS code in the document's coding section, tagged `covered` / `non_covered` /
  `investigational` by what the document says about that code (a code is non-covered only if the text says so of
  that code or of exactly the procedure it describes). Codes the document leaves to another decision-maker: omit.
- `exclusions`: each statement that something is not covered / not medically necessary / investigational / cosmetic:
  `{"text": verbatim, "cpt": [codes that ARE that excluded thing]}`.
- `notes`: list of strings. Record every judgment call: ambiguous and/or, sentences you left out and why, anything
  a reasonable reviewer could read differently. These are as valuable as the tree.
- `status`: `"ok"`, or `"needs_review"` with `review.no_criteria_reason` if the document has no criteria of its own
  (defers everything to InterQual/MCG/an NCD). If it defers only some pathways, build the rest and mark the deferred
  pathways' single criterion `answerable: false`.

## Validate (must pass, zero problems)
```
.venv/bin/python tests/fixtures/truth/check_truth.py tests/fixtures/truth/<slug>.json <pdf>
```
It checks the schema, that every criterion `text` and exclusion `text` appears verbatim in the PDF text (whitespace
and hyphenation normalised), every leaf id exists, every criterion is used, and codes appear in the PDF.

## Report back
The file path, counts (criteria / pathways / codes / exclusions), and the 3–5 hardest judgment calls.

## Added after Pass 2
- **Several copies in one PDF.** Some downloads hold a redline (tracked changes merged into the text, e.g.
  "December 2023November 2024") followed by clean copies. Build from the final clean copy and say so in `notes`.
- **One guideline at a time.** If you have several, finish and validate each file before starting the next, so your
  work survives if you are stopped. Builder scripts you write go in your own scratch folder, not the repo.
- **No coverage criteria of its own** (a code list, a deferral to InterQual/MCG/an LCD): still write the file, with
  `status: "needs_review"`, `review.no_criteria_reason`, the codes, and any pathways it does state.
- **Code-to-pathway mapping matters**: these keys will also be used to test checking only the pathways that govern an
  order's CPT code. Set every pathway's `applies_to_cpt` deliberately and say in `notes` how you mapped codes the
  document does not tie to a section.
