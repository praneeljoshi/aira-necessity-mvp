"""Pure tests for experiments/eval: tree_diff's logic after alignment, the results-row reader, the coordinator view,
and the deletion test. No model calls, no data/: synthetic trees, the repo's answer keys, tmp_path."""
import json

from experiments.eval import fa_mutation_check as fm
from experiments.eval import pairs as P
from experiments.eval import tree_diff as td

L = lambda i: ("leaf", i)


def al(*links):
    return td.Alignment(links=[td.Link(gen=g, relation=r, truth=t) for g, r, t in links])


def run(t_tree, g_tree, a, t_un=(), g_un=(), t_thr=None, g_thr=None):
    tt = {i: i for i in td.leaves(t_tree)}
    gt = {i: i for i in td.leaves(g_tree)}
    return td.compare(t_tree, tt, set(t_un), t_thr or {}, g_tree, gt, set(g_un), g_thr or {}, a)


def flips(ws):
    return sorted(tuple(w["flip"]) for w in ws)


def test_eval_three_valued():
    full = 0b111  # rows: MET, NOT_MET, INSUFFICIENT for leaf a
    env = {"a": (0b001, 0b010), "b": (0b111, 0)}
    assert td.ev(("all", [L("a"), L("b")]), env, full) == (0b001, 0b010)
    assert td.ev(("not", L("a")), env, full) == (0b010, 0b001)          # INSUFFICIENT stays
    assert td.ev(("any", [L("a"), ("not", L("b"))]), env, full) == (0b001, 0b010)
    m, n = td.ev(("atl", 1, [L("a"), ("not", L("b"))]), env, full)
    assert (m, n) == (0b001, 0b010)


def test_equivalent_trees_have_no_witnesses():
    t = ("all", [L("a"), ("any", [L("b"), L("c")])])
    g = ("all", [L("x"), ("any", [L("y"), L("z")])])
    r = run(t, g, al(("x", "same", ["a"]), ("y", "same", ["b"]), ("z", "same", ["c"])))
    assert r["false_approvals"] == [] and r["missed_good"] == []
    assert r["exhaustive"] and r["exact_heuristic"]["false_approvals"] == 0 and r["exact_heuristic"]["missed_good"] == 0


def test_dropped_requirement_is_a_single_flip_false_approval():
    t = ("all", [L("dx"), L("pain"), L("pt")])
    g = ("all", [L("p"), L("q")])
    r = run(t, g, al(("p", "same", ["pain"]), ("q", "same", ["pt"])))
    assert flips(r["false_approvals"]) == [("T.dx",)]
    assert r["key_unused"] == ["dx"]


def test_extra_exclusion_not_is_never_ready_when_silent():
    t = ("all", [L("a")])
    g = ("all", [L("x"), ("not", L("cosmetic"))])
    r = run(t, g, al(("x", "same", ["a"]), ("cosmetic", "none", [])))
    assert r["silence"] == {"key": "MET", "gen": "INSUFFICIENT"}
    assert flips(r["missed_good"]) == [("G.cosmetic",)]
    assert r["false_approvals"] == []


def test_and_vs_or():
    t = ("all", [L("a"), L("b")])
    g = ("any", [L("x"), L("y")])
    r = run(t, g, al(("x", "same", ["a"]), ("y", "same", ["b"])))
    assert flips(r["false_approvals"]) == [("T.a",), ("T.b",)]


def test_negation_and_combines():
    t = ("all", [("not", L("dvt")), L("a"), L("b")])
    g = ("all", [L("no_dvt"), L("ab")])
    r = run(t, g, al(("no_dvt", "negation", ["dvt"]), ("ab", "combines", ["a", "b"])))
    assert r["false_approvals"] == [] and r["missed_good"] == []


def test_unanswerable_is_met_and_reported():
    t = ("all", [L("a"), L("b")])
    g = ("all", [L("x"), L("y")])
    r = run(t, g, al(("x", "same", ["a"]), ("y", "same", ["b"])), g_un=["y"])
    assert flips(r["false_approvals"]) == [("T.b",)]
    assert r["unanswerable"]["gen"] == ["y"]


