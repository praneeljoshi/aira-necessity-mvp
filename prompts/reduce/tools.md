A clinic is asking {{payer}} to approve a procedure. You have the order exactly as the clinic wrote it and the
payer's guideline. Build, with the tools, the logic of every condition that limits approval of this procedure for
this patient's diagnosis. A nurse will check each condition against the chart; if the chart meets your logic the
request goes out as ready. Missing a condition approves a patient the payer would deny: never acceptable. An extra
condition only costs a coordinator a review. When unsure whether a sentence limits approval, include it.

1. Find the indication(s) this order falls under, from its procedure, code(s), diagnosis, age and sex. If more than
   one could apply and nothing in the order tells them apart, keep each (combine with OR at the end). Rule a route
   out only on what the order fixes: the product or device code, the procedure, the side, the age band. Do not rule
   out a clinical alternative just because the diagnosis code names a different one.
2. Add every condition that limits approval under it, wherever it is printed: what the indication's own sentence
   names (population, device, diagnosis, technique: "in adults", "FDA-approved", "to treat ankyloglossia"); its
   listed requirements with their numbers, durations and time windows; anything that takes approval away
   ("experimental or investigational for", "does not meet the definition of medical necessity when",
   contraindications, "sole indication"; in "all other indications, including X and Y", X and Y are conditions);
   definitions it uses; notes, footnotes and "criteria above" it points to; reimbursement limits on this procedure.
   Use `find` for these words. Attach a condition from another section only when the text links it (a cross-
   reference, a defined term, a note that names this procedure). If a literal condition would make a route
   impossible, leave it out of that route and say so in `notes`.
3. Keep qualifiers with what they qualify ("if any", "sole", men/women, dominant/non-dominant, adult/child).
   "e.g.", "such as", "including, but not limited to" give examples: put them in the question, never make them a
   closed list or a cutoff. "Unless contraindicated" is (requirement OR contraindicated). When the grouping of
   and/or is ambiguous, take the stricter reading and record the other in `notes`.
4. Combine as the text does with `define_block` for shared parts and `set_logic` per indication.
5. Before `submit`: describe to yourself a patient who meets your logic but whom the text would deny. If you can,
   add what is missing. Then `submit`; fix any problems it returns.

You may make several tool calls in one turn (for example, every `add_condition` of a list at once). The guideline in
the message has no line ids; `find`, `read`, `add_condition` and `show` give them.

## Example (an invented guideline, for the method only)

The guideline:

```
g0101 POSITION STATEMENT:
g0102 Endoscopic widget repair (EWR) meets the definition of medical necessity in adults when ALL of the
g0103 following are met:
g0104   • Symptomatic widget stenosis of 50% or greater on imaging; AND
g0105   • Failure of at least 6 weeks of conservative therapy that includes at least 2 of the following:
g0106       o Physical therapy
g0107       o Anti-inflammatory medication (unless contraindicated)
g0108       o Activity modification
g0109   • Use of an FDA-approved widget device.
g0110 Repeat EWR meets the definition of medical necessity when the criteria above are met and the prior repair
g0111 has failed.
g0112 EWR is considered experimental or investigational for all other indications, including widget dissection
g0113 and prophylactic repair.
g0140 REIMBURSEMENT INFORMATION:
g0141 EWR is limited to one procedure per side per 12 months.
```

The order: `{"procedure": "Endoscopic widget repair, left", "cpt_line": "99999 — Endoscopic widget repair, unilateral", "diagnosis": "Widget stenosis, left (Z99.1)", "age": 58, "sex": "F"}`

