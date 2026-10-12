# Evaluating step H (guideline reduce)

Step H turns a payer policy plus the confirmed indication into the conditions a coordinator checks. This page says how
we measure it, what we found, and what we have not measured. Code, test sets and run commands: `experiments/eval/` (see its README).

## What a test is

One **test** = a guideline (the whole policy text) + the confirmed indication's printed heading + a procedure order
(CPT, procedure as written, diagnosis, age, sex, plan). Step H returns a logic tree of conditions. No chart is involved:
the tree is compared with an **answer key** for that indication.

- **Keys** (`tests/fixtures/truth/`): hand-built trees. 23 Florida Blue policies and 8 other payers were built by Fable
  in a sandbox; 2 repo fixtures were built by hand (FL varicose veins, CMS NCD 20.8.3). Keys are not ground truth —
  they omit some routes the policy grants — so every disputed finding is checked against the policy text itself.
- **Test sets** (`experiments/eval/`): 15 fixture tests (FL veins ×4, CMS pacemaker, and the harder pathways of FL
  sleep testing, PAP, knee, spine, lymphedema) and 10 holdout tests (Fallon ICD ×7, UHC venous ×3) that no prompt was
  tuned on. Orders and headings for the holdout were written from the policy only, never the key.

## How a tree is scored

1. **Alignment.** Each generated condition is matched to key conditions (same, narrower, part of, negation, …). Two
   independent aligners per pair; a third adjudicates disagreements.
2. **Exact check.** A SAT solver searches every chart — each condition met, not met or silent — for one the tree
   approves but the key denies (a *requirement the chart could skip*) and the reverse (a *good chart refused*).
3. **Blind policy review.** Every flagged chart and every key condition missing from the tree goes to two reviewers who
   see only the policy text and the concrete chart — never the version or the key. A third breaks ties. Only
   policy-confirmed findings count.
4. **Deletion test.** Planted requirement drops must be caught 100%.

Metrics: policy-confirmed **missing conditions** (primary — the coordinator is never asked), **skippable requirements**,
**extra conditions** by kind (review load), **never-ready** (a condition no chart can answer on every path), cost.

## Results (gpt-6-sol, 25 tests)

> **Test set:** 15 fixture tests (FL veins ×4, CMS pacemaker, and 10 harder Florida Blue pathways in sleep, PAP, knee,
> spine and lymphedema — prompts were developed against these) plus 10 holdout tests (Fallon ICD ×7, UHC venous ×3 —
> never tuned on). The holdout keys are small (1–4 conditions, mostly "meets InterQual / NCD"), so they catch fewer
> kinds of error. Numbers below are all 25 together; same tests, inputs, scorer and blind review for every version.

| Metric (all 25 tests) | v1.1 | form | loose | **shipped (loose-next + admin)** |
|---|---|---|---|---|
| Tests with a checklist | 15 (stage C lost the section on 10) | 25 | 25 | 25 |
| **Missing conditions**, policy-confirmed | **2** | **3** | **1** | **0** |
| Tests where a chart can skip a requirement | 3 | 4 | 3 (all via the exemption) | 3 (all via the exemption) |
| Conditions per checklist (mean) | 19.7 | 32.1 | 29.2 | 27.8 |
| Conditions shown after admin folding | 19.7 | 32.1 | 29.2 | **26.4** |
| Extra conditions not in the key (shown) | 2.5 | 19.5 | 15.1 | **12.7** |
| Tests that can never reach "ready" | 1 of 15 | 14 | 13 | **10** |
| $ per test (gpt-6-sol prices) | ~0.08 | ~0.31 | 0.23 | 0.25 |

