Read this patient chart and identify the procedure that needs prior authorization now. The chart is given as its lines, exactly as extracted from the PDF, each numbered: `[r0041] text`. Blank lines and `--- page 3 ---` markers are shown for readability only; they are not spans and cannot be cited. A span is one line; when a sentence or table row wraps over several lines, cite the range `"r0102-r0104"`. Return one JSON object:

```
{"patient_name": "...", "payer": "...",
 "procedure": {"cpt": ["36475"], "as_written": "Endovenous radiofrequency ablation, left great saphenous vein",
               "target": "left great saphenous vein", "surgeon": "Dr. Elena Vasquez, MD, FACS",
               "diagnosis": "Varicose veins of left lower extremity with inflammation (I83.12)",
               "plan": "PPO — BlueOptions"},
 "refs": ["r0212", "r0213-r0214"]}
```

Rules. This is the key every later step runs on, so copy, never infer.
- `payer`: the primary insurance carrier exactly as written ("Florida Blue BlueCare HMO", "UnitedHealthcare Medicare Advantage").
- `procedure.cpt`: only the codes written for the procedure being requested now (not past procedures, not diagnostics). If two procedures are planned for the same session, return both codes. If a procedure is named with no code, leave `cpt` empty. Never infer or look up a code. Write each code without its modifier ("36475-LT" and "36475-RT" are "36475"; the side goes in `target`).
- `procedure.as_written`: the requested procedure as the chart words it, from the plan or order.
- `procedure.target`: what the procedure treats, as the chart says it: the vein or body part with its side, the joint, or the indication ("left great saphenous vein", "right knee medial meniscus", "symptomatic bradycardia"). When the order treats more than one vein, side or site, name each ("right great saphenous vein and right anterior accessory saphenous vein"; "left great saphenous vein; right anterior accessory saphenous vein"). Null if the chart does not say.
- `procedure.surgeon`: the treating or ordering surgeon for this procedure, as written. Null if absent.
- `procedure.diagnosis`: the indication the chart gives for this procedure, with its ICD-10 codes, as written (a planned-procedure block's "Clinical Indication" or the plan's diagnosis line). Null if absent.
- `procedure.plan`: the member's plan as the chart's insurance or coverage section writes it (plan name, product or line of business: "PPO — BlueOptions", "Medicare Part B", "FEP Blue Standard"); copy it as written. Null if the chart does not say.
- `patient_name` as written.
- `refs`: the lines (or line ranges) the procedure, codes and target were read from.
- No planned procedure: empty `cpt`, null `as_written` and `target`.

## Chart

{{chart_spans}}
