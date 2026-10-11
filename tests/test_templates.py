"""The surgeon ask's wording (app/decide/templates.py): each item is the guideline's words as quoted, then what is needed (no
sentence built around a quote, no lower-casing), a chart quote once per draft, and no text predicts the payer's
decision. Shipped once: "Documentation that federal Employee Program (FEP)…", "endovenous radiofrequency,." and
"Florida Blue will deny without it". Pure: no store, no model."""
from __future__ import annotations

from app.decide import templates as T
from app.core.models import Criterion, Threshold
from tests.test_pipeline import DENY, assert_no_denial

PAYER = "Florida Blue"
COMP = Criterion(id="compression", refs=["g0001"], quote="conservative management including compression therapy for at "
                 "least 3 months has not improved the symptoms", question="?", threshold=Threshold(op="gte", value=3, unit="months"))


def test_an_item_is_the_guidelines_words_then_whats_needed():
    """Each ask line is “<the guideline's words>” — <what is needed>: never 'Documentation that <quote>', never
    lower-cased (proper nouns keep their case), no ',.' left at a quote's end."""
    fep = T.request_lines(None, "Federal Employee Program (FEP): Follow FEP guidelines.", PAYER, False)[0]
    assert fep.startswith("“Federal Employee Program (FEP): Follow FEP guidelines” — ")
    for words in ("ICDs alone.", "wound care when indicated", "endovenous radiofrequency,.", "Bradycardia due to drugs;"):
        line = T.join_request(T.request_lines(None, words, PAYER, False))
        assert "Documentation that" not in line and " that “" not in line
        assert ",." not in line and ";”" not in line and ",”" not in line
    assert T.clip("endovenous radiofrequency,.") == "endovenous radiofrequency"
    dur = T.join_request(T.request_lines(COMP, COMP.quote, PAYER, True))
    assert dur.startswith("“conservative management") and "at least 3 months of wearing them" in dur
    ex = T.request_lines(None, "Bradycardia due to drugs", PAYER, False, exclusion=True)[0]
    assert ex.startswith("“Bradycardia due to drugs” (must not apply)")


def test_one_chart_quote_is_shown_once_per_draft():
    who, pat, proc = "Dr. Tran", "Robert Mitchell", "Pacemaker, 33207"
    q = T.chart_says("Heart rate 38 bpm on telemetry.")
    lines = [f"“A” — {q}.", f"“B” — {q}."]
    text = T.addendum(who, pat, proc, PAYER, lines, [], True, ["Federal Employee Program (FEP) members"])
    assert text.count("Heart rate 38 bpm on telemetry") == 1 and "says the same (quoted above)" in text
    assert "Federal Employee Program (FEP) members" in text
    text = T.addendum(who, pat, proc, PAYER, ["“A” — a note that documents it."], [q, q], False, [])
    assert text.count("Heart rate 38 bpm") == 1


def test_the_ask_never_predicts_a_denial():
    who, pat, proc = "Dr. Vasquez", "Linda Park", "Endovenous laser ablation, 36478"
    lines = [T.join_request(T.request_lines(COMP, COMP.quote, PAYER, True))]
    texts = [
        T.addendum(who, pat, proc, PAYER, lines, [], False, []),
        T.addendum(who, pat, proc, PAYER, lines, ["the chart on September 9 says “compression earlier this year”"], False, []),
        T.addendum(who, pat, proc, PAYER, lines, ["a", "b", "c"], False, []),
        T.addendum(who, pat, proc, PAYER, lines, [], True, ["CEAP class C2 or greater"]),
        T.not_covered(who, pat, proc, PAYER, "36468 as cosmetic"),
        T.which_section(who, pat, proc, PAYER, ["Great or Small Saphenous Veins", "Accessory Saphenous Veins"]),
    ] + T.request_lines(COMP, COMP.quote, PAYER, False) + T.request_lines(None, "Reflux on duplex", PAYER, False)
    for t in texts:
        assert_no_denial(t)
    # every ask ends with a plain question to the surgeon, never a prediction about the payer
    assert "Florida Blue's guideline asks for. Could you add a note that shows this?" in texts[1]
    assert "Could you add a note that shows it?" in texts[0]


def test_the_check_catches_deny_words():
    for bad in ("Florida Blue will deny without it.", "They would deny it.", "It may be denied.", "a denial", "deny"):
        assert DENY.search(bad)
    assert not DENY.search("The chart says “Denies chest pain.”")          # a chart quote's 'denies' is not ours
