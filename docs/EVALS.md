# Evals

The coordinator accepts every criterion, so the error that matters most is a **missing criterion**.

## 1. Guideline reduction (step H)

Step H turns the whole policy plus one confirmed indication into a criteria tree. Code: `eval/`.

**Method.**
- **Keys:** criteria trees per indication, hand-built or built by Fable from the PDF alone.
- **Tests:** policy + indication heading + procedure order. 15 dev, 10 holdout (Fallon, UHC) never tuned on.
- **Scoring:** align generated criteria to the key; a SAT solver finds any chart the tree approves and the key denies;
  blind reviewers confirm each finding against the policy text.
- **Reliability:** 100% of planted gaps caught; aligners and reviewers agree 95–98%.

| 25 tests | v1.1 | form | loose | **shipped** |
| --- | --- | --- | --- | --- |
| Missing criteria | 2 / 15 | 3 / 25 | 1 / 25 | **0 / 25** |
| Section lost (no tree) | 10 / 25 | 0 | 0 | 0 |
| Criteria shown (mean) | 19.7 | 32.1 | 29.2 | 26.4 |
| $ per test | 0.08 | 0.31 | 0.23 | 0.25 |

- **Read the whole policy.** v1.1 read only one section and lost it on 10 of 25 tests.
- **Keep the prompt open.** Forms, tools, scripts and loops missed as much at 2–4× the cost.
- **Complete, then quiet.** Zero missing criteria; admin folding trims the noise.

_Reviewers and aligners are Claude; 25 tests is a small sample._

## 2. Judging (step I)

142 synthetic charts with known outcomes:

| | Result |
| --- | --- |
| False "ready to submit" | **1 / 142** |
| Correct outcome | 137 / 142 (96%) |
| Correct requirement verdicts | 1,225 / 1,268 (97%) |

Messy wording, shuffled notes, other chart formats and prompt injection did not move it.

_Run on gpt-5.5. The shipped judge is gpt-6-sol, stronger on general benchmarks; on our 5 sample charts it found every
planted fact. The 142-chart rerun on sol is in progress._
