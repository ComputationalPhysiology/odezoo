import io
import json
import os
import sys

import pytest
from helpers import CELLML_BYTES, make_model, run, write_checkout
from rich.console import Console
from rich.pager import SystemPager

from odezoo.cli import main
from odezoo.render import print_models


@pytest.fixture
def two_models(tmp_path):
    """A checkout with Beeler–Reuter and an unreviewed sheep model in another category"""
    other = make_model(
        id="noble_1962",
        name="Noble 1962",
        categories=["cardiovascular_circulation"],
        species="sheep",
        reviewed=False,
    )
    files = {"pmr-cb090c9.cellml": CELLML_BYTES}
    return str(write_checkout(tmp_path / "reg", [(make_model(), files), (other, files)]))


def test_list_shows_every_model(capsys, two_models):
    code, out, _ = run(capsys, "--registry", two_models, "list")
    assert code == 0 and "beeler_reuter_1977" in out and "noble_1962" in out


def test_list_takes_the_filters(capsys, two_models):
    assert run(capsys, "--registry", two_models, "list", "--unreviewed", "--ids")[1] == (
        "noble_1962\n"
    )
    filters = ["--category", "electrophysiology", "--species", "canine", "--format", "cellml"]
    found = run(
        capsys, "--registry", two_models, "list", *filters, "--keyword", "cardiac", "--ids"
    )[1]
    assert found == "beeler_reuter_1977\n"
    out = run(capsys, "--registry", two_models, "list", "--species", "sheep", "--json")[1]
    assert [m["id"] for m in json.loads(out)] == ["noble_1962"]


def test_list_takes_no_text():
    with pytest.raises(SystemExit) as e:
        main(["list", "noble"])
    assert e.value.code == 2


def test_help_points_newcomers_to_list(capsys):
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "odezoo list" in capsys.readouterr().out


@pytest.mark.parametrize("command", ["list", "search"])
def test_no_pager_is_accepted(capsys, two_models, command):
    assert run(capsys, "--registry", two_models, command, "--no-pager")[0] == 0


# --- Paging -----------------------------------------------------------------------------------


@pytest.fixture
def shown(monkeypatch):
    """What the system pager was given to show; nothing is run"""
    pages: list[str] = []
    monkeypatch.setattr(SystemPager, "show", lambda self, content: pages.append(content))
    return pages


def terminal(height: int) -> Console:
    return Console(
        file=io.StringIO(), force_terminal=True, color_system="standard", width=100, height=height
    )


def test_a_table_taller_than_the_terminal_is_paged(shown):
    out = terminal(height=3)
    print_models([make_model()], out)
    assert len(shown) == 1 and "beeler_reuter_1977" in shown[0]
    assert out.file.getvalue() == ""


def test_a_table_that_fits_is_printed(shown):
    out = terminal(height=100)
    print_models([make_model()], out)
    assert shown == [] and "beeler_reuter_1977" in out.file.getvalue()


def test_paging_can_be_turned_off(shown):
    out = terminal(height=3)
    print_models([make_model()], out, pager=False)
    assert shown == [] and "beeler_reuter_1977" in out.file.getvalue()


def test_output_that_is_not_a_terminal_is_never_paged(shown):
    out = Console(file=io.StringIO(), height=3)
    print_models([make_model()], out)
    assert shown == [] and "beeler_reuter_1977" in out.file.getvalue()


def test_paged_table_keeps_its_colours(shown, monkeypatch):
    out = terminal(height=3)
    monkeypatch.setattr(sys, "platform", "linux")  # anywhere but Windows (next test)
    print_models([make_model()], out)
    assert "\x1b[" in shown[0]


def test_paged_table_is_plain_on_windows(shown, monkeypatch):
    # Windows' pager, more, prints colour codes as text.
    monkeypatch.setattr(sys, "platform", "win32")
    print_models([make_model()], terminal(height=3))
    assert "\x1b[" not in shown[0]


def test_less_is_told_to_show_colours(shown, monkeypatch):
    monkeypatch.setenv("LESS", "")  # so that monkeypatch restores LESS however the test ends
    monkeypatch.delenv("LESS")
    print_models([make_model()], terminal(height=3))
    assert os.environ["LESS"] == "FRX"


def test_less_options_of_the_user_are_kept(shown, monkeypatch):
    monkeypatch.setenv("LESS", "-S")
    print_models([make_model()], terminal(height=3))
    assert os.environ["LESS"] == "-S"
