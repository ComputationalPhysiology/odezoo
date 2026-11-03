import hashlib
import json
import sys
from dataclasses import replace

import pytest
from helpers import make_model, replace_version, run, write_checkout

from odezoo.maintain.check import check

BR = "models/beeler_reuter_1977"
GOOD_ODE = b"states(x=1)\nparameters(a=1)\ndx_dt = -a*x\n"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ode_model(body: bytes, **changes):
    """A model whose only version is our own .ode file, kept in the checkout"""
    model = replace_version(
        make_model(default_version=None),
        id="v1",
        format="ode",
        file="v1.ode",
        source=None,
        sha256=sha(body),
        **changes,
    )
    return model, {"v1.ode": body}


def test_clean_checkout_is_ok(checkout):
    r = check(checkout)
    assert r.ok and r.checked == 1 and r.errors == []


def test_hash_mismatch(checkout):
    (checkout / BR / "pmr-cb090c9.cellml").write_bytes(b"<x/>")
    assert any("sha256" in e and "pmr-cb090c9.cellml" in e for e in check(checkout).errors)


def test_missing_file(checkout):
    (checkout / BR / "pmr-cb090c9.cellml").unlink()
    assert any("pmr-cb090c9.cellml" in e and "missing" in e for e in check(checkout).errors)


def test_stray_file(checkout):
    (checkout / BR / "extra.txt").write_text("x")
    assert any("extra.txt" in e and "not referenced" in e for e in check(checkout).errors)


def test_licence_file_next_to_the_model_is_allowed(checkout):
    (checkout / BR / "LICENSE").write_text("Copyright (c) 2025 Someone\n")
    assert check(checkout).ok


def mit_checkout(tmp_path, *, notice: bool):
    """A checkout whose one model keeps a copy under MIT, with or without its LICENSE file"""
    model, files = ode_model(GOOD_ODE, license="MIT")
    root = write_checkout(tmp_path / "reg", [(model, files)])
    (root / "LICENSES/MIT.txt").write_text("MIT License\n")
    if notice:
        (root / BR / "LICENSE").write_text("Copyright (c) 2025 Someone\n")
    return root


def test_mit_copy_needs_its_licence_file(tmp_path):
    errors = check(mit_checkout(tmp_path, notice=False)).errors
    assert any(f"{BR}/LICENSE" in e and "copyright notice" in e for e in errors)


def test_mit_copy_with_its_licence_file_is_ok(tmp_path):
    assert check(mit_checkout(tmp_path, notice=True)).errors == []


def test_missing_licence_text(checkout):
    (checkout / "LICENSES/CC-BY-3.0.txt").unlink()
    assert any("LICENSES/CC-BY-3.0.txt" in e for e in check(checkout).errors)


@pytest.mark.parametrize(
    "body, word",
    [
        (b"<model", "XML"),
        (b'<model xmlns="http://example.org/"/>', "namespace"),
        (
            b'<model xmlns="http://www.cellml.org/cellml/1.1#"><import xlink:href="x.cellml" '
            b'xmlns:xlink="http://www.w3.org/1999/xlink"/></model>',
            "import",
        ),
    ],
)
def test_cellml_content(tmp_path, body, word):
    m = replace_version(make_model(), sha256=sha(body))
    root = write_checkout(tmp_path, [(m, {"pmr-cb090c9.cellml": body})])
    assert any(word in e for e in check(root).errors)


def test_one_broken_model_does_not_hide_others(checkout):
    bad = checkout / "models/broken"
    bad.mkdir()
    (bad / "model.toml").write_text("id = 'broken'\n")
    r = check(checkout)
    assert r.checked == 2 and len(r.errors) >= 1
    assert all(e.startswith("models/broken/") for e in r.errors)


def test_ode_without_gotranx_warns(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "gotranx", None)
    root = write_checkout(tmp_path, [ode_model(b"anything")])
    r = check(root)
    assert r.ok and [w for w in r.warnings if "gotranx not installed" in w]


def test_ode_loaded_with_gotranx(tmp_path):
    pytest.importorskip("gotranx")
    assert check(write_checkout(tmp_path / "good", [ode_model(GOOD_ODE)])).ok
    bad = check(write_checkout(tmp_path / "bad", [ode_model(b"dx_dt = ")]))
    assert any("v1.ode" in e and "gotranx" in e for e in bad.errors)


def test_derived_licence_differs_warns(tmp_path):
    base = make_model()
    own = replace(
        base.versions[0],
        id="v1",
        format="ode",
        file="v1.ode",
        source=None,
        sha256=sha(GOOD_ODE),
        license="MIT",
        derived_from="pmr-cb090c9",
    )
    model = replace(base, versions=(base.versions[0], own))
    from helpers import CELLML_BYTES

    root = write_checkout(
        tmp_path, [(model, {"pmr-cb090c9.cellml": CELLML_BYTES, "v1.ode": GOOD_ODE})]
    )
    (root / "LICENSES/MIT.txt").write_text("MIT")
    r = check(root)
    assert any("v1" in w and "MIT" in w and "CC-BY-3.0" in w for w in r.warnings)


def test_unknown_id(checkout):
    assert any("nope" in e for e in check(checkout, ["nope"]).errors)


def test_only_the_named_models_are_checked(checkout):
    bad = checkout / "models/broken"
    bad.mkdir()
    (bad / "model.toml").write_text("id = 'broken'\n")
    r = check(checkout, ["beeler_reuter_1977"])
    assert r.ok and r.checked == 1


def test_cli_check_and_build(capsys, checkout, tmp_path, monkeypatch):
    code, out, _ = run(capsys, "--registry", str(checkout), "registry", "check")
    assert code == 0 and "1 models checked, 0 errors, 0 warnings" in out
    monkeypatch.setenv("ODEZOO_REGISTRY_COMMIT", "b" * 40)
    run(capsys, "--registry", str(checkout), "registry", "build", "-o", str(tmp_path / "r.json"))
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["commit"] == "b" * 40 and data["models"][0]["id"] == "beeler_reuter_1977"


def test_cli_check_fails_on_errors(capsys, checkout):
    (checkout / BR / "extra.txt").write_text("x")
    code, out, _ = run(capsys, "--registry", str(checkout), "registry", "check")
    assert code == 1 and "not referenced" in out


def test_cli_registry_commands_need_a_checkout(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, _, err = run(capsys, "registry", "check")
    assert code == 1 and "models/" in err
