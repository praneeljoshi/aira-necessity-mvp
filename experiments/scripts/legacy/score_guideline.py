"""v1 scorer (from the guideline-reduce branch), kept for v1-vs-v1.1 comparison. No model calls.

    python scripts/score_guideline.py tests/fixtures/truth/<id>.json data/guidelines/generated/<id>.json [-v]
    python scripts/score_guideline.py --all          # every truth fixture that has a generated counterpart

Four measures:
  codes      per code in either scope: same tag / different tag / only one side. A covered<->non-covered/investigational
             flip is critical (it stops a covered chart at the gate, or lets a non-covered one through).
  criteria   each truth criterion matched to generated criteria by word overlap (containment of the truth words);
             recall = truth criteria with a match, precision = generated criteria with a match.
  pathways   per code: number of truth pathways vs generated pathways that govern it.
  behaviour  per code: draw random met / not-met assignments over the truth criteria (generated leaves inherit the
             value of their matched truth criterion; unmatched generated leaves draw their own), decide each side
             (any governing pathway whose tree passes), and count agreement. A false pass (generated passes, truth
             does not) is the dangerous direction; a false fail sends a good chart to a person.
"""
from __future__ import annotations

import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from experiments.scripts.legacy.models import Guideline, Scenario  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def governs(g: Guideline, s: Scenario, code: str) -> bool:
    """v1 rule: a pathway that names codes governs those; one that names none governs codes no pathway names."""
    if s.applies_to_cpt:
        return code in s.applies_to_cpt
    return not any(code in x.applies_to_cpt for x in g.scenarios)
STOP = set("the a an of or and is are to in for with has have been be by at as that this from not no any one more "
           "following there were was it its on which than when who all must following individual patient member".split())
MATCH = 0.6     # share of the truth criterion's words found in a generated criterion
SAMPLES = 4000


