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
4. Write the tree as a script in the language below. `check` it as often as you like; fix every error by editing the script; when it passes, do the self-check (a patient who meets your logic but whom the text would deny) and `submit`.

You may make several tool calls in one turn. The guideline in the message has no line ids; `find` and `read` give
them, and errors name the nearest printed lines.

## The language

A tree script is plain Python syntax restricted to declarations. Each line is an assignment or one of the calls below.
No imports, loops, functions, attributes, comprehensions or other calls: the host reads it, it does not run it.

```python
# one condition (a leaf): id, the guideline's exact words, the nurse's question
adult = C("adult", "in adults", "Is the patient an adult?")
stenosis = C("stenosis_50", "Symptomatic widget stenosis of 50% or greater on imaging",
             "Does imaging show symptomatic widget stenosis of 50% or more?", threshold=(">=", 50, "%"))
contract = C("benefit_terms", "subject to the member's benefit terms", "Do the member's benefits allow it?",
             answerable=False)

# logic: & is AND, | is OR, ~ is NOT, parentheses group, at_least(k, a, b, c) is "at least k of"
# a variable holding logic is a reusable block
conservative = stenosis & at_least(2, pt, nsaid | nsaid_contraindicated, activity_mod)

# one per indication you use: its id, the guideline sentence that grants it (exact words), its logic
indication("ewr_first", grant="Endoscopic widget repair (EWR) meets the definition of medical necessity in adults",
           logic=adult & conservative & ~exclusions)

# if the order is not covered at all: the guideline's words saying so (then no indication is needed)
not_covered("is considered experimental or investigational for all other indications")

# your reading in your own words: judgment calls, alternatives you considered
notes("Both routes kept: the order does not say whether a prior repair exists.")
```

Rules the host checks (and reports as `line N: ...`):
- every `C(...)` quote is printed in the guideline (line breaks and spaces do not matter); on a miss it returns the
  nearest printed lines so you can copy the exact words;
- condition ids are unique; every name used in logic is defined above its use; every condition is used in some
  indication's logic;
- `threshold` is `(op, value, unit)` with op one of `>=`, `>`, `<=`, `<`, `==`; `answerable` is True/False;
- every `indication(...)` has a `grant` quote that is printed in the guideline and a `logic`;
- at least one `indication(...)` or a `not_covered(...)`.

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

Round 1, `check`:
```python
adult = C("adult", "in adults", "Is the patient an adult?")
stenosis = C("stenosis_50", "Symptomatic widget stenosis of 50% or greater on imaging",
             "Does imaging show symptomatic widget stenosis of 50% or more?", threshold=(">=", 50, "%"))
conservative_6wk = C("conservative_6wk", "Failure of at least 6 weeks of conservative therapy",
                     "Did at least 6 weeks of conservative therapy fail (dated notes)?", threshold=(">=", 6, "weeks"))
pt = C("pt", "Physical therapy", "Was physical therapy tried?")
nsaid = C("nsaid", "Anti-inflammatory medication", "Was anti-inflammatory medication tried?")
nsaid_ci = C("nsaid_contraindicated", "unless contraindicated",
             "Is anti-inflammatory medication documented as contraindicated?")
activity_mod = C("activity_mod", "Activity modification", "Was activity modification tried?")
fda = C("fda_device", "Use of an FDA-approved widget device", "Is the planned device FDA-approved?")
once = C("once_per_12mo", "one procedure per side every 12 months", "Has this side had EWR in the past 12 months?")

ewr_criteria = adult & stenosis & conservative_6wk & at_least(2, pt, nsaid | nsaid_ci, activity_mod) & fda
indication("ewr_first", grant="Endoscopic widget repair (EWR) meets the definition of medical necessity in adults",
           logic=ewr_criteria & ~exclusions & ~once)
```
Result:
```
{"ok": false, "errors": [
 "line 12: quote not found: 'one procedure per side every 12 months' (nearest g0141: 'EWR is limited to one procedure per side per 12 months.')",
 "line 16: name 'exclusions' is not defined"]}
```
Round 2: copy the printed words; add the exclusions found with `find("investigational")`; keep the repeat route because
the order does not say whether a prior repair exists:
```python
# ... lines 1-11 unchanged (shortened here; the whole script is sent) ...
once = C("once_per_12mo", "limited to one procedure per side per 12 months",
         "Has this side had EWR in the past 12 months?")
dissection = C("dissection", "widget dissection", "Is there a widget dissection?")
prophylactic = C("prophylactic", "prophylactic repair", "Is the repair prophylactic (no current stenosis)?")
prior_failed = C("prior_repair_failed", "the prior repair has failed", "Has a prior EWR on this side failed?")

ewr_criteria = adult & stenosis & conservative_6wk & at_least(2, pt, nsaid | nsaid_ci, activity_mod) & fda
exclusions = dissection | prophylactic
indication("ewr_first", grant="Endoscopic widget repair (EWR) meets the definition of medical necessity in adults",
           logic=ewr_criteria & ~exclusions & ~once)
indication("ewr_repeat", grant="Repeat EWR meets the definition of medical necessity when the criteria above are met",
           logic=ewr_criteria & prior_failed & ~exclusions & ~once)
notes("Both routes kept: the order does not say whether a prior repair exists. 'once_per_12mo' is the reimbursement "
      "limit, used under NOT.")
```
Result: `{"ok": true, "summary": {...}}`. Self-check: a child fails `adult`; one conservative modality fails
`at_least(2, ...)`; a dissection fails `~exclusions`. Nothing missing -> `submit` the same script -> ok.

What the example shows:
- scope words in the grant sentence become conditions
- "criteria above" is a reused variable
- exclusions are conditions under `~`
- "unless contraindicated" is `|` inside `at_least`
- a limit in the reimbursement section is found and used
- a failed quote is fixed by copying `nearest`
- routes the order cannot tell apart are both declared
- the whole script is re-sent on every fix
