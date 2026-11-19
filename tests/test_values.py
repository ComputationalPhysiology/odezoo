import json

import pytest
from helpers import CELLML_BYTES, make_model, run, write_checkout

from odezoo.cli import main


@pytest.fixture
def family(tmp_path):
    """A checkout with Beeler–Reuter and two ten Tusscher variants of one family"""
    files = {"pmr-cb090c9.cellml": CELLML_BYTES}
    variants = [
        make_model(
            id=f"tentusscher_2006_{v}",
            name=f"ten Tusscher 2006 {v}",
            species="human",
            family="tentusscher_2006",
        )  # fmt: skip
        for v in ("endo", "epi")
    ]
    models = [(make_model(), files), *((m, files) for m in variants)]
    return str(write_checkout(tmp_path / "reg", models))


def test_values_lists_each_species_with_its_count(capsys, family):
    code, out, _ = run(capsys, "--registry", family, "values", "species")
    assert code == 0
    rows = [[w for w in line.split() if w.isalnum()] for line in out.splitlines()]
    counted = [r for r in rows if r[:1] in (["human"], ["canine"])]
    assert counted == [["human", "2"], ["canine", "1"]]  # the most common first


def test_values_json_and_filters(capsys, family):
    out = run(capsys, "--registry", family, "values", "family", "--json")[1]
    assert json.loads(out) == {"tentusscher_2006": 2}
    out = run(capsys, "--registry", family, "values", "species", "--species", "canine", "--json")[1]
    assert json.loads(out) == {"canine": 1}


def test_values_with_nothing_to_count(capsys, family):
    code, out, err = run(capsys, "--registry", family, "values", "species", "--species", "sheep")
    assert code == 0 and out == "" and "No models match" in err


def test_values_needs_a_known_field(capsys):
    with pytest.raises(SystemExit) as e:
        main(["values", "colour"])
    assert e.value.code == 2


def test_list_filters_by_family(capsys, family):
    out = run(capsys, "--registry", family, "list", "--family", "tentusscher_2006", "--ids")[1]
    assert out == "tentusscher_2006_endo\ntentusscher_2006_epi\n"


def test_info_names_the_rest_of_the_family(capsys, family):
    out = run(capsys, "--registry", family, "info", "tentusscher_2006_epi")[1]
    assert "tentusscher_2006_endo" in out


def test_info_of_a_model_without_a_family(capsys, family):
    out = run(capsys, "--registry", family, "info", "beeler_reuter_1977")[1]
    assert "Family" not in out