def test_threshold_difference_listed():
    t, g = ("all", [L("a")]), ("all", [L("x")])
    r = run(t, g, al(("x", "same", ["a"])), t_thr={"a": {"op": "gte", "value": 2}}, g_thr={"x": {"op": "eq", "value": 2}})
    assert r["thresholds"][0]["key"] == "a"


def test_large_trees_use_the_neighbourhood():
    t = ("all", [L(f"a{i}") for i in range(30)])
    g = ("all", [L(f"x{i}") for i in range(29)])
    r = run(t, g, al(*[(f"x{i}", "same", [f"a{i}"]) for i in range(29)]))
    assert not r["exhaustive"]
    assert flips(r["false_approvals"]) == [("T.a29",)]


def test_check_alignment_flags_bad_links():
    a = al(("x", "same", ["nope"]), ("x", "combines", ["a"]))
    p = td.check_alignment(a, {"a"}, {"x", "y"})
    assert any("unknown T" in x for x in p) and any("twice" in x for x in p) and any("y not linked" in x for x in p)


def test_v11_expression_and_key():
    e = {"all": ["a", {"not": "b"}, {"at_least": {"k": 2, "of": ["c", "d", "e"]}}]}
    assert td.from_expr(e) == ("all", [L("a"), ("not", L("b")), ("atl", 2, [L("c"), L("d"), L("e")])])
    assert P.v11_key("ab" * 32, "29877", "Debridement for arthrofibrosis (left)") == \
        "abababababababab-29877-debridement-for-arthrofibrosis"


def test_extra_alternative_in_v11_is_not_a_false_approval_by_itself():
    # key: one indication; v1.1: that indication OR another one the key's pathway does not list
    t = ("all", [L("dx"), L("size")])
    g = ("any", [("all", [L("x"), L("y")]), L("other_route")])
    r = run(t, g, al(("x", "same", ["dx"]), ("y", "same", ["size"]), ("other_route", "none", [])))
    assert r["false_approvals"] == []
    # but an extra mandatory requirement is assumed met when looking for false approvals
    g2 = ("all", [L("x"), L("photos")])
    r2 = run(t, g2, al(("x", "same", ["dx"]), ("photos", "none", [])))
    assert flips(r2["false_approvals"]) == [("T.size",)]
    assert flips(r2["missed_good"]) == [("G.photos",)]


def test_negation_of_several_is_none_of():
    t = ("all", [L("dx"), ("not", ("any", [L("ci1"), L("ci2")]))])
    g = ("all", [L("x"), L("no_ci")])
    r = run(t, g, al(("x", "same", ["dx"]), ("no_ci", "negation", ["ci1", "ci2"])))
    assert r["false_approvals"] == [] and r["missed_good"] == []


# ---------------------------------------------------------------- exact SAT check

import random  # noqa: E402

MET, NM, INS = td.MET, td.NOT_MET, td.INSUFFICIENT


def rand_tree(rng, pool, depth=0):
    r = rng.random()
    if depth >= 3 or r < 0.3:
        return ("const", rng.choice(td.VALUES)) if rng.random() < 0.04 else L(rng.choice(pool))
    if r < 0.42:
        return ("not", rand_tree(rng, pool, depth + 1))
    ks = [rand_tree(rng, pool, depth + 1) for _ in range(rng.randint(1, 4))]
    if r < 0.55:
        return ("atl", rng.randint(1, len(ks)), ks)
    return (rng.choice(["all", "any"]), ks)


