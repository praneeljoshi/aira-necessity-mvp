# Evals

Step H turns a payer policy plus the confirmed indication into the conditions a coordinator checks. The coordinator
accepts every item; nothing is approved automatically. So the error that matters is a **missing condition** — a
requirement the policy states that the checklist never asks about. Code: `experiments/eval/`.

## 1. How we evaluate

**Answer keys.** Hand-built condition trees per policy pathway (`tests/fixtures/truth/`): 23 Florida Blue and 8 other
payers built by Fable in an isolated sandbox from the PDF alone, plus 2 built by hand (FL veins, CMS pacemaker). Keys
were critiqued by independent reviewers and corrected. They are not perfect (some omit routes the policy grants), so
every disputed finding is settled against the policy text, not the key.

**Test sets.** A test = the whole policy + the confirmed indication's printed heading + a procedure order (CPT,
diagnosis, age, sex, plan). Orders and headings are written by agents that see the policy, never the key.
- 15 fixture tests: FL veins ×4, CMS pacemaker, and the harder Florida Blue pathways (sleep, PAP, knee, spine,
  lymphedema). Prompts were developed against these.
- 10 holdout tests: Fallon ICD ×7, UHC veins ×3. Never tuned on.

**Simulated charts (judge only).** 142 synthetic charts with known answers, written from the fixture trees with planted
facts, conflicts, messy wording and other formats (`stress/`). These test chart reading, not checklist building.

**Harness.** For each test:
1. Two aligners independently match generated conditions to key conditions; a third adjudicates.
2. A SAT solver checks every possible chart (each condition met / not met / silent) for one the checklist passes but
   the key denies, and the reverse.
3. Two blind reviewers check each finding against the policy text, without seeing the key or which version made it.
4. A deletion test plants dropped requirements; the solver must catch 100%.

**Reliability.** Deletion test 100% (≈1,000 planted gaps). Aligners agree 94–98%, reviewers 95–98%. All reviewers
are Claude, so this is consistency, not clinical validation. n = 25 bounds the miss rate below ~12%, not at zero.

## 2. Results and the decisions they drove

| All 25 tests, gpt-6-sol | v1.1 | form | loose | **shipped** |
|---|---|---|---|---|
| Missing conditions | 2 / 15 | 3 / 25 | 1 / 25 | **0 / 25** |
| No checklist (section lost) | 10 / 25 | 0 | 0 | 0 |
| Conditions shown (mean) | 19.7 | 32.1 | 29.2 | 26.4 |
| $ per test | ~0.08 | ~0.31 | 0.23 | 0.25 |

- **Don't slice the policy into sections.** v1.1 read only the section it cut out and lost it on 10 of 25 tests, missing limits printed elsewhere.
- **Keep the prompt open-ended.** Adding structure (JSON forms, tools, scripts, loops) missed as much, cost 2–4× more and tripped over the logic.
- **Complete first, then quiet.** Keep rules got missing conditions to zero; folding procedure wording, paperwork and headings out of view cut the noise enough to ship.
