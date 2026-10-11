"""Step A: lines are spans, verbatim; blank lines and page breaks are rendered but not citable; ranges expand."""
from app.models import Range, Span
from app.narrow import code_in
from app.spans import expand, in_range, render_chart, render_guideline, resolves, split_chart, split_guideline, table, text_of
from tests.conftest import rng, sid
from tests.fake import codes_of


def test_lines_are_spans_verbatim_with_indent():
    spans = split_guideline("Heading\n   •   bullet one\n\tcontinued   \n")
    assert [s.id for s in spans] == ["g0001", "g0002", "g0003"]
    assert [s.text for s in spans] == ["Heading", "   •   bullet one", "    continued"]   # tab -> 4 spaces, trailing stripped
    assert all(s.page == 1 and not s.blank_before for s in spans)


def test_blank_lines_are_not_spans_but_render_as_one_empty_line():
    spans = split_chart("a\n\n\n   b\nc\n")
    assert [s.text for s in spans] == ["a", "   b", "c"]
    assert [s.blank_before for s in spans] == [False, True, False]
    assert render_chart(spans) == "--- page 1 ---\n[r0001] a\n\n[r0002]    b\n[r0003] c"


def test_page_markers_render_but_cannot_be_cited():
    spans = split_guideline("one\n\ftwo\n\f\n\f  three")
    assert [(s.text, s.page) for s in spans] == [("one", 1), ("two", 2), ("  three", 4)]
    out = render_guideline(spans)
    assert "--- page 1 ---\n[g0001] one\n--- page 2 ---\n[g0002] two\n--- page 4 ---\n[g0003]   three" == out
    tbl = table(spans)
    assert not resolves("--- page 2 ---", tbl) and not any("--- page" in s.text for s in spans)


def test_ids_zero_padded_to_the_width_needed():
    assert split_chart("\n".join("x" for _ in range(12000)))[-1].id == "r12000"
    assert split_chart("x\ny")[0].id == "r0001"


def test_fl_one_span_per_nonblank_line(fl_text, fl_spans):
    from app.spans import GLYPHS
    lines = [ln.replace("\t", "    ").rstrip() for ln in fl_text.translate(GLYPHS).replace("\f", "\n").split("\n")]
    assert [s.text for s in fl_spans] == [ln for ln in lines if ln]
    assert fl_spans[0].id == "g0001"


def test_expand_ranges_and_text_of_joins_stripped(fl_spans):
    a, b = fl_spans[10].id, fl_spans[13].id
    assert expand([f"{a}-{b}"], fl_spans) == [s.id for s in fl_spans[10:14]]
    assert expand([f"{b}–{a}"], fl_spans) == [s.id for s in fl_spans[10:14]]          # en dash, either order
    assert expand(["g9999", f"{a}-g9999"], fl_spans) == ["g9999", f"{a}-g9999"]      # unknown kept for the checks
    assert [s.id for s in in_range(fl_spans, Range(first=a, last=b))] == [s.id for s in fl_spans[10:14]]
    assert in_range(fl_spans, Range(first=b, last=a)) == []
    tbl = table(fl_spans)
    r = rng(fl_spans, "There is demonstrated saphenous reflux", "class C2* or greater")
    joined = text_of([r], tbl)       # two lines, each stripped of its indent, one space between
    assert joined.startswith("•   There is demonstrated saphenous reflux and CEAP") and \
        joined.endswith("(Clinical-Etiology-Anatomy-Pathophysiology) class C2* or greater; AND")
    assert resolves(r, tbl) and not resolves("g9999", tbl) and not resolves(f"{a}-g9999", tbl)


def test_range_citation_for_a_code_row_passes_code_in(fl_spans):
    tbl = table(fl_spans)
    rows = {c["code"]: c for c in codes_of(fl_spans)}
    row = rows["36473"]                      # "(Investigational)" sits on the row's third line
    assert "-" in row["refs"][0] and row["tag"] == "investigational"
    assert code_in("36473", text_of(row["refs"], tbl))
    assert not code_in("36473", text_of(expand(row["refs"], tbl)[1:], tbl))
    assert rows["36468"]["tag"] == "non_covered" and rows["36475"]["tag"] == "covered"


def test_render_keeps_the_line_as_extracted(fl_spans):
    out = render_guideline(fl_spans)
    item = sid(fl_spans, "1. Ulceration secondary to venous stasis")
    assert f"[{item}]        1. Ulceration secondary to venous stasis; OR" in out
    assert "--- page 2 ---" in out


def test_chart_lines_keep_layout(delgado_spans):
    heading = next(s for s in delgado_spans if s.text.startswith("Visit Date: March 18, 2025"))
    assert heading.id.startswith("r")
    row = next(s for s in delgado_spans if "Plan Type" in s.text)
    assert "   Plan Type" in row.text and "PPO" in row.text and "|" not in row.text


def test_manual_spans_default_page_and_gap():
    s = Span(id="r1", text="x")
    assert s.page == 1 and not s.blank_before


def test_private_use_bullets_map_one_for_one():
    from app.spans import unmapped_glyphs
    raw = "      reflux\n         lavage\n odd"
    spans = split_guideline(raw)
    assert [s.text for s in spans] == ["   •   reflux", "      ▪   lavage", " odd"]
    assert [len(s.text) for s in spans] == [len(x) for x in raw.split("\n")]     # indent and length unchanged
    assert unmapped_glyphs(raw) == {"U+F0BF": 1}


def test_fl_bullets_are_real_bullets(fl_spans):
    s = next(x for x in fl_spans if "There is demonstrated saphenous reflux" in x.text)
    assert s.text.lstrip().startswith("•") and "" not in s.text
