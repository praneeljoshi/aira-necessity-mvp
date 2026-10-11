Below is a payer guideline and a checklist someone wrote from it for one covered indication: criteria and the logic that is true when the payer would approve. Your job is to find what it lets through.

Describe patients (or planned procedures) who satisfy the logic as written but whom the guideline's text would deny: a condition left out, an exclusion or limitation printed elsewhere in the document, a qualifier dropped ("sole", "in adults", "FDA-approved", "for the treatment of …"), an OR that should be an AND, a waiver applied too broadly, an example list read as closed. Then close each gap.

You may only tighten. Add criteria for what is missing and give revised logic that keeps every existing criterion. Do not remove or loosen anything. If you find nothing, return empty lists.

## Not loopholes (do not add these)

They belong in notes, not the checklist; a patient who passes without them is not a loophole:
- Payment, reimbursement, rental or purchase and "stop billing" lines, and what the supplier must do or keep on file.
- Evidence summaries, rationale and background text; effective dates ("Effective for dates of service on or after …").
- "As determined by <the payer>" cost-effectiveness judgments, and benefit terms ("subject to the member's benefit plan").
- Documents that exist only after the procedure (operative report, pathology report).
- Process lines: "prior authorization is required", "submit records", which form to send.

## Admin lines

A patient who passes without these is not a loophole either. If you add one, it carries `admin: true`:
- Definitions, and "may be required" documentation lists (and other lists of documents to keep or send).
- The procedure's own description: words that only restate the ordered code's descriptor ("percutaneous, radiofrequency; first vein treated"). A device, technique or protection the requirement names ("with stenting", "with embolic protection", "FDA-approved", "permanent") is a condition, not admin, even when the order also says it.
- Headings and list lead-ins ("one or more of the following:"; "If this Medical Coverage Guideline contains a step therapy requirement …" is a lead-in).

## Still gaps to close

These are conditions; a checklist that leaves one out has a loophole (a missing scope word, limit or side/site requirement is a loophole):
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

## The request

{{request}}

## The confirmed indication(s)

{{pathways}}

## The checklist

{{tree}}

## Return JSON

```
{"loopholes": ["A patient whose ulcer is arterial, not venous, passes: the guideline requires 'secondary to venous stasis'."],
 "criteria": [{"id": "venous_ulcer_cause", "quote": "secondary to venous stasis", "refs": ["g0028"], "threshold": null,
               "answerable": true, "question": "Is the ulcer caused by venous stasis?", "admin": false}],
 "logic": [{"pathway": "great_small_saphenous", "logic": "saphenous_reflux AND ((venous_ulcer AND venous_ulcer_cause) OR compression_3_months) AND NOT dvt"}]}
```

Quotes are copied exactly from the guideline. Each added criterion carries `admin`: true only for the lines under "Admin lines", with `admin_why` one of "billing or coding", "paperwork", "heading or definition", "procedure wording"; when unsure, false; never for anything under "Still gaps to close". Do not add swept lines or admin lines as loopholes: a loophole is a patient the text would deny. `threshold.op` is one of ">=", ">", "<=", "<", "=="; a range is two criteria. `logic` uses criterion ids with AND, OR, NOT, parentheses and AT_LEAST k OF (…); give it only for an indication you changed.

## The guideline

{{guideline_spans}}
