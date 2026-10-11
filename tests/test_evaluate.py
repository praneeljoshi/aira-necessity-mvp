from app.decide.evaluate import compile_expr, leaf_ids, missing, parse, path_nodes
from app.core.models import Verdict


def v(status, conf=0.9):
    return Verdict(criterion="x", status=status, confidence=conf)


GSV = {"all": ["reflux", "size", {"any": ["ulcer", {"all": ["symptoms", "compression"]}]}]}


def test_parse_normalises_and_reports():
    p = []
    assert parse({"all": ["a"]}, {"a"}, p) == "a"
    assert parse({"at_least": {"k": 2, "of": ["a", "b", "c"]}}, {"a", "b", "c"}, p) == {"at_least": {"k": 2, "of": ["a", "b", "c"]}}
    assert not p
    parse({"all": ["a", "zz"]}, {"a"}, p)
    assert any("zz" in x for x in p)
    p = []
    assert parse({"at_least": {"k": 4, "of": ["a", "b"]}}, {"a", "b"}, p) is None and p


def test_all_any():
    vs = {"reflux": v("MET"), "size": v("MET"), "ulcer": v("INSUFFICIENT"), "symptoms": v("MET"), "compression": v("MET")}
    assert compile_expr(GSV, vs).status == "MET"
    vs["compression"] = v("INSUFFICIENT")
    n = compile_expr(GSV, vs)
    assert n.status == "INSUFFICIENT"
    assert {x.criterion for x in missing(n)} in ({"ulcer"}, {"compression"})
    vs["size"] = v("NOT_MET")
    assert compile_expr(GSV, vs).status == "NOT_MET"


def test_not():
    e = {"not": {"any": ["dvt", "reversible"]}}
    assert compile_expr(e, {"dvt": v("NOT_MET"), "reversible": v("NOT_MET")}).status == "MET"
    assert compile_expr(e, {"dvt": v("MET"), "reversible": v("NOT_MET")}).status == "NOT_MET"
    assert compile_expr(e, {"dvt": v("INSUFFICIENT"), "reversible": v("NOT_MET")}).status == "INSUFFICIENT"


def test_at_least():
    e = {"at_least": {"k": 2, "of": ["a", "b", "c"]}}
    assert compile_expr(e, {"a": v("MET"), "b": v("MET"), "c": v("NOT_MET")}).status == "MET"
    n = compile_expr(e, {"a": v("MET"), "b": v("INSUFFICIENT"), "c": v("NOT_MET")})
    assert n.status == "INSUFFICIENT"
    assert [x.criterion for x in missing(n)] == ["b"]
    assert {x.criterion for x in path_nodes(n)} == {"a", "b"}
    assert compile_expr(e, {"a": v("MET"), "b": v("NOT_MET"), "c": v("NOT_MET")}).status == "NOT_MET"


def test_conditional_shape():
    e = {"any": [{"not": "pregnant"}, "counseling"]}       # "for X, Y is required"
    assert compile_expr(e, {"pregnant": v("NOT_MET"), "counseling": v("INSUFFICIENT")}).status == "MET"
    assert compile_expr(e, {"pregnant": v("MET"), "counseling": v("INSUFFICIENT")}).status == "INSUFFICIENT"


def test_missing_verdict_is_insufficient():
    assert compile_expr("a", {}).status == "INSUFFICIENT"


def test_leaf_ids():
    assert leaf_ids(GSV) == ["reflux", "size", "ulcer", "symptoms", "compression"]


def test_not_over_a_list_names_the_items():
    from app.decide.result import _items
    e = {"not": {"any": ["reversible", "asymptomatic", "sleep"]}}
    n = compile_expr(e, {"reversible": v("NOT_MET"), "asymptomatic": v("MET"), "sleep": v("NOT_MET")})
    assert _items(n) == [(["asymptomatic"], "NOT_MET", "Must not apply: ")]
    ok = compile_expr(e, {"reversible": v("NOT_MET"), "asymptomatic": v("NOT_MET"), "sleep": v("NOT_MET")})
    assert [r[0] for r in _items(ok)] == [["reversible"], ["asymptomatic"], ["sleep"]] and {r[1] for r in _items(ok)} == {"MET"}
    single = compile_expr({"not": "dvt"}, {"dvt": v("NOT_MET")})
    assert _items(single) == [(["dvt"], "MET", "Must not apply: ")]
    compound = compile_expr({"not": {"all": ["afib", "without_symptoms"]}}, {"afib": v("NOT_MET"), "without_symptoms": v("MET")})
    assert _items(compound) == [(["afib"], "MET", "Must not apply: "), (["without_symptoms"], "NOT_MET", "Must not apply: ")]
