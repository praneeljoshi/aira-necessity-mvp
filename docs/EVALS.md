# Evals

The coordinator accepts every criterion, so the error that matters most is a **missing criterion**.

## 1. Guideline reduction (step H)

Turns the whole policy plus one confirmed indication into a criteria tree. Code: `eval/`.

**Method.**

- **Keys:** criteria trees per indication, hand-built or built by Fable from the PDF alone.
- **Tests:** policy + indication heading + procedure order. 15 dev, 10 holdout (Fallon, UHC) never tuned on.
- **Scoring:** align generated criteria to the key; a SAT solver finds any chart the tree approves and the key denies;
blind reviewers confirm each finding against the policy text.
- **Reliability:** 100% of planted gaps caught; aligners and reviewers agree 95–98%.


| 25 tests               | v1.1    | form   | loose  | **shipped** |
| ---------------------- | ------- | ------ | ------ | ----------- |
| Missing criteria       | 2 / 15  | 3 / 25 | 1 / 25 | **0 / 25**  |
| Section lost (no tree) | 10 / 25 | 0      | 0      | 0           |
| Criteria shown (mean)  | 19.7    | 32.1   | 29.2   | 26.4        |
| $ per test             | 0.08    | 0.31   | 0.23   | 0.25        |


- **Read the whole policy.** v1.1 read only one section and lost it on 10 of 25 tests.
- **Keep the prompt open.** Forms, tools, scripts and loops missed as much at 2–4× the cost.
- **Complete, then quiet.** Zero missing criteria; admin folding trims the noise.

*Reviewers and aligners are Claude; 25 tests is a small sample.*

## 2. Judging (step I)

gpt-6-sol on 120 single-procedure synthetic charts with known outcomes:

| | Result |
| --- | --- |
| False "ready to submit" | **0 / 120** |
| Correct outcome | 115 / 120 (96%) |
| Correct requirement verdicts | 1,015 / 1,052 (96%) |

Messy wording, shuffled notes, long charts, other formats and prompt injection did not move it. On the 5 sample charts
it found every planted fact, including all 3 traps in the 138-page chart.

*Multi-procedure orders (22 more charts) scored 9 / 22 under the old pipeline, which picked the best pathway across
codes; v1.2 has the coordinator confirm the indication per code. Not yet re-run on v1.2.*
