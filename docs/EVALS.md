# Evals

Step H reduces a payer policy to the criteria tree for one confirmed indication. It sees the whole policy, gets one
retry when code validation fails (quotes, citations, logic), then one add-only audit pass. The coordinator accepts
every criterion, so the error that matters most is a **missing criterion**: one the policy requires that the tree
omits. Code: `eval/`.

## 1. How we evaluate

**Answer keys.** Ground-truth criteria trees per indication: hand-built, or built by Fable from the PDF alone in an
isolated sandbox. Disputes are settled against the policy text, not the key.

**Test sets.** Each test is a policy, the indication heading, and a procedure order. 15 fixture tests (dev set) and
10 holdout tests (Fallon, UHC) never tuned on.

**Synthetic charts.** 142 synthetic charts with known outcomes, used to test the judge.

**Scoring.**
1. Align generated criteria to key criteria.
2. A SAT solver checks every three-valued chart assignment for one the generated tree approves and the key denies.
3. Blind reviewers verify each finding against the policy text.

**Reliability.** The deletion test caught 100% of planted gaps. Aligners and reviewers agreed about 95–98% of the time.

## 2. Results

| All 25 tests | v1.1 | form | loose | **shipped** |
| --- | --- | --- | --- | --- |
| Missing criteria | 2 / 15 | 3 / 25 | 1 / 25 | **0 / 25** |
| No tree (section lost) | 10 / 25 | 0 | 0 | 0 |
| Criteria shown (mean) | 19.7 | 32.1 | 29.2 | 26.4 |
| $ per test | 0.08 | 0.31 | 0.23 | 0.25 |

- **Don't segment the policy.** v1.1 reduced only the section stage C cut out and lost it on 10 of 25 tests.
- **Keep the prompt open.** Added structure (JSON forms, tools, scripts, loops) missed as much at 2–4× the cost.
- **Complete first, then quiet.** Zero missing criteria; admin folding cut the noise enough to ship.

## 3. Judge

142 synthetic charts with known outcomes (stress run, `docs/judgement-findings.md`):

| | Result |
| --- | --- |
| False "ready to submit" | **1 / 142** |
| Correct outcome | 137 / 142 (96%) |
| Correct requirement verdicts | 1,225 / 1,268 (97%) |

Messy wording, shuffled note order, other chart formats and prompt injection did not move it.

_The stress run used gpt-5.5 as the judge. We have since upgraded to gpt-6-sol, a newer model that outperforms
gpt-5.5 on general benchmarks; on our 5 sample charts it found every planted fact, including all 3 traps in the
138-page chart. The 142-chart run has not yet been repeated on sol._

_Reviewers are Claude, and this is a small sample._
