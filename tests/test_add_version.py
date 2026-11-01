from datetime import date

import pytest
from helpers import run

from odezoo.errors import RegistryError
from odezoo.maintain.version import add_version
from odezoo.registry import load_checkout

BR = "models/beeler_reuter_1977"


def test_adds_v1_then_v2(checkout, tmp_path):
    src = tmp_path / "br.ode"
    src.write_bytes(b"states(V=-84)\n")
    v = add_version(checkout, "beeler_reuter_1977", src, derived_from="pmr-cb090c9",
                    notes="Units in ms", today=date(2027, 1, 15))  # fmt: skip
    assert (v.id, v.file, v.format, v.license) == ("v1", "v1.ode", "ode", "CC-BY-3.0")
    assert (v.added, v.notes, v.derived_from) == (date(2027, 1, 15), "Units in ms", "pmr-cb090c9")
    m = load_checkout(checkout).get("beeler_reuter_1977")
    assert [x.id for x in m.versions] == ["pmr-cb090c9", "v1"]
    assert (checkout / BR / "v1.ode").read_bytes() == b"states(V=-84)\n"
    assert add_version(checkout, "beeler_reuter_1977", src, derived_from="v1").id == "v2"


def test_licence_can_be_given(checkout, tmp_path):
    src = tmp_path / "br.ode"
    src.write_bytes(b"x")
    v = add_version(checkout, "beeler_reuter_1977", src, derived_from="pmr-cb090c9", license="MIT")
    assert load_checkout(checkout).get("beeler_reuter_1977").version(v.id).license == "MIT"


@pytest.mark.parametrize(
    "changes",
    [{"derived_from": "nope"}, {"derived_from": "pmr-cb090c9", "license": "unknown"}],
)
def test_a_bad_version_changes_nothing(checkout, tmp_path, changes):
    before = (checkout / BR / "model.toml").read_text()
    src = tmp_path / "br.ode"
    src.write_bytes(b"x")
    with pytest.raises(RegistryError):
        add_version(checkout, "beeler_reuter_1977", src, **changes)
    assert (checkout / BR / "model.toml").read_text() == before
    assert not (checkout / BR / "v1.ode").exists()


def test_unknown_suffix(checkout, tmp_path):
    src = tmp_path / "br.mmt"
    src.write_bytes(b"x")
    with pytest.raises(RegistryError, match="mmt"):
        add_version(checkout, "beeler_reuter_1977", src, derived_from="pmr-cb090c9")


def test_cli_add_version(capsys, checkout, tmp_path):
    src = tmp_path / "br.ode"
    src.write_bytes(b"x")
    code, out, _ = run(capsys, "--registry", str(checkout), "registry", "add", "version",
                       "beeler_reuter_1977", str(src), "--derived-from", "pmr-cb090c9")  # fmt: skip
    assert code == 0 and "Added beeler_reuter_1977 v1 (ode)" in out


def test_existing_file_is_never_overwritten(checkout, tmp_path):
    (checkout / BR / "v1.ode").write_bytes(b"someone's work")
    src = tmp_path / "br.ode"
    src.write_bytes(b"x")
    with pytest.raises(RegistryError, match="v1.ode"):
        add_version(checkout, "beeler_reuter_1977", src, derived_from="pmr-cb090c9")
    assert (checkout / BR / "v1.ode").read_bytes() == b"someone's work"


def test_unknown_parent_is_named(checkout, tmp_path):
    src = tmp_path / "br.ode"
    src.write_bytes(b"x")
    with pytest.raises(RegistryError, match="nope"):
        add_version(checkout, "beeler_reuter_1977", src, derived_from="nope")
