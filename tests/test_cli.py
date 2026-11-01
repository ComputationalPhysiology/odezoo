import json

import pytest
from helpers import run

from odezoo.cli import main


def test_help_exits_0():
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0


def test_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == "odezoo 0.1.0"


def test_no_command_prints_help_and_returns_2(capsys):
    assert run(capsys)[0] == 2


def test_bad_choice_is_usage_error():
    with pytest.raises(SystemExit) as e:
        main(["search", "--format", "mmt"])
    assert e.value.code == 2


def test_search_table(capsys, checkout):
    code, out, _ = run(capsys, "--registry", str(checkout), "search")
    assert code == 0 and "beeler_reuter_1977" in out
    assert "1977" in out and "electrophysiology" in out
    assert "\x1b[" not in out


def test_global_option_after_command(capsys, checkout):
    assert run(capsys, "search", "--registry", str(checkout), "--ids")[1] == "beeler_reuter_1977\n"


def test_search_json(capsys, checkout):
    out = run(capsys, "--registry", str(checkout), "search", "--json")[1]
    assert json.loads(out)[0]["id"] == "beeler_reuter_1977"


def test_search_filters(capsys, checkout):
    found = run(capsys, "--registry", str(checkout), "search", "--category", "electrophysiology",
                "--format", "cellml", "--reviewed", "--ids")[1]  # fmt: skip
    assert found == "beeler_reuter_1977\n"
    assert run(capsys, "--registry", str(checkout), "search", "--unreviewed", "--ids")[1] == ""


def test_search_no_match(capsys, checkout):
    code, out, err = run(capsys, "--registry", str(checkout), "search", "zzz")
    assert code == 0 and out == "" and "No models match" in err


def test_info(capsys, checkout):
    code, out, _ = run(capsys, "--registry", str(checkout), "info", "beeler_reuter_1977")
    assert code == 0 and "https://doi.org/10.1113/jphysiol.1977.sp011853" in out
    assert "pmr-cb090c9" in out and "CC-BY-3.0" in out
    assert "\x1b[" not in out


def test_info_json(capsys, checkout):
    out = run(capsys, "--registry", str(checkout), "info", "beeler_reuter_1977", "--json")[1]
    assert json.loads(out)["paper"]["pubmed"] == 874889


def test_info_unknown_suggests(capsys, checkout):
    code, _, err = run(capsys, "--registry", str(checkout), "info", "beeler_reuter_1978")
    assert code == 1 and "did you mean" in err and "beeler_reuter_1977" in err