def test_sat_agrees_with_brute_force_on_random_trees():
    rng = random.Random(7)
    seen_fa = seen_none = seen_route = 0
    for _ in range(400):
        nk, ng = rng.randint(1, 6), rng.randint(0, 4)
        keys, gens = [f"T.k{i}" for i in range(nk)], [f"G.g{i}" for i in range(ng)]
        T = rand_tree(rng, keys)
        Gx = rand_tree(rng, keys + gens)
        if len(set(td.leaves(T)) | set(td.leaves(Gx))) > 10:
            continue
        x = td.exact_diff(T, Gx, cap=50, cap_missed=50)
        b = td.brute_force(T, Gx)
        assert x["false_approval"] == (b["false_approvals"] > 0), (T, Gx)
        assert x["missed_good_exists"] == (b["missed_good"] > 0), (T, Gx)
        assert bool(x["false_approvals"] or x["false_approvals_via_gen_only_routes"]) == x["false_approval"]
        # direct = some false approval with every generated-only route not MET
        bd = td.brute_force(T, Gx, fix={r: (NM, INS) for r in x["routes"]})
        assert bool(x["false_approvals"]) == (bd["false_approvals"] > 0), (T, Gx, x["routes"])
        # per-key-leaf attribution, "alone": that key leaf off its qualifying value, every other key leaf on it
        base = x["baseline"]
        kv = sorted(v for v in base if v in set(td.leaves(T)))
        for k in kv:
            fix = {v: (base[v],) for v in kv if v != k}
            fix[k] = tuple(y for y in td.VALUES if y != base[k])
            alone = td.brute_force(T, Gx, fix=fix)["false_approvals"] > 0
            assert x["fa_by_key_leaf"].get(k, {}).get("alone", False) == alone, (T, Gx, k)
            anyk = td.brute_force(T, Gx, fix={k: fix[k]})["false_approvals"] > 0
            assert (k in x["fa_by_key_leaf"]) == anyk, (T, Gx, k)
        seen_fa += x["false_approval"]
        seen_none += not x["false_approval"]
        seen_route += bool(x["false_approvals_via_gen_only_routes"])
    assert seen_fa > 50 and seen_none > 50 and seen_route > 5


def test_witnesses_are_minimal():
    rng = random.Random(11)
    checked = 0
    for _ in range(300):
        keys, gens = [f"T.k{i}" for i in range(rng.randint(2, 6))], [f"G.g{i}" for i in range(rng.randint(0, 3))]
        T, Gx = rand_tree(rng, keys), rand_tree(rng, keys + gens)
        x = td.exact_diff(T, Gx)
        base = x["baseline"]
        for w in x["false_approvals"] + x["false_approvals_via_gen_only_routes"] + x["missed_good"]:
            a = {**base, **w["values"], **w.get("routes_off", {})}
            fa = w["kind"] != "missed_good"
            ok = lambda a: (td.eval_assign(Gx, a) == MET and td.eval_assign(T, a) != MET) if fa else \
                (td.eval_assign(T, a) == MET and td.eval_assign(Gx, a) != MET)
            assert ok(a)
            for v in w["flip"]:                       # resetting any one flipped leaf to the qualifying chart breaks it
                assert not ok({**a, v: base[v]}), (T, Gx, w, v)
            checked += 1
        # failing-key-leaf sets are distinct and none contains another (blocking on minimal sets)
        sets = [frozenset(w["fails"]) for w in x["false_approvals"] + x["false_approvals_via_gen_only_routes"]]
        assert all(not (s1 < s2 or s1 == s2) for i, s1 in enumerate(sets) for s2 in sets[i + 1:])
    assert checked > 100


