Split this patient chart into its sections and label each one. A later step judges the chart against a payer's criteria, and it may only read the record itself: what was observed, measured, tested, prescribed and documented at a visit or in a report. It must not read the clinic's own summaries of the case, and it must not read the planned procedure or the authorization request, because those state what the clinic wants approved rather than show it.

The chart is given as its lines, each numbered: `[r0041] text`. Blank lines and `--- page 3 ---` markers are not lines and cannot be cited. Return one JSON object.

## Labels

- `evidence`: the record. Demographics (age, sex), current medications and medication history, allergies, visit notes (chief complaint, history, review of systems, vitals, examination, labs, the clinician's assessment and plan at that visit, orders, medication reconciliation, the signature line), diagnostic and imaging reports (the measurements, the interpretation or impression, the signature line), lab results, therapy notes, letters from other clinicians.
- `summary`: the clinic's restatement of the case, written for the request: a "Clinical Indication Summary", "Medical Necessity Summary", "Letter of Medical Necessity", "Summary of Findings" or case recap; a problem list; a patient-instructions or after-visit summary; an encounter-coding block; a cover sheet.
- `order`: the procedure being requested: a "Planned Procedure" block, the scheduled surgery, the prior-authorization request or status, the CPT and units, the scheduled surgeon and facility.
- `admin`: identity and administration with nothing clinical: the clinic letterhead, "Patient Medical Chart" banners, confidentiality notices, insurance and coverage, page footers.

When a section mixes kinds, split it at the line where the kind changes. When unsure whether something is the clinic's summary or the record, call it `summary`.

Every line belongs to exactly one section; cover the whole chart, first line to last, including page headers and footers (label them `admin`).

## A worked example: this clinic's chart format

Robert Mitchell's chart from Metropolitan Cardiology Associates is laid out like this. Charts from this clinic follow the same format; other charts will differ, and you label by what a section is, not by its exact heading.

| Heading in the chart | Label |
|---|---|
| METROPOLITAN CARDIOLOGY ASSOCIATES (letterhead, address, NPI) | admin |
| PATIENT MEDICAL CHART / CONFIDENTIAL — FOR AUTHORIZED USE ONLY | admin |
| 1. PATIENT DEMOGRAPHICS | evidence |
| 2. INSURANCE & COVERAGE (Primary Insurance, Secondary Insurance) | admin |
| 3. ACTIVE PROBLEM LIST | summary |
| 4. CURRENT MEDICATIONS (including the "Note:" under the table) | evidence |
| 5. ALLERGIES & ADVERSE REACTIONS | evidence |
| 6. VISIT NOTES — CARDIOLOGY: each "Visit Date: … \| Attending: … \| Type: …" through its "Electronically signed: …" line (Chief Complaint, History of Present Illness, Interval History, Physical Examination, Laboratory Results, Holter Monitor Summary, Assessment & Plan) | evidence |
| 7. DIAGNOSTIC IMAGING & TESTING REPORTS: each report ("Electrocardiogram (EKG) — October 8, 2025", "Transthoracic Echocardiogram (TTE) — November 5, 2025", "30-Day Holter Monitor Report — November 1-29, 2025") through its "Electronically signed" line | evidence |
| 8. PLANNED PROCEDURE (Planned Procedure, CPT, Unit, Surgeon, Facility, Payer, PA Status, Auth #) | order |
| Clinical Indication Summary (the bullets under it: Diagnosis, Metabolic workup, EKG, Echo, Holter, Metoprolol) | summary |
| "This document is for clinical and administrative use only…" | admin |

The same clinic's longer charts also have "MEDICATION HISTORY" (evidence), "LABORATORY RESULTS" (evidence) and "ENCOUNTER NOTES — ALL SOURCES, CHRONOLOGICAL" (evidence). Inside each encounter, "Patient Instructions / After Visit Summary:" and "Encounter Coding:" are `summary`, and the encounter's other parts are evidence.

## Return JSON

```
{"sections": [
  {"title": "1. PATIENT DEMOGRAPHICS", "label": "evidence", "spans": [{"first": "r0008", "last": "r0018"}]},
  {"title": "Visit Date: October 8, 2025 — New Patient Consult", "label": "evidence", "spans": [{"first": "r0056", "last": "r0083"}]},
  {"title": "Clinical Indication Summary", "label": "summary", "spans": [{"first": "r0160", "last": "r0168"}]}]}
```

`title`: the section's heading as printed (for a visit or report, its first line). `spans`: one or more ranges of single line ids, in order. List sections in chart order.

## Chart

{{chart_spans}}