```
find("medical necessity")            -> hits g0102-g0103 (EWR in adults), g0110-g0111 (repeat EWR)
read("g0101", "g0141")               -> the section
# First repair (no prior EWR in the order) -> the g0102 indication; repeat EWR is ruled out only if the chart
# shows no prior repair, but the order says nothing about a prior repair, so keep both routes.
add_condition("adult", "in adults", "Is the patient an adult?")                                     -> ok g0102
add_condition("stenosis_50", "Symptomatic widget stenosis of 50% or greater on imaging",
              "Does imaging show symptomatic widget stenosis of 50% or more?",
              threshold={"op": ">=", "value": 50, "unit": "%"})                                        -> ok g0104
add_condition("conservative_6wk", "Failure of at least 6 weeks of conservative therapy",
              "Did at least 6 weeks of conservative therapy fail (dated notes)?",
              threshold={"op": ">=", "value": 1.5, "unit": "months"})                                  -> ok g0105
add_condition("pt", "Physical therapy", "Was physical therapy tried?")                                 -> ok g0106
add_condition("nsaid", "Anti-inflammatory medication", "Was anti-inflammatory medication tried?")      -> ok g0107
add_condition("nsaid_contraindicated", "unless contraindicated",
              "Is anti-inflammatory medication documented as contraindicated?")                        -> ok g0107
add_condition("activity_mod", "Activity modification", "Was activity modification tried?")            -> ok g0108
add_condition("fda_device", "Use of an FDA-approved widget device",
              "Is the planned device FDA-approved?")                                                   -> ok g0109
add_condition("prior_repair_failed", "the prior repair has failed", "Has a prior EWR on this side failed?")
                                                                                                       -> ok g0110-g0111
add_condition("dissection", "widget dissection", "Is there a widget dissection?")                     -> ok g0112
add_condition("prophylactic", "prophylactic repair", "Is the repair prophylactic (no current stenosis)?") -> ok g0113
add_condition("once_per_12mo", "one procedure per side every 12 months",
              "Has this side had EWR in the past 12 months?")
   -> {"ok": false, "problems": ["quote not found"],
       "nearest": [{"lines": "g0141", "text": "EWR is limited to one procedure per side per 12 months."}]}
# paraphrased by mistake ("every"): copy the printed words from `nearest` and retry
add_condition("once_per_12mo", "limited to one procedure per side per 12 months",
              "Has this side had EWR in the past 12 months?")                                         -> ok g0141
define_block("ewr_criteria",
  "adult AND stenosis_50 AND conservative_6wk AND AT_LEAST 2 OF (pt, (nsaid OR nsaid_contraindicated), activity_mod) AND fda_device")
                                                                                                       -> ok
define_block("ewr_exclusions", "dissection OR prophylactic")                                           -> ok
# re-reading g0105: the 6-week threshold was entered in months; fix it in place
update_condition("conservative_6wk", threshold={"op": ">=", "value": 6, "unit": "weeks"})             -> ok g0105
set_logic("ewr_first", "ewr_criteria AND NOT ewr_exclusions AND NOT once_per_12mo")                   -> ok
set_logic("ewr_repeat", "ewr_criteria AND prior_repair_failed AND NOT ewr_exclusions AND NOT once_per_12mo") -> ok
# Self-check: a patient with 50% stenosis, 6 weeks of PT only, FDA device -> fails AT_LEAST 2: correct. A child -> fails
# adult: correct. A dissection -> NOT ewr_exclusions fails: correct. Nothing found missing.
submit(indication_quotes=["Endoscopic widget repair (EWR) meets the definition of medical necessity in adults",
                          "Repeat EWR meets the definition of medical necessity when the criteria above are met"],
       notes="Both routes kept: the order does not say whether a prior repair exists. 'once_per_12mo' is the
              reimbursement limit, used as NOT (has had EWR on this side in 12 months).")
   -> {"ok": true}
```

What the example shows:
- the indication's own sentence gives `adult` and `fda_device`
- "criteria above" became a block reused by the repeat route
- the exclusion list became conditions used under NOT
- "unless contraindicated" is an OR inside the at-least group
- the reimbursement limit was found and used
- a failed quote was fixed by copying from `nearest`
- a condition was corrected in place with `update_condition`
- routes the order cannot tell apart are both kept
