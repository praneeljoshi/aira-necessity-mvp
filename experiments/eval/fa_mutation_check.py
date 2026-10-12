"""Deletion test for the exact false-approval check: make the generated tree stop checking a key requirement and see
whether the check reports a false approval wherever one exists.

    .venv/bin/python experiments/eval/fa_mutation_check.py --results <results-*.jsonl> [--results F ...]
                                                           [--store DIR ...] [--view full|coordinator] [--out DIR]

Pairs and their cached alignments exactly as tree_diff.py reads them (<out>/<arm>/align/, stamps checked); pairs with
no valid cached alignment are skipped and counted. No model call. Writes <out>/fa_mutation_check.json.

For every scored pair and every key leaf k with positive polarity (required, not under a NOT; unanswerable key leaves
are MET and skipped), every generated leaf linked to k (any relation but none) becomes a constant: MET, or NOT_MET if it
sits under a NOT in the generated tree (the generated tree passes it whatever the chart says).

Ground truth, independent of the SAT encoding:
  <= 13 variables   brute force over every three-valued chart (3^n rows, bit-parallel ev())
  14 .. 20          brute force over every two-valued chart (2^n rows): an FA found there is real; the SAT result is
                    also accepted when its witness re-evaluates as an FA under ev() (every witness is re-checked)
  > 20              the SAT result, its witness re-checked by ev()
Detection rate = deletions where SAT reports an FA in which k is not met / deletions where the ground truth has one
(an FA that existed before the deletion does not count for k). The rate over "any FA" is reported too. Both must be
100%. A deletion with no such FA means the generated tree still enforces k some other way; those are listed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.eval import tree_diff as td  # noqa: E402


def mutate(g_tree: tuple, drop: set[str]) -> tuple:
    pol = td.polarity(g_tree)
    return td.subst(g_tree, lambda i: ("const", td.NOT_MET if pol.get(i) else td.MET) if i in drop else ("leaf", i))


def truth(T: tuple, Gx: tuple, sat: dict, k: str | None = None) -> tuple[bool, str]:
    """Is there a false approval (with key leaf k off its qualifying value, when k is given)?"""
    base = sat["baseline"]
    vs = set(td.leaves(T)) | set(td.leaves(Gx))
    fk = {k: tuple(x for x in td.VALUES if x != base[k])} if k else {}
    got = (k in sat["fa_by_key_leaf"]) if k else sat["false_approval"]
    if len(vs) <= 13:
        return td.brute_force(T, Gx, fix=fk)["false_approvals"] > 0, "brute 3-valued"
    if len(vs) <= 20:
        fix = {v: (td.MET, td.NOT_MET) for v in vs}
        if k:
            fix[k] = (td.NOT_MET,) if base[k] == td.MET else (td.MET,)
        if td.brute_force(T, Gx, fix=fix)["false_approvals"]:
            return True, "brute 2-valued"
        return got, "brute 2-valued: none; SAT witness re-checked" if got else "brute 2-valued: none; SAT unsat"
    return got, "SAT (witness re-checked)"


def run(recs, run_name: str = "") -> dict:
    """recs: records with `t`, `g` (tree_diff sides), `al` (Alignment), `arm`, `name` (tree_diff.aligned)."""
    cases, missed, no_fa = [], [], []
    for rec in recs:
        if not rec.get("al"):
            continue
        (t_tree, t_text, t_un, _), (g_tree, g_text, g_un, _), al = rec["t"], rec["g"], rec["al"]
        t_pol = td.polarity(t_tree)
        before = td.exact_diff(*td.map_trees(t_tree, t_un, g_tree, g_un, al))
        for k in sorted(set(td.leaves(t_tree)) - t_un):
            if t_pol.get(k):
                continue
            linked = {l.gen for l in al.links if k in l.truth and l.relation != "none"}
            if not linked:
                continue
            T, Gx = td.map_trees(t_tree, t_un, mutate(g_tree, linked), g_un, al)
            sat = td.exact_diff(T, Gx)
            real, how = truth(T, Gx, sat)
            real_k, how_k = truth(T, Gx, sat, "T." + k)          # an FA in which k itself is not met
            fails_k = any("T." + k in w["fails"] for w in sat["false_approvals"] + sat["false_approvals_via_gen_only_routes"])
            c = {"arm": rec["arm"], "pair": rec["name"], "key_leaf": k, "dropped": sorted(linked),
                 "variables": len(set(td.leaves(T)) | set(td.leaves(Gx))), "truth": real, "how": how,
                 "sat": sat["false_approval"], "direct": bool(sat["false_approvals"]),
                 "k_in_a_witness": fails_k, "k_alone": sat["fa_by_key_leaf"].get("T." + k, {}).get("alone", False),
                 "fa_before": before["false_approval"], "truth_k": real_k, "how_k": how_k,
                 "sat_k": "T." + k in sat["fa_by_key_leaf"]}
            cases.append(c)
            if (real and not sat["false_approval"]) or (real_k and not c["sat_k"]):
                missed.append(c)
            if not real_k:
                # why no FA: does the key still pass with k failing (k is not needed once its route is on)? Is the
                # generated tree ready at all? Which generated leaves still stand for k (relation none, same words)?
                base = sat["baseline"]
                a = {**base, "T." + k: td.NOT_MET}
                c["key_with_only_k_off"] = td.eval_assign(T, a)
                c["gen_with_only_k_off"] = td.eval_assign(Gx, a)
                c["gen_can_be_met"] = td.brute_force(Gx, ("const", td.NOT_MET))["false_approvals"] > 0 \
                    if c["variables"] <= 13 else None
                c["gen_unlinked_leaves"] = sorted(l.gen for l in al.links if l.relation == "none")
                c["key_text"] = t_text.get(k, "").split(" | ")[0][:140]
                no_fa.append(c)
    n_real = sum(c["truth"] for c in cases)
    n_hit = sum(c["truth"] and c["sat"] for c in cases)
    n_real_k = sum(c["truth_k"] for c in cases)
    n_hit_k = sum(c["truth_k"] and c["sat_k"] for c in cases)
    arms = sorted({c["arm"] for c in cases})
    cnt = lambda a, f: sum(1 for c in cases if c["arm"] == a and f(c))
    return {"run": run_name, "deletions": len(cases),
            "real_fa_with_k": n_real_k, "detected_with_k": n_hit_k,
            "detection_rate_with_k": n_hit_k / n_real_k if n_real_k else None,
            "real_fa_any": n_real, "detected_any": n_hit, "detection_rate_any": n_hit / n_real if n_real else None,
            "sat_fa_without_truth": sum(c["sat"] and not c["truth"] for c in cases) + sum(c["sat_k"] and not c["truth_k"] for c in cases),
            "ground_truth_with_k": {h: sum(c["how_k"] == h for c in cases) for h in sorted({c["how_k"] for c in cases})},
            "by_arm": {a: {"deletions": cnt(a, lambda c: True), "real_with_k": cnt(a, lambda c: c["truth_k"]),
                           "detected_with_k": cnt(a, lambda c: c["truth_k"] and c["sat_k"]),
                           "k_alone": cnt(a, lambda c: c["k_alone"]),
                           "fa_existed_before": cnt(a, lambda c: c["fa_before"])} for a in arms},
            "missed": missed, "no_fa": no_fa, "cases": cases}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", action="append", default=[])
    ap.add_argument("--store", action="append", default=[])
    ap.add_argument("--only", default="")
    ap.add_argument("--view", choices=("full", "coordinator"), default="full")
    ap.add_argument("--out", default=str(td.OUT))
    a = ap.parse_args()
    if not a.results and not a.store:
        ap.error("give --results and/or --store")
    out = Path(a.out)
    recs = list(td.records([Path(x) for x in a.results], [Path(x) for x in a.store],
                           {x for x in a.only.split(",") if x}, a.view, out))
    ok = list(td.aligned(recs))
    name = ",".join(dict.fromkeys(r["arm"] for r in recs))
    r = run(ok, name)
    r["pairs"], r["pairs_aligned"] = len(recs), len(ok)
    out.mkdir(parents=True, exist_ok=True)
    (out / "fa_mutation_check.json").write_text(json.dumps(r, indent=1, default=str))
    pct = lambda x: "n/a" if x is None else f"{100 * x:.1f}%"
    print(f"{name}: {len(ok)}/{len(recs)} pairs aligned; {r['deletions']} deletions; an FA with the dropped key leaf "
          f"not met exists in {r['real_fa_with_k']}; SAT finds it in {r['detected_with_k']} "
          f"({pct(r['detection_rate_with_k'])}); any FA: {r['detected_any']}/{r['real_fa_any']}; "
          f"SAT FA without ground truth {r['sat_fa_without_truth']}; missed {len(r['missed'])}")
    print("ground truth (with k):", r["ground_truth_with_k"])
    for arm, x in r["by_arm"].items():
        print(f"  {arm}: {x}")
    print(f"no FA after the deletion: {len(r['no_fa'])}")
    for c in r["no_fa"]:
        print(f"  {c['arm'][:10]:10} {c['pair'][:55]:55} {c['key_leaf']:40} key|only-k-off {c['key_with_only_k_off']:12} "
              f"gen {c['gen_with_only_k_off']:12} dropped {c['dropped']}")
    print(f"wrote {out / 'fa_mutation_check.json'}")


if __name__ == "__main__":
    main()