def test_mobitz_compound_exclusion():
    # key: AV block, symptomatic, and NOT (asymptomatic Mobitz I without a prolonged QRS / intra-His block)
    excl = lambda p: ("not", ("all", [L(p + "mobitz_i"), ("not", ("any", [L(p + "qrs"), L(p + "his")]))]))
    t = ("all", [L("av_block"), L("symptomatic"), excl("")])
    # generated: same exclusion over generated-only leaves, and no "symptomatic"
    g = ("all", [L("x"), excl("g_")])
    r = run(t, g, al(("x", "same", ["av_block"]), ("g_mobitz_i", "none", []), ("g_qrs", "none", []), ("g_his", "none", [])))
    # the dropped requirement, and (the generated exclusion being unlinked) the key's exclusion firing unseen
    assert [w["fails"] for w in r["false_approvals"]] == [["T.symptomatic"], ["T.his", "T.mobitz_i", "T.qrs"]]
    assert r["false_approvals"][0]["flip"] == ["T.symptomatic"]
    # the exclusion's trigger (Mobitz I, under a NOT) is never a route: holding routes off leaves it absent. Its
    # exceptions (prolonged QRS, intra-His block) are optional positive leaves, so they count as routes (held off).
    assert r["gen_only_routes"] == ["G.g_his", "G.g_qrs"]
    assert r["false_approvals_heuristic"]              # the heuristic pass, fixed, now finds it too
    # and with the exclusion aligned to the key's leaves
    r2 = run(t, g, al(("x", "same", ["av_block"]), ("g_mobitz_i", "same", ["mobitz_i"]), ("g_qrs", "same", ["qrs"]),
                      ("g_his", "same", ["his"])))
    assert [w["fails"] for w in r2["false_approvals"]] == [["T.symptomatic"]]


def test_hidden_behind_or_needs_many_flips():
    # key: compression only on the pain route; generated: the pain route forgot it. A false approval needs every other
    # route off as well: 4 flips from the qualifying chart, among 30 variables (no exhaustive heuristic search).
    pad = [f"p{i}" for i in range(25)]
    t = ("all", [*map(L, pad), ("any", [L("ulcer"), L("bleed"), L("phleb"), ("all", [L("pain"), L("comp3")])])])
    g = ("all", [*map(L, pad), ("any", [L("ulcer"), L("bleed"), L("phleb"), L("pain")])])
    a = al(*[(i, "same", [i]) for i in pad + ["ulcer", "bleed", "phleb", "pain"]])
    r = run(t, g, a)
    assert not r["exhaustive"]
    [w] = r["false_approvals"]
    assert w["fails"] == ["T.bleed", "T.comp3", "T.phleb", "T.ulcer"]
    x = r["fa_by_key_leaf"]["T.comp3"]
    assert (x["with_others"], x["alone"], x["alone_direct"]) == (True, False, False)
    assert sorted(x["example"]) == ["T.bleed", "T.comp3", "T.phleb", "T.ulcer"]
    assert r["false_approvals_heuristic"] == []        # what the old neighbourhood search missed


def test_generated_only_route_is_reported_separately():
    t = ("all", [L("dx"), L("comp3")])
    g = ("all", [L("x"), ("any", [L("c"), L("exemption")])])
    r = run(t, g, al(("x", "same", ["dx"]), ("c", "same", ["comp3"]), ("exemption", "none", [])))
    assert r["false_approvals"] == []
    [w] = r["false_approvals_via_gen_only_routes"]
    assert w["fails"] == ["T.comp3"] and w["routes_used"] == ["G.exemption"]
    assert r["gen_only_routes"] == ["G.exemption"]


def test_unanswerable_follows_the_app():
    # a required unanswerable generated leaf is MET: the key leaf it stood for can fail
    t = ("all", [L("a"), L("b"), ("not", L("ex"))])
    g = ("all", [L("x"), L("y"), ("not", L("gex"))])
    links = al(("x", "same", ["a"]), ("y", "same", ["b"]), ("gex", "same", ["ex"]))
    r = run(t, g, links, g_un=["y"])
    assert [w["fails"] for w in r["false_approvals"]] == [["T.b"]]
    # an unanswerable exclusion never fires (NOT_MET under the NOT): the key's exclusion present is approved
    r = run(t, g, links, g_un=["gex"])
    [w] = r["false_approvals"]
    assert w["fails"] == ["T.ex"] and w["values"] == {"T.ex": MET}
    # an unanswerable key leaf is MET: dropping it in the generated tree is no false approval
    g2 = ("all", [L("x"), ("not", L("gex"))])
    r = run(t, g2, al(("x", "same", ["a"]), ("gex", "same", ["ex"])), t_un=["b"])
    assert r["false_approvals"] == [] and not r["false_approval"]


