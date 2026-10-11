A prior-authorization team will check a patient chart against this payer guideline before submitting a request. A person has confirmed which covered indication the request falls under. Read the whole guideline and identify every condition that limits approval of this procedure under this indication, then write the logic that is true exactly when the payer would approve.

Think of everything a payer's reviewer would hold the chart to: the indication's own criteria; what the guideline says applies to every indication; the condition, population, anatomy, side, device or technique the coverage is for; limitations and exclusions wherever they are printed (contraindications, "not medically necessary when …", "does not meet the definition …", reimbursement rules that deny a combination); definitions and cross-references the criteria lean on ("as outlined above", "nonhealing"); waivers and conditionals. Missing a condition is the worst error: nobody gathers that evidence, and a chart that should not pass will. An extra condition costs one question that staff can strike. When unsure, include it.

Not conditions: paperwork about which form to send, billing instructions that do not change coverage, background, rationale and references. A condition that is about the clinical facts a chart must document is a condition.

## Sweep to notes (never a condition)

These go in notes, never in the criteria:
- Payment, reimbursement, rental or purchase and "stop billing" lines, and what the supplier must do or keep on file.
- Evidence summaries, rationale and background text; effective dates ("Effective for dates of service on or after …").
- "As determined by <the payer>" cost-effectiveness judgments, and benefit terms ("subject to the member's benefit plan").
- Documents that exist only after the procedure (operative report, pathology report).
- Process lines: "prior authorization is required", "submit records", which form to send.

## Write and mark admin

Write these as criteria with `admin: true` (code folds them under "Not asked of the chart", where a person can restore one); never sweep them to notes:
- Definitions, and "may be required" documentation lists (and other lists of documents to keep or send).
- The procedure's own description: words that only restate the ordered code's descriptor ("percutaneous, radiofrequency; first vein treated"). A device, technique or protection the requirement names ("with stenting", "with embolic protection", "FDA-approved", "permanent") is a condition, not admin, even when the order also says it.
- Headings and list lead-ins ("one or more of the following:"; "If this Medical Coverage Guideline contains a step therapy requirement …" is a lead-in).

## Keep these (always conditions; never swept, never admin)

- Frequency, quantity and time limits on the service; any reimbursement rule that denies a combination.
- A definition that carries a "must" or a threshold the criteria rely on ("an AHI from under 2 hours of sleep needs at least 10 events").
- A payer determination the grant depends on ("as determined by the Plan" as a condition of approval): kept, `answerable: false`.
- A coded diagnosis the criteria require: it is clinical.
- A signed and dated statement or attestation that stands in for evidence: kept as a way to approval, an OR route.
- Provider and setting requirements: who performs or interprets the service, the facility.
- External references ("meets InterQual", "NCD 20.4"): kept, `answerable: false`.
- An open route the policy grants ("such as …", "other … disorder"): keep the route.
- A lead-in stem whose children carry the requirement ("B. Presence of a comorbid condition:" heading a list): the stem's scope words stay; it is not admin.
- A requirement tied to the treated side or site ("lymphoscintigraphy of the limb proposed for surgery").
- Scope words, even inside the procedure's description or a lead-in: "FDA-approved", "adults" or an age, "permanent", side and site, a device type the order does not state.
- The step-therapy exemption: an alternative the policy grants stays an OR route (its lead-in sentence is admin; the exemption route is kept).
- The member's plan rule below applies as written.
- Anything clinical. When a line mixes billing with a clinical fact, the clinical fact is a condition.

{{plan_rule}}
## The request

{{request}}

## The confirmed indication(s)

{{pathways}}

## Codes on it

{{codes_json}}

## Return JSON

```
{"notes": "your reading, in your own words: what this indication covers, what else in the guideline bears on it, and any judgment calls",
 "criteria": [
   {"id": "saphenous_reflux", "quote": "There is demonstrated saphenous reflux", "refs": ["g0025"],
    "threshold": null, "answerable": true, "question": "Does a duplex ultrasound show reflux in the vein to be treated?", "admin": false},
   {"id": "compression_3_months", "quote": "compression therapy for at least 3 months has not improved the symptoms", "refs": ["g0032-g0034"],
    "threshold": {"op": ">=", "value": 3, "unit": "months"}, "answerable": true,
    "question": "Has compression been tried for at least 3 months without improvement, with dates?", "admin": false},
   {"id": "dvt", "quote": "secondary to deep venous thrombosis", "refs": ["g0050"], "threshold": null, "answerable": true,
    "question": "Is the vein disease caused by a deep venous thrombosis?", "admin": false}],
 "logic": [{"pathway": "great_small_saphenous", "logic": "saphenous_reflux AND (venous_ulcer OR compression_3_months) AND NOT dvt"}]}
```

- One criterion per condition. `quote`: the condition's words copied exactly from the guideline (any lines; line breaks do not matter); code finds the quote, so copy it, do not paraphrase. Keep qualifiers with what they qualify ("if any", "sole", "in adults"). `refs`: the line or range it is on.
- Write each requirement once: if two lines of the policy say the same thing, make one condition and cite both.
- A condition stated as something that must not be true (an exclusion, a contraindication) is a criterion for the situation, used under NOT. A condition stated negatively ("is not secondary to DVT") may also be written as is.
- "e.g.", "such as", "including but not limited to" give examples, never a closed list or a cutoff; a named item in an exclusion list is still excluded.
- `threshold` when the condition sets its own number (a measurement, a duration, a recency window, a class or grade, an age, a score); keep the printed operator. Otherwise null.
- `threshold.op` is one of ">=", ">", "<=", "<", "==" and nothing else (never "in"); a range is two conditions, one with ">=" (or ">") and one with "<=" (or "<").
- `answerable: false` for what no chart or order can show (provider credentials, facility accreditation, criteria held in another document). It stays in the logic.
- `admin: true` for the lines under "Write and mark admin" (and a coding instruction that denies nothing), with `admin_why` one of "billing or coding", "paperwork", "heading or definition", "procedure wording". When unsure, `false`. Never `admin`: anything under "Keep these".
- `logic`: one per confirmed indication, over criterion ids, with AND, OR, NOT, parentheses and AT_LEAST k OF (a, b, c). NOT binds tightest, then AND, then OR: use parentheses whenever you mix them.

## The guideline

{{guideline_spans}}
