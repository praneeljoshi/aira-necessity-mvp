You read a payer medical-necessity guideline for one prior-authorization request. Return the payer, the guideline's code table, the covered indications it describes (the routes to approval), and which of them this request falls under. You do not extract requirements: a later step reads the whole guideline for the indication a person confirms.

The document is given as its lines, each numbered: `[g0031]     text`. The spaces after the id are the line's own indent. Blank lines and `--- page 3 ---` markers are not lines and cannot be cited. Cite a line, or a range `"g0031-g0033"` when something wraps; `first` and `last` are single ids. Return one JSON object.

## The request

{{procedure_json}}

`cpt` are the codes written in the chart; `as_written` is the procedure as the chart words it; `target` is what it treats; `diagnosis` is the clinic's stated indication, with ICD-10 codes when given. Any of them may be empty.

## Return JSON

```
{"payer": {"name": "Florida Blue", "aliases": ["Blue Cross and Blue Shield of Florida", "BCBSFL"], "refs": ["g0002"]},
 "no_pathways_reason": null,
 "codes": [{"code": "36475", "tag": "covered", "refs": ["g0091-g0092"]},
           {"code": "36468", "tag": "non_covered", "refs": ["g0086"]}],
 "pathways": [{"id": "great_small_saphenous", "spans": [{"first": "g0023", "last": "g0036"}],
               "codes": ["36475", "36478", "37722"], "targets": ["great saphenous vein", "small saphenous vein"]},
              {"id": "perforator", "spans": [{"first": "g0071", "last": "g0083"}],
               "codes": ["37760", "37761"], "targets": ["perforator veins", "leg ulcer"]}],
 "chosen": {"pathway_ids": ["great_small_saphenous"], "mapped_cpt": null, "why_refs": ["g0023"]}}
```

## Payer
`name`: the payer as its members know it ("Florida Blue", "UnitedHealthcare", "CMS"), not a committee or document type. `aliases`: its other names in the document. `refs`: where it is named.

## Codes
Every CPT and HCPCS code in the coding section, each once; a range written as a range is listed code by code. `refs`: the row where the code is printed. `tag` by the document's words about that code or the procedure its description names: "non-covered", "not medically necessary", "cosmetic" → `non_covered`; "investigational", "experimental", "unproven" → `investigational`; left to another decision-maker (a MAC, another policy, a state mandate) → `not_addressed`; otherwise `covered`. A statement about a narrower use does not tag a code whose description also covers a covered use.

## Covered indications
A covered indication is one route to approval: a situation the payer covers, with its own conditions (a vein, joint, diagnosis, population, device, initial vs repeat, a special case such as concurrent treatment). Alternatives inside one list of conditions are one indication. `spans`: where the indication is stated, its heading through its conditions, as one or more ranges. `codes`: the table codes it governs (printed with it, or whose description names its procedure). `targets`: up to four short phrases in the document's words saying what it is about. If the document covers nothing of its own (all investigational or not covered, or the criteria live in InterQual, MCG, an NCD or another policy), return `"pathways": []` and cite that sentence in `no_pathways_reason`.

## Chosen
The indications this request falls under: they govern one of the request's codes and agree with its procedure, target and diagnosis (the coding section often lists ICD-10 codes per indication). Choose a concurrent, repeat or bilateral indication only when the request says so; veins on the two legs are separate procedures. One indication per procedure. When the request does not say enough to decide between indications (no target, or a target several indications share equally), leave those out: a person will be asked. An indication that alone governs the request's code and does not contradict its target or diagnosis is chosen; the request need not repeat its conditions (symptoms, severity, tests), which a later step checks. `mapped_cpt`: only when the request has no code in the table, the table code matching `as_written`. `why_refs`: the lines that match the request.

## Document

{{guideline_spans}}
