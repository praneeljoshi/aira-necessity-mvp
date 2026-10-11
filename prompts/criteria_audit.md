Below is a payer guideline and a checklist someone wrote from it for one covered indication: criteria and the logic that is true when the payer would approve. Your job is to find what it lets through.

Describe patients (or planned procedures) who satisfy the logic as written but whom the guideline's text would deny: a condition left out, an exclusion or limitation printed elsewhere in the document, a qualifier dropped ("sole", "in adults", "FDA-approved", "for the treatment of …"), an OR that should be an AND, a waiver applied too broadly, an example list read as closed. Then close each gap.

You may only tighten. Add criteria for what is missing and give revised logic that keeps every existing criterion. Do not remove or loosen anything. If you find nothing, return empty lists.

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

Quotes are copied exactly from the guideline. Each added criterion carries `admin`: true only when the line is not a condition about the patient (billing, coding, reimbursement or payment; process paperwork; headings, list lead-ins, effective dates, definitions no condition depends on), with `admin_why` one of "billing or coding", "paperwork", "heading or definition"; when unsure, false; never for a required coded diagnosis, a document that stands in for a missing test, or a lead-in whose words are the condition. Do not add admin lines as loopholes: a loophole is a patient the text would deny. `logic` uses criterion ids with AND, OR, NOT, parentheses and AT_LEAST k OF (…); give it only for an indication you changed.

## The guideline

{{guideline_spans}}
