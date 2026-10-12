# Evals

Step H reads a payer policy and lists what the coordinator must check. The coordinator approves every item. So the
mistake that matters most is a **missing condition**: something the policy requires that the list never asks for.
Code: `eval/`.

## 1. How we evaluate

**Answer keys.** For each policy, a correct list of conditions, built by hand or by Fable from the PDF alone. Where a
key and the policy disagree, the policy wins.

**Tests.** Each test is a policy, the indication, and a procedure order. 15 tests we worked against, plus 10 holdout
tests (Fallon, UHC) we never tuned on.

**Simulated charts.** 142 made-up charts with known answers, used to test chart reading.

**Scoring.**
1. Match each generated condition to the key.
2. A solver checks every possible chart for one our list lets through but the key would not.
3. Reviewers check each finding against the policy, without seeing which version made it.

**Reliability.** The scorer caught 100% of planted gaps. Aligners and reviewers agreed about 95–98% of the time.

## 2. Results

| All 25 tests | v1.1 | form | loose | **shipped** |
| --- | --- | --- | --- | --- |
| Missing conditions | 2 / 15 | 3 / 25 | 1 / 25 | **0 / 25** |
| No list at all | 10 / 25 | 0 | 0 | 0 |
| Conditions shown | 19.7 | 32.1 | 29.2 | 26.4 |
| $ per test | 0.08 | 0.31 | 0.23 | 0.25 |

- **Don't cut the policy into sections.** v1.1 lost the section on 10 of 25 tests.
- **Keep the prompt open.** Extra structure missed just as much and cost 2–4× more.
- **Complete first, then quiet.** Zero missing conditions; folding the noise made it shippable.

_Reviewers are Claude, and this is a small sample._
