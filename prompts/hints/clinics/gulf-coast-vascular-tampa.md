---
match:
  - 2200 Bayshore Blvd, Suite 310
  - "NPI: 1987654321"
where: first 10 lines
# The classic synthetic clinic: Gulf Coast Vascular Surgery Associates, Tampa (Delgado, Park + addendum, Okafor, Ruiz long chart;
# data/samples/synthetic, make_charts.py, make_long_chart.py, make_park_addendum.py). Synthetic ("Patient identifiers are fictional").
# Must NOT match: the demo EVAR charts printed as "GULF COAST VASCULAR SURGERY ASSOCIATES" at 2750 Bahia Vista St, Sarasota (NPI 1639204471),
# so the clinic name alone is not a match string.
---
Gulf Coast Vascular (Tampa) chart, numbered sections:
- Evidence: Demographics, Current Medications / Medication History (Start/Stop columns), Allergies, Visit or Encounter Notes ("Visit Date: …" to "Electronically signed: … — <date>"), Imaging & Testing Reports (heading "<Study> — <side> — <date>"), Laboratory Results, Addenda (a fact keeps the date it states).
- Not evidence: Insurance and "Copy to:" (admin), Active Problem List, the encounter index table, "Patient Instructions / After Visit Summary", "Encounter Coding", the closing "Clinical Indication Summary" (summary), Planned Procedure (order).
Instructions or recommendations are not evidence the patient did it; durations come from dated notes of continuous use, and a trial can stop and restart.
