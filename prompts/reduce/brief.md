# Reduce a payer guideline to the conditions for one order

A clinic is asking the payer to approve a procedure. In this directory:
- `guideline.txt`: the payer's guideline, as extracted from its PDF;
- `order.json`: the order as the clinic wrote it (procedure, CPT codes, diagnosis with ICD-10, age, sex when known);
- `codes.json`: the guideline's code-table rows for the order's codes;
- `helpers.py`: `C`, `block`, `th`, `write` (read it).

{{indication_rule}}

A nurse will check each condition against the patient's chart. If the chart meets your expression, the request is sent
as ready. So: **missing a condition approves a patient the payer would deny, which is the error that must never
happen. An extra condition only costs the nurse a question.** When unsure whether a sentence limits approval, include it.

## What counts
1. List every condition that limits approval of care under the indication, wherever in the text it is stated:
   - what the patient, condition, procedure, site, population or device must be or must have, including what the
     indication's own sentence names ("in adults", "using an FDA-approved device", "to treat ankyloglossia");
   - the requirements listed under it, with their thresholds, durations and time windows;
   - anything that takes approval away: "is considered experimental or investigational for …", "does not meet the
     definition of medical necessity when …", contraindications, "the sole indication is …"; in "all other
     indications, including X and Y", X and Y are each a condition;
   - conditions stated in other sections that apply to it (definitions of terms it uses, reimbursement limits on this
     procedure, notes and footnotes it points to, "the criteria above").
2. Keep qualifiers with what they qualify ("if any", "sole", "in men … in women", "dominant … non-dominant", adult /
   child). "e.g." / "such as" / "including, but not limited to" give examples: put them in the condition's question,
   never a closed list or a cutoff.
3. Combine them as the text does: `all`, `any`, `not`, `at_least`. A condition that takes approval away goes under
   `not`. "Unless contraindicated" is `any` of the requirement and its contraindication.
4. Each condition: `id` (short snake_case); `quote`, the guideline's exact words for it, copied from `guideline.txt`
   (line breaks do not matter); `question`, how a nurse asks it of a chart, saying what the chart must show;
   `threshold` only when the text itself sets a number (`th(">=", 3, "months")`; none for e.g. numbers); `answerable`
   false only if no chart could show it (a contract term, the provider's credentials, criteria held in another
   document).
5. Documents produced after the service (a pathology or operative report) cannot be in a chart before approval: put
   them in `notes`, not in the conditions.
{{policies}}
{{plan_rule}}
{{sweep}}
## How to work (do it this way)
1. Read `guideline.txt` and `order.json` once, whole.
2. Write `tree.py` that imports `helpers` and builds the conditions with `C(...)` (it checks every quote against the
   guideline as you write it), groups that recur with `block(...)`, and ends with `write(...)`.
3. Run it. Fix every failure (a quote not found, an unknown id, an unused condition, a bad expression) and run it
   again, until it prints OK.
4. Your final message: "DONE" and anything you could not do. The host reads `tree.json`; it will then ask you for the
   full-policy sweep and to check yourself (patients your expression lets through), in this same directory.

Read only the files in this directory. No network.
