# Guideline profile: what a worker records per document

Audience: the owner is new to payer guidelines and is building a system that turns a guideline into a criteria
tree (`all` / `any` / `not` over leaf requirements) and judges a patient chart against it. Profiles exist to teach
how guidelines vary and to surface everything that would break or strain that approach. Quote the document;
never invent. Short quotes (under ~40 words) with a page or section pointer.

Write one JSON file per document to `sourcing/analysis/profiles/<pdf stem>.json`, then run
`python3 -m sourcing.profile_check sourcing/analysis/profiles/<pdf stem>.json` and fix anything it reports.

```json
{
  "file": "cigna-0051-bariatric-surgery.pdf",
  "treatment": "bariatric-surgery",
  "payer": "cigna",
  "doc_kind": "medical policy | coverage policy | clinical guideline (vendor) | Medicare Advantage policy | Medicaid policy | other",
  "lines_of_business": ["what plans/products it says it applies to, as written"],
  "effective_or_revised": "as printed",
  "sections_in_order": ["headings as printed, in order"],
  "criteria_location": "which section(s) and pages hold the coverage criteria; note if criteria are split across sections",
  "procedures_covered": ["each distinct procedure/service the doc rules on; note when one doc covers many"],
  "logic": {
    "top_level": "all | any | k-of-n | pathways (several indications each with own criteria) | other",
    "max_nesting_depth": 3,
    "k_of_n": [{"k": 2, "n": 5, "quote": "..."}],
    "exclusions_or_contraindications": "how exclusions are expressed (a NOT list, separate section, inline 'unless')",
    "initial_vs_repeat": "separate criteria for repeat/continuation/revision/second side? quote",
    "and_or_ambiguity": [{"quote": "...", "why_ambiguous": "..."}]
  },
  "requirement_kinds": [{"kind": "conservative therapy | duration | imaging finding | measurement threshold | symptom | functional impairment | diagnosis | age | BMI/comorbidity | prior procedure | provider/facility qualification | site of service | documentation/photos | psych/nutrition evaluation | patient commitment | lab value | other",
                         "quote": "...", "where": "p.3 / Position Statement 1.b"}],
  "thresholds": [{"quantity": "vein diameter", "value": ">= 3", "unit": "mm", "quote": "..."}],
  "time_windows": [{"what": "compression therapy trial", "length": "3 months", "quote": "..."}],
  "codes": {"cpt_hcpcs_listed": true, "icd10_listed": false,
            "codes_tied_to_criteria": "are codes mapped to specific criteria, or just listed?",
            "non_covered_code_lists": "codes declared investigational / not covered, if any"},
  "external_dependencies": [{"what": "criteria delegated to MCG/InterQual/CMS LCD/another policy/state mandate", "quote": "..."}],
  "definitions_that_change_meaning": [{"term": "...", "definition_quote": "..."}],
  "vague_terms": [{"quote": "...", "problem": "undefined 'significant', 'failed', 'appropriate', etc."}],
  "extraction_hazards": ["what in the PDF text (see sourcing/text/...) would trip a parser: tables flattened, multi-column, repeated headers/footers, redline/strikethrough, footnotes carrying criteria, images, page breaks inside lists"],
  "interesting_structures": ["anything unusual and instructive: scoring systems, decision tables, flowcharts, criteria by age band, staged approvals, quantity limits, site-of-service rules"],
  "fit_to_tree": {"score": 1, "scale": "1 = all/any/not expresses it cleanly ... 5 = needs new constructs or human judgment", "why": "..."}
}
```

Use `[]` / `""` when a field does not apply. Read the extracted text in `sourcing/text/<treatment>/<stem>.txt`
(made by `pdftotext -layout`); open the PDF itself only if the text looks broken. Crude regex counts for every
document are in `sourcing/analysis/survey.json`.
