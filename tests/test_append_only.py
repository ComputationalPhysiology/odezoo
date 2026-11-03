import pytest
from helpers import CELLML_SHA, run

from odezoo.maintain.append_only import append_only_problems

V0 = {
    "id": "pmr-cb090c9",
    "format": "cellml",
    "sha256": "a" * 64,
    "license": "CC-BY-3.0",
    "file": "pmr-cb090c9.cellml",
    "added": "2026-11-01",
}
V1 = {
    "id": "v1",
    "format": "ode",
    "sha256": "b" * 64,
    "license": "CC-BY-3.0",
    "file": "v1.ode",
    "added": "2027-01-15",
}


def doc(*versions, models=("beeler_reuter_1977",)):
    """A registry.json document whose models each hold `versions`"""
    return {"schema": 1, "models": [{"id": m, "versions": list(versions)} for m in models]}


def test_adding_a_version_is_fine():
    assert append_only_problems(doc(V0), doc(V0, V1)) == []


def test_adding_a_model_is_fine():
    assert append_only_problems(doc(V0), doc(V0, models=("beeler_reuter_1977", "noble"))) == []


def test_correcting_licence_and_notes_is_fine():
    corrected = {**V1, "license": "MIT", "notes": "Units in ms"}
    assert append_only_problems(doc(V0, V1), doc(V0, corrected)) == []


def test_removing_a_version():
    assert append_only_problems(doc(V0, V1), doc(V0)) == ["beeler_reuter_1977 v1: removed"]


def test_removing_a_model():
    assert append_only_problems(doc(V0, V1), doc(V0, models=())) == [
        "beeler_reuter_1977 pmr-cb090c9: removed",
        "beeler_reuter_1977 v1: removed",
    ]


@pytest.mark.parametrize("field", ["format", "sha256", "file"])
def test_changing_a_frozen_field(field):
    changed = {**V1, field: "c" * 64 if field == "sha256" else "cellml"}
    assert append_only_problems(doc(V0, V1), doc(V0, changed)) == [
        f"beeler_reuter_1977 v1: {field} changed"
    ]


def test_dropping_the_copy_is_a_change():
    without_file = {key: value for key, value in V1.items() if key != "file"}
    assert append_only_problems(doc(V1), doc(without_file)) == [
        "beeler_reuter_1977 v1: file changed"
    ]


def test_cli_check_against(capsys, checkout, tmp_path):
    old = str(tmp_path / "old.json")
    assert run(capsys, "--registry", str(checkout), "registry", "build", "-o", old)[0] == 0
    assert run(capsys, "--registry", str(checkout), "registry", "check", "--against", old)[0] == 0
    toml = checkout / "models/beeler_reuter_1977/model.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace(CELLML_SHA, "0" * 64), "utf-8")
    code, out, _ = run(capsys, "--registry", str(checkout), "registry", "check", "--against", old)
    assert code == 1 and "beeler_reuter_1977 pmr-cb090c9: sha256 changed" in out


@pytest.mark.parametrize("content", ["not json", '{"schema": 2, "models": []}'])
def test_cli_check_against_a_bad_file(capsys, checkout, tmp_path, content):
    old = tmp_path / "old.json"
    old.write_text(content, encoding="utf-8")
    code, _, err = run(capsys, "--registry", str(checkout), "registry", "check", "--against",
                       str(old))  # fmt: skip
    assert code == 1 and "old.json" in err and len(err.strip().splitlines()) == 1
