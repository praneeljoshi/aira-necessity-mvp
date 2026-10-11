# Guideline analysis worker: shared instructions

Working directory (run every command from here):
the repo root.

Context: the owner is new to payer medical-necessity guidelines. They are building a prior-authorization checker
that turns one guideline into a criteria tree (`all` / `any` / `not` over leaf requirements, each leaf judged
MET / NOT_MET / INSUFFICIENT against a patient chart with quoted evidence). Florida Blue (BCBSFL) is the client
payer; other payers are here to show variance. Your job is to teach them how real guidelines are built, how they
differ, and what would break or strain that approach. Be concrete: quote the documents (short quotes with page or
section pointers). Never invent content; if the text is unclear, say so.

Inputs
- Extracted text: `sourcing/text/<treatment>/<pdf stem>.txt` (pdftotext -layout). Original PDFs:
  `sourcing/library/<treatment>/<file>.pdf`; provenance in the `.json` beside each PDF.
- Regex counts per document: `sourcing/analysis/survey.json` (crude signals only).
- Profile schema: `sourcing/analysis/PROFILE.md`. Read it first.

Reading strategy (documents can be 40-100 pages): `grep -n` the text file for headings first, then read the
criteria / policy / position-statement sections fully and the coding, definitions and program-exception sections
quickly. Skim or skip long evidence reviews and reference lists; note their size only. Read with offset/limit.

Outputs (write only these; never edit code, never touch data/, never use port 8000, no browser):
1. One profile per assigned document: `sourcing/analysis/profiles/<pdf stem>.json`, validated with
   `python3 -m sourcing.profile_check <path>` (fix until ok).
2. The markdown report named in your assignment.

Finish with a final message of at most 15 lines: files written, and the three most important things you learned.