def words(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", s.lower().replace("≥", " gte ").replace("≤", " lte ")) if w not in STOP}


_NEG = re.compile(r"\b(not|non|no|without|absence|absent|never|none)\b|\bnon-|n't\b", re.I)


def negated(s: str) -> bool:
    return bool(_NEG.search(s))


def match_criteria(t: Guideline, g: Guideline) -> dict[str, str]:
    """generated id -> truth id (best containment of truth words in the generated text, then Jaccard)."""
    out: dict[str, str] = {}
    tw = {c.id: words(c.text) for c in t.criteria}
    for gc in g.criteria:
        gw = words(gc.text)
        best, score = None, 0.0
        for tid, w in tw.items():
            if not w or not gw:
                continue
            contain = len(w & gw) / len(w)
            back = len(w & gw) / len(gw)          # share of the generated words found in the truth criterion
            s = contain * 0.5 + back * 0.5
            if max(contain, back) >= MATCH and s > score:
                best, score = tid, s
        if best:
            out[gc.id] = best
    return out


def parity(g: Guideline) -> dict[str, bool]:
    """criterion id -> True when it sits under an odd number of `not`s (a contraindication): usually absent."""
    out: dict[str, bool] = {}

    def walk(n, neg):
        if n.type == "leaf":
            out.setdefault(n.criterion, neg)
        elif n.type == "not":
            walk(n.child, not neg)
        else:
            for c in n.children:
                walk(c, neg)
    for sc in g.scenarios:
        walk(sc.requires, False)
    return out


def ev(n, val) -> bool:
    if n.type == "leaf":
        return val(n.criterion)
    if n.type == "not":
        return not ev(n.child, val)
    xs = [ev(c, val) for c in n.children]
    return all(xs) if n.type == "all" else any(xs)


def score(truth: Path, gen: Path, verbose: bool = False) -> dict:
    t = Guideline.model_validate_json(truth.read_text())
    g = Guideline.model_validate_json(gen.read_text())
    r: dict = {"id": truth.stem, "truth_status": t.status, "gen_status": g.status}

    # codes
    codes = sorted(set(t.scope.cpt) | set(g.scope.cpt))
    same = [c for c in codes if t.scope.cpt.get(c) == g.scope.cpt.get(c)]
    diff = [c for c in codes if c in t.scope.cpt and c in g.scope.cpt and t.scope.cpt[c] != g.scope.cpt[c]]
    critical = [c for c in diff if "covered" in (t.scope.cpt[c], g.scope.cpt[c])]
    r["codes"] = {"truth": len(t.scope.cpt), "gen": len(g.scope.cpt), "same": len(same), "different": diff,
                  "critical": critical, "only_truth": [c for c in codes if c not in g.scope.cpt],
                  "only_gen": [c for c in codes if c not in t.scope.cpt]}

    # criteria
    m = match_criteria(t, g)
    hit = set(m.values())
    tt = {c.id: c.text for c in t.criteria}
    gt = g.criterion_map()

    def paraphrase(a: str, b: str) -> bool:      # same requirement reworded, not one merged into a larger one
        wa, wb = words(a), words(b)
        return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= 0.5
    def negates_shared(a: str, b: str) -> bool:  # a negation in `a` governs words that `b` also has
        toks = re.findall(r"[a-z0-9']+|non-", a.lower())
        wb = words(b)
        for i, tok in enumerate(toks):
            if tok in ("not", "non", "non-", "no", "without", "absence", "absent", "never", "none", "n't"):
                nxt = [x for x in toks[i + 1:i + 5] if x not in STOP]
                if any(x in wb for x in nxt[:3]):
                    return True
        return False

    def flipped(gtext: str, ttext: str) -> bool:
        if negated(gtext) == negated(ttext) or not paraphrase(gtext, ttext):
            return False
        return negates_shared(gtext, ttext) if negated(gtext) else negates_shared(ttext, gtext)
    flip = {gid for gid, tid in m.items() if flipped(gt[gid].text, tt[tid])}
    r["criteria"] = {"truth": len(t.criteria), "gen": len(g.criteria),
                     "recall": round(len(hit) / len(t.criteria), 3) if t.criteria else None,
                     "precision": round(len(m) / len(g.criteria), 3) if g.criteria else None,
                     "missed": [c.id for c in t.criteria if c.id not in hit],
                     "extra": [c.id for c in g.criteria if c.id not in m]}

    # pathways + behaviour, per code the truth covers
    rng = random.Random(7)
    per_code = {}
    tcodes = [c for c, s in t.scope.cpt.items() if s == "covered"] or [""]
    for code in tcodes:
        tp = [s for s in t.scenarios if not code or governs(t, s, code)]
        gp = [s for s in g.scenarios if not code or governs(g, s, code)]
        # a non-covered code, or a guideline marked for review, never passes
        gate_t = t.scope.cpt.get(code) in ("non_covered", "investigational") or t.status == "needs_review"
        gate_g = g.scope.cpt.get(code) in ("non_covered", "investigational") or g.status == "needs_review"
        agree = fp = ff = shared = gpass = tpass = both = 0
        tneg, gneg = parity(t), parity(g)
        unmatched_t = {c.id for c in t.criteria} - hit
        for _ in range(SAMPLES):
            p = rng.uniform(0.5, 0.97)
            # a requirement no chart can show is never judged: the app takes it as met and flags it for review
            tv = {c.id: (rng.random() < (1 - p if tneg.get(c.id) else p)) if c.answerable else True for c in t.criteria}
            gv = {c.id: True if not c.answerable else (tv[m[c.id]] != (c.id in flip)) if c.id in m
                  else rng.random() < (1 - p if gneg.get(c.id) else p) for c in g.criteria}
            dt = not gate_t and any(ev(s.requires, lambda x: tv.get(x, False)) for s in tp)
            dg = not gate_g and any(ev(s.requires, lambda x: gv.get(x, False)) for s in gp)
            agree += dt == dg
            gpass += dg
            tpass += dt
            both += dg and dt
            fp += dg and not dt
            ff += dt and not dg
            # shared logic: requirements only one side has are taken as met on that side
            tv2 = {k: True if k in unmatched_t else v for k, v in tv.items()}
            gv2 = {k: v if k in m else True for k, v in gv.items()}
            st = not gate_t and any(ev(s.requires, lambda x: tv2.get(x, False)) for s in tp)
            sg = not gate_g and any(ev(s.requires, lambda x: gv2.get(x, False)) for s in gp)
            shared += st == sg
        per_code[code or "*"] = {"truth_paths": len(tp), "gen_paths": len(gp), "agree": round(agree / SAMPLES, 3),
                                 "false_pass": round(fp / SAMPLES, 3), "false_fail": round(ff / SAMPLES, 3),
                                 "shared_logic": round(shared / SAMPLES, 3),
                                 "truth_pass_rate": round(tpass / SAMPLES, 3), "gen_pass_rate": round(gpass / SAMPLES, 3),
                                 # of the patterns the generated tree passes, the share the truth does not: wrong approvals
                                 "wrong_of_gen_passes": round(1 - both / gpass, 3) if gpass else None,
                                 # of the patterns the truth passes, the share the generated tree misses
                                 "missed_of_truth_passes": round(1 - both / tpass, 3) if tpass else None}
    r["per_code"] = per_code
    vals = list(per_code.values())
    r["behaviour"] = {k: round(sum(v[k] for v in vals) / len(vals), 3) for k in ("agree", "false_pass", "false_fail", "shared_logic",
                                                                                 "truth_pass_rate", "gen_pass_rate")}
    for k in ("wrong_of_gen_passes", "missed_of_truth_passes"):
        xs = [v[k] for v in vals if v[k] is not None]
        r["behaviour"][k] = round(sum(xs) / len(xs), 3) if xs else None
    r["behaviour"]["worst_code"] = min(per_code, key=lambda c: per_code[c]["agree"])
    if verbose:
        print(json.dumps(r, indent=1))
    return r


def line(r: dict) -> str:
    c, k, b = r["criteria"], r["codes"], r["behaviour"]
    return (f"{r['id'][:44]:44} status {r['truth_status'][:5]}/{r['gen_status'][:5]}  crit {c['truth']:>3}/{c['gen']:>3} "
            f"recall {c['recall'] or 0:.2f} prec {c['precision'] or 0:.2f}  codes {k['same']}/{len(set(k['only_truth']) | set(k['only_gen'])) + k['same'] + len(k['different'])}"
            f" critical {len(k['critical'])}  agree {b['agree']:.2f}  pass truth/gen {b['truth_pass_rate']:.2f}/{b['gen_pass_rate']:.2f}"
            f"  WRONG-of-gen-passes {_f(b['wrong_of_gen_passes'])}  missed-of-truth-passes {_f(b['missed_of_truth_passes'])}")


def _f(x) -> str:
    return "  n/a" if x is None else f"{x:.2f}"


if __name__ == "__main__":
    if sys.argv[1:2] == ["--all"]:
        legacy = [(ROOT / "data/guidelines/bcbsfl-02-33000-31.json", ROOT / "data/guidelines/generated/bcbsf-02-33000-31.json"),
                  (ROOT / "tests/fixtures/centers-for-medicare-medicaid-services-ncd-20-8-3.json", ROOT /
                   "data/guidelines/generated/centers-for-medicare-medicaid-services-national-coverage-determination-ncd-20-8-3.json")]
        for tp, gp in legacy:
            if gp.exists():
                print(line(score(tp, gp, "-v" in sys.argv)))
        alias = {"kaiser-redundant-skin-surgery": "kaiser-foundation-health-plan-of-the-mid-plastic-and-reconstructive-surgery",
                 "excellus-2-01-07": "not-stated-in-document-2-01-07"}
        for tp in sorted((ROOT / "tests/fixtures/truth").glob("*.json")):
            gp = ROOT / "data/guidelines/generated" / f"{alias.get(tp.stem, tp.stem)}.json"
            if gp.exists():
                print(line(score(tp, gp, "-v" in sys.argv)))
            else:
                print(f"{tp.stem}: no generated counterpart")
    else:
        print(line(score(Path(sys.argv[1]), Path(sys.argv[2]), "-v" in sys.argv)))