def test_silence_counts_as_a_false_approval_value():
    # key needs x documented; generated asks "no contraindication" as NOT x: silent x is INSUFFICIENT on both
    t = ("all", [L("a"), ("any", [L("b"), ("not", L("b"))])])     # key: b documented either way
    g = ("all", [L("x")])
    r = run(t, g, al(("x", "same", ["a"])))
    [w] = r["false_approvals"]
    assert w["values"] == {"T.b": INS}                              # only the silent chart separates them


# ---------------------------------------------------------------- the deletion test

def test_fa_mutation_check_detects_every_planted_gap():
    # generated tree = the key's, leaf for leaf: deleting the leaf for any required key leaf must open a false
    # approval, and the exact check must report it (100%)
    t = ("all", [L("dx"), L("size"), ("any", [L("ulcer"), ("all", [L("pain"), L("comp")])]), ("not", L("dvt"))])
    g = td.subst(t, lambda i: L("g_" + i))
    a = al(*[("g_" + i, "same", [i]) for i in td.leaves(t)])
    tt, gt = {i: i for i in td.leaves(t)}, {i: i for i in td.leaves(g)}
    rec = {"arm": "synthetic", "name": "pair", "t": (t, tt, set(), {}), "g": (g, gt, set(), {}), "al": a}
    r = fm.run([rec], "synthetic")
    assert r["deletions"] == 5                       # every positive key leaf; dvt sits under a NOT
    assert r["real_fa_with_k"] == 5 and r["detected_with_k"] == 5 and r["detection_rate_with_k"] == 1.0
    assert r["detection_rate_any"] == 1.0 and r["missed"] == [] and r["sat_fa_without_truth"] == 0
    assert all(not c["fa_before"] for c in r["cases"])


# ---------------------------------------------------------------- the reduce runner's results rows

def expr_of(t):
    if t[0] == "leaf":
        return t[1]
    if t[0] == "not":
        return {"not": expr_of(t[1])}
    return {t[0]: [expr_of(c) for c in t[1]]}


def write_run(tmp_path, gid, scenario_id, drop=(), admin=()):
    """A results file and criteria/<key>.json as experiments/scripts/reduce_code.py writes them: the key pathway's tree
    re-expressed with g_ ids, minus `drop`, plus required `admin` leaves flagged admin."""
    key = P.load_key(gid)
    sc = next(s for s in key.scenarios if s.id == scenario_id)
    t = td.from_key(sc.requires)

    def cut(x):
        if x[0] == "leaf":
            return None if x[1] in drop else ("leaf", "g_" + x[1])
        if x[0] == "not":
            c = cut(x[1])
            return c and ("not", c)
        cs = [c for c in map(cut, x[1]) if c]
        return (x[0], cs) if cs else None
    g = cut(t)
    g = ("all", [g] + [("leaf", a) for a in admin])
    text = {c.id: c for c in key.criteria}
    crit = [{"id": "g_" + i, "refs": ["L1"], "quote": text[i].text, "question": text[i].question}
            for i in td.leaves(t) if i not in drop]
    crit += [{"id": a, "refs": ["L2"], "quote": "Use code " + a, "question": "billing", "admin": True,
              "admin_why": "billing or coding"} for a in admin]
    k = f"abc-{scenario_id}"
    d = {"narrowed": {"key": k, "guideline": {"id": gid, "sha256": "0" * 64, "payer": {"name": "x"}},
                      "pathways": [{"id": "indication", "spans": [], "codes": []}], "chosen": ["indication"]},
         "criteria": {"key": k, "criteria": crit, "expressions": [{"pathway": "indication", "expr": expr_of(g)}]}}
    (tmp_path / "criteria").mkdir(exist_ok=True)
    (tmp_path / "criteria" / f"{k}.json").write_text(json.dumps(d))
    row = {"guideline": gid, "pathway": sc.name, "scenario_id": scenario_id, "code": "36475", "key": k,
           "status": "ok", "criteria": len(crit)}
    failed = {"guideline": gid, "pathway": "Accessory Saphenous Veins", "scenario_id": "accessory_saphenous",
              "code": "36478", "error": "ValueError: boom"}
    f = tmp_path / "results-heading-loose-next-fixtures.jsonl"
    f.write_text(json.dumps({**row, "status": "needs_review"}) + "\n" + json.dumps(row) + "\n" + json.dumps(failed) + "\n")
    return f, t


