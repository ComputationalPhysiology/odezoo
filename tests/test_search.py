from search_models import ALL, br, ids, tt, wk

from odezoo.search import search


def test_no_filters_returns_all_sorted():
    assert ids(search([wk, tt, br])) == [
        "beeler_reuter_1977",
        "tentusscher_2006_epi",
        "windkessel_2000",
    ]


def test_text_every_word_any_field():
    assert ids(search(ALL, "TUSSCHER panfilov")) == ["tentusscher_2006_epi"]


def test_text_all_words_must_match():
    assert search(ALL, "tusscher beeler") == []


def test_category_or_within():
    found = search(ALL, category=["calcium_dynamics", "cardiovascular_circulation"])
    assert ids(found) == ["tentusscher_2006_epi", "windkessel_2000"]


def test_filters_and_across():
    found = search(ALL, category="electrophysiology", species="human")
    assert ids(found) == ["tentusscher_2006_epi"]


def test_keyword_is_normalized():
    assert ids(search(ALL, keyword="Ventricular  Myocyte")) == ["beeler_reuter_1977"]


def test_format():
    assert ids(search(ALL, format="ode")) == ["tentusscher_2006_epi", "windkessel_2000"]


def test_reviewed():
    assert ids(search(ALL, reviewed=False)) == ["tentusscher_2006_epi"]