- **Missing conditions** is the primary metric: a requirement the policy states that the checklist never asks about.
  *Skippable* counts the same kind of gap from the chart's side — a chart the checklist would let through that the
  policy denies (form's 3 holdout cases are the missing "18 and older" counted both ways).
- **Step-therapy exemption.** Florida Blue policies print an exemption process; loose and shipped keep it as a route the
  coordinator verifies (its question cannot be answered from a chart, so it always goes to review). Blind reviewers
  judged that it does not waive conservative care on those tests, which gives the 3; if it does, those are 0.
- **v1.1's stage C** lost the confirmed section on 10 of 25 tests (9 of 10 holdout) before step H ran; v1.1 also reads
  only that section, which is why it adds few extras and misses conditions printed elsewhere.
- **Admin folding** (shipped) folded 36 of 696 conditions (5%) — procedure wording 20, paperwork 9, heading or
  definition 7 — behind "Not asked of the chart". It hid no key condition and created no skippable requirement.
- **Extra conditions by kind** (mean per test, loose → shipped as shown): billing 3.1 → 2.1, definition 1.7 → 1.1,
  documentation list 1.0 → 0.2, payer judgment 0.6 → 0.2, post-op document 0.8 → 0.6, scope restatement 1.8 → 2.5,
  clinical requirement the key lacks 3.2 → 2.5, clinical exclusion the key lacks 2.8 → 3.4.
- Costs marked ~ are converted from gpt-5.5 list prices recorded at run time.
- **Arms we dropped** (scored with an earlier, non-blind method, so not in the table): script and tools (2–4× cost,
  more incoherent trees), an external fix-point loop (3× cost, more scope creep, one skippable requirement).
- The **step-therapy exemption** printed in Florida Blue policies is kept as a route the coordinator verifies; reviewers
  disagree on whether it waives conservative care, so it never auto-satisfies anything.

## How reliable the scorer is

- Deletion test: 764 of 764, then 394 of 394 planted gaps caught.
- The exact check replaced an earlier sampling search that missed 32–39% of planted gaps; all earlier numbers were
  re-scored.
- Aligners agree on 94–98% of matches; blind reviewers on 95–97% of cases.
- **All aligners and reviewers are Claude** (same model, same brief): agreement is an upper bound, not human or
  clinical validation.

## The judge (reading charts) — measured separately

- **Phase 1 stress run** (`aira-necessity` repo, branch phase-2, `docs/judgement-findings.md`; 9 Oct 2026, tag `v1`, gpt-5.5): 142 synthetic charts with
  known answers on the two fixture guidelines. **False "Ready to submit": 1 / 142.** Determination correct 137 / 142;
  leaf verdicts correct 1,225 / 1,268 (97%); payer 142 / 142, CPT 139 / 142; about $0.11 and 17 s per chart. Messy
  wording, shuffled order, other formats and prompt injection did not move it; long charts lost the procedure request
  in 2 of the 5 wrong determinations.
- **v1.2 record-reading eval** (gpt-6-sol, sample charts, `record_eval.py`; v1.2-tools `data/record_eval/sol6-medium/EVAL.md`): every miss traced to the checklist asking
  for something the chart does not hold (CPT descriptor and billing lines, since folded as admin); none to the judge
  misreading the chart or the sectioner hiding evidence.
- Not yet re-run at scale on the shipped pipeline (v1.2 trees, gpt-6-luna judge), on real clinician-written charts, or
  on guidelines beyond the two fixtures.

## What we have not measured

- **n is small.** Zero misses in 25 tests bounds the miss rate at roughly 12% (95%); it does not show it is zero.
- **Indication choice.** Tests are given the confirmed indication; picking it is unmeasured at scale.
- **Run-to-run variance.** Rebuilding a checklist can change it; one carotid demo case folded a key condition (the order
  stated it, but the fold was silent) after a rebuild.

Product stance that follows from this: the pipeline sources indications, conditions and evidence; **the coordinator
accepts every item**. There are no automatic "met" checks.

## Why v1.1 did poorly

v1.1's step H read only the section its stage C cut out for the indication. When the cut missed the indication (10 of
25 tests) there was no checklist; even with the right section, limits printed elsewhere (reimbursement exclusions,
definitions with thresholds, "criteria above", age and FDA scope) were invisible, and a line-accounting check pushed
the model toward citing lines rather than reasoning about the logic. v1.2 confirms the indication by its quoted heading,
reads the whole policy, and checks only quotes and citations.

## What led to each version

- **loose (v1.2):** v1.1 lost sections and missed limits printed elsewhere, so the confirmed indication is given and
  step H reads the whole policy in one pass, with an add-only review step. Earlier v1.1 audits traced most misses to
  scope words in the grant sentence ("in adults", "FDA-approved"), which the prompt now names.
- **form:** built to make the logic checkable by code (a JSON tree plus a check loop). It came out no safer and dropped
  "18 and older" on three holdout tests, so it was not shipped.
- **Plan rule:** checklists asked "not an FEP/SAO member" on every path, so no case could reach ready; plan-only
  conditions are now pruned using the member's plan.
- **loose-next (shipped):** loose was complete but noisy. Billing lines, evidence summaries, payer judgments and
  post-procedure documents go to notes; keep rules (coded diagnoses, attestations, limits, definitions with thresholds,
  open routes) were added after an early version lost two of them.
- **Admin folding:** procedure wording, paperwork and headings are risky to delete (the gold labels showed a few match
  the key), so they are folded and restorable instead of removed.
- **Exact scorer:** a deletion test showed the first scorer missed about a third of planted gaps, so it was replaced
  with a SAT check and every number was re-scored.

## Raw numbers by test set

Counts with denominators (tests with a checklist). Conditions and extras are means per test; shipped shows the full
checklist / what the coordinator sees after folding. $ at gpt-6-sol prices (~ = converted from gpt-5.5 list prices).

| Set | Version | Checklists | Missing conditions | Skippable tests | Conditions | Extras | Never-ready | $/test |
|---|---|---|---|---|---|---|---|---|
| Fixtures (15) | v1.1 | 14 / 15 | 2 / 14 | 3 / 14 | 20.8 | 2.5 | 1 / 14 | ~0.10 |
| | form | 15 / 15 | 0 / 15 | 1 / 15 | 42.9 | 23.7 | 5 / 15 | ~0.37 |
| | loose | 15 / 15 | 0 / 15 | 3 / 15 | 40.3 | 18.3 | 4 / 15 | 0.26 |
| | shipped | 15 / 15 | 0 / 15 | 3 / 15 | 39.5 / 37.4 | 18.2 / 16.1 | 2 / 15 | 0.28 |
| Holdout (10) | v1.1 | 1 / 10 | 0 / 1 | 0 / 1 | 5.0 | 2.0 | 0 / 1 | ~0.05 |
| | form | 10 / 10 | 3 / 10 | 3 / 10 | 15.9 | 13.1 | 9 / 10 | ~0.23 |
| | loose | 10 / 10 | 1 / 10 | 0 / 10 | 12.6 | 10.3 | 9 / 10 | 0.18 |
| | shipped | 10 / 10 | 0 / 10 | 0 / 10 | 10.3 / 9.9 | 7.9 / 7.5 | 8 / 10 | 0.19 |

Skippable tests for loose and shipped on fixtures are all through the step-therapy exemption route. Holdout never-ready
is high for every version because most holdout indications require "meets InterQual / NCD", which no chart can show.
Sources: guideline-reduce `experiments/tree_diff/{v11-baseline, v12-fixtures-strict, v12-holdout, loose-next-admin}/summary.json`.
