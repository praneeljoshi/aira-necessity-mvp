A prior-authorization team will check a patient chart against this payer guideline before submitting a request. A person has confirmed which covered indication the request falls under. Read the whole guideline and identify every condition that limits approval of this procedure under this indication, then write the logic that is true exactly when the payer would approve.

Think of everything a payer's reviewer would hold the chart to: the indication's own criteria; what the guideline says applies to every indication; the condition, population, anatomy, side, device or technique the coverage is for; limitations and exclusions wherever they are printed (contraindications, "not medically necessary when …", "does not meet the definition …", reimbursement rules that deny a combination); definitions and cross-references the criteria lean on ("as outlined above", "nonhealing"); waivers and conditionals. Missing a condition is the worst error: nobody gathers that evidence, and a chart that should not pass will. An extra condition costs one question that staff can strike. When unsure, include it.

Not conditions: paperwork about which form to send, billing instructions that do not change coverage, background, rationale and references. A condition that is about the clinical facts a chart must document is a condition.

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
- A condition stated as something that must not be true (an exclusion, a contraindication) is a criterion for the situation, used under NOT. A condition stated negatively ("is not secondary to DVT") may also be written as is.
- "e.g.", "such as", "including but not limited to" give examples, never a closed list or a cutoff; a named item in an exclusion list is still excluded.
- `threshold` when the condition sets its own number (a measurement, a duration, a recency window, a class or grade, an age, a score); keep the printed operator. Otherwise null.
- `answerable: false` for what no chart or order can show (provider credentials, facility accreditation, criteria held in another document). It stays in the logic.
- `admin: true` when the line is not a condition about the patient: billing, coding, reimbursement or payment ("separate payment will not be made…", "reimburse according to…", rental and purchase rules); process paperwork ("prior authorization is required", "a signed and dated statement…", lists of documents to send); headings, list lead-ins, effective dates, and definitions no condition depends on. When unsure, `false`. Never `admin`: a coded diagnosis the criteria require (it is clinical); an attestation or document that stands in for a missing test (it is a way to approval); a lead-in whose list or scope words are the condition (e.g. "in adults who meet all of the following:"). With `admin: true`, `admin_why` is one of "billing or coding", "paperwork", "heading or definition".
- `logic`: one per confirmed indication, over criterion ids, with AND, OR, NOT, parentheses and AT_LEAST k OF (a, b, c). NOT binds tightest, then AND, then OR: use parentheses whenever you mix them.

## The guideline

{{guideline_spans}}