def same_alignment(rec):
    return td.Alignment(links=[td.Link(gen=g, relation="same", truth=[g[2:]]) for g in td.leaves(rec["g"][0])
                               if g.startswith("g_")] +
                        [td.Link(gen=g, relation="none") for g in td.leaves(rec["g"][0]) if not g.startswith("g_")])


def test_results_rows_pair_with_the_repo_fixture_keys(tmp_path):
    f, t = write_run(tmp_path, "bcbsfl-02-33000-31", "great_small_saphenous")
    ps = P.results_pairs(f)
    assert [(p["scenario_id"], p["gen"] is not None) for p in ps] == [("great_small_saphenous", True),
                                                                         ("accessory_saphenous", False)]
    assert ps[0]["arm"] == "results-heading-loose-next-fixtures" and ps[0]["row"]["status"] == "ok"   # last row wins
    assert P.key_path("cms-ncd-20-8-3").name == "centers-for-medicare-medicaid-services-ncd-20-8-3.json"
    assert P.load_key("cms-ncd-20-8-3").scenarios
    out = tmp_path / "out"
    recs = list(td.records([f], [], set(), "full", out))
    assert recs[1]["no_tree"] and recs[1]["error"] == "ValueError: boom"
    assert list(td.aligned(recs)) == []                    # nothing cached: nothing scored, no model call
    td.save_alignment(recs[0], same_alignment(recs[0]), [], "test")
    [rec] = td.aligned(td.records([f], [], set(), "full", out))
    assert rec["alignment_problems"] == []
    T, Gx = td.map_trees(rec["t"][0], rec["t"][2], rec["g"][0], rec["g"][2], rec["al"])
    x = td.exact_diff(T, Gx)
    assert not x["false_approval"] and not x["missed_good_exists"]


def test_dropped_key_leaf_in_a_results_row_is_a_false_approval(tmp_path):
    f, _ = write_run(tmp_path, "bcbsfl-02-33000-31", "great_small_saphenous", drop=("compression_3_months",))
    rec = next(r for r in td.records([f], [], set(), "full", tmp_path / "out") if not r.get("no_tree"))
    T, Gx = td.map_trees(rec["t"][0], rec["t"][2], rec["g"][0], rec["g"][2], same_alignment(rec))
    x = td.exact_diff(T, Gx)
    assert x["false_approval"] and "T.compression_3_months" in x["fa_by_key_leaf"]


def test_coordinator_view_prunes_admin_leaves_and_derives_the_alignment(tmp_path):
    f, _ = write_run(tmp_path, "bcbsfl-02-33000-31", "great_small_saphenous", admin=("billing_note",))
    out = tmp_path / "out"
    full = next(r for r in td.records([f], [], set(), "full", out) if not r.get("no_tree"))
    assert "billing_note" in td.leaves(full["g"][0])
    td.save_alignment(full, same_alignment(full), [], "test")
    coord = next(r for r in td.records([f], [], set(), "coordinator", out) if not r.get("no_tree"))
    assert coord["arm"].endswith("-coordinator") and "billing_note" not in td.leaves(coord["g"][0])
    al, problems = td.cached_alignment(coord)
    assert problems == [] and {l.gen for l in al.links} == set(td.leaves(coord["g"][0]))
    assert json.loads(coord["align_file"].read_text())["aligner"] == "derived from the full view"
