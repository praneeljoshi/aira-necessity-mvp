# experiments/eval

These tools score step H's requirement tree against a hand-built answer key. They check the logic exactly. They do not compare wording.

| file | what it is |
|---|---|
| `tree_diff.py` | The scorer. The model makes one call per pair to align leaves. Everything after that is code: an exact SAT check of the three-valued logic for false approvals and missed good charts. It also compares the qualifying chart, the silent-exclusion case and thresholds. |
| `fa_mutation_check.py` | The deletion test. For each required key leaf, it removes the generated leaves that stand for that leaf and checks whether the scorer reports the false approval that opens. Brute force supplies the ground truth. The detection rate must be 100%. |
| `pairs.py` | Reads the pairs. Results rows come from `experiments/scripts/reduce_code.py` (`results-*.jsonl` plus `criteria/<key>.json`), or from a v1.1 score store. They are paired with the answer keys in `tests/fixtures/truth/`. The two repo fixtures `bcbsfl-02-33000-31` and `cms-ncd-20-8-3` map to `tests/fixtures/*.json`. |
| `align_trees.md` | The alignment prompt. |
| `test_sets/` | The 15 fixture tests and the 10 holdout tests. Each set has the order rows (`*_orders.jsonl`) and the confirmed headings (`*_headings.jsonl`). |

## Run

1. Produce a results file. This step makes paid model calls (step H). Its output goes to `data/reduce_loose/<model>/`, which git ignores.

```
STEP_H=loose-next OPENAI_API_KEY=... .venv/bin/python experiments/scripts/reduce_code.py \
    --orders experiments/eval/test_sets/fixture_orders.jsonl \
    --headings experiments/eval/test_sets/fixture_headings.jsonl --tag fixtures
# -> data/reduce_loose/<model>/results-heading-loose-next-fixtures.jsonl  (holdout: holdout_*.jsonl, --tag holdout)
```

2. Align the leaves without a model call: export the prompts, answer them, then import the answers. If no cached alignment exists and you don't pass `--export-prompts`, `tree_diff.py` calls the model instead.

```
R=data/reduce_loose/<model>/results-heading-loose-next-fixtures.jsonl
.venv/bin/python experiments/eval/tree_diff.py --results $R --export-prompts /tmp/align
#   answer each /tmp/align/<arm>/<name>.md as <name>.json beside it ({"links": [...]}, one link per G leaf)
.venv/bin/python experiments/eval/tree_diff.py --results $R --import-answers /tmp/align
```

When the alignments are cached, scoring makes no calls:

```
.venv/bin/python experiments/eval/tree_diff.py --results $R                      # full tree
.venv/bin/python experiments/eval/tree_diff.py --results $R --view coordinator   # admin leaves pruned as the app does
.venv/bin/python experiments/eval/fa_mutation_check.py --results $R             # deletion test on the same pairs
```

Output goes to `experiments/eval/data/`, which git ignores. Pass `--out` to put it somewhere else:

- `report.md`: a summary for each arm, then each test's false approvals, missed good charts and threshold differences.
- `results.json`: every scored row.
- `<arm>/align/<name>.json`: the cached alignments. Each one is stamped with both trees and is reused only while the stamp still matches.
- `fa_mutation_check.json`: the deletion test's results.

In the coordinator view, a pair with no alignment of its own reuses the full view's alignment, minus the pruned leaves.

Tests: `.venv/bin/python -m pytest -q experiments/tests/test_tree_diff.py`. They are pure: synthetic trees, the repo's answer keys and `tmp_path`.
