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

| | v1.1 | v1.2 loose | loose-next (early) | **shipped: loose-next + admin** |
|---|---|---|---|---|
| Missing conditions, policy-confirmed | 2 (+10 tests where stage C lost the section) | 1 | 1 | **0** |
| Conditions shown per test (mean) | — | 29.2 | 24.0 | 26.4 |
| Tests that can never reach "ready" | — | 13 | 9 | 10 |
| $ per test | 0.22 | 0.23 | 0.20 | 0.25 |

- **v1.1's stage C** lost the confirmed section on 10 of 25 tests (9 of 10 holdout) before step H ran. v1.2 gives step H
  the whole policy and the confirmed indication.
- **Admin folding** (procedure wording, paperwork, headings) folded 36 of 696 conditions (5%) behind "Not asked of the
  chart". It created no skippable requirement and hid no key condition.
- **Targeted noise** (billing, definitions, documentation lists, payer judgments, post-op documents) fell 62% from loose.
- **Arms we dropped:** form (3 holdout tests dropped "18 and older"), script/tools (2–4× cost, more incoherent trees),
  an external fix-point loop (3× cost, more scope creep, one skippable requirement).
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
