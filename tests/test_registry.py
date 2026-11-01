import json
import re
import subprocess
import sys
import zipfile
from datetime import date

import pytest
from helpers import REPO, write_checkout

import odezoo.registry
from odezoo.errors import ModelNotFound, RegistryError
from odezoo.registry import (
    MIRROR_BASE,
    build,
    from_json,
    load,
    load_checkout,
    resolve_commit,
)


def test_load_checkout(checkout):
    reg = load_checkout(checkout)
    assert list(reg.models) == ["beeler_reuter_1977"]
    assert reg.root == checkout and reg.commit is None


def test_folder_must_match_id(checkout):
    (checkout / "models/beeler_reuter_1977").rename(checkout / "models/other")
    with pytest.raises(RegistryError, match="other"):
        load_checkout(checkout)


def test_missing_models_folder(tmp_path):
    with pytest.raises(RegistryError, match="models"):
        load_checkout(tmp_path)


def test_build_and_from_json_round_trip(checkout):
    data = build(checkout, commit="a" * 40, built=date(2026, 11, 1))
    assert (data["schema"], data["commit"], data["built"]) == (1, "a" * 40, "2026-11-01")
    reg = from_json(json.loads(json.dumps(data)))
    assert reg.models == load_checkout(checkout).models
    assert reg.root is None and reg.mirror_base == MIRROR_BASE


def test_from_json_rejects_unknown_schema():
    with pytest.raises(RegistryError, match="schema"):
        from_json({"schema": 2, "commit": None, "built": "2026-11-01", "models": []})


def test_load_precedence(checkout, tmp_path, monkeypatch):
    other = write_checkout(tmp_path / "other", [])
    monkeypatch.setenv("ODEZOO_REGISTRY", str(checkout))
    assert load().root == checkout
    assert load(other).root == other
    monkeypatch.delenv("ODEZOO_REGISTRY")
    monkeypatch.setattr(odezoo.registry, "bundled_path", lambda: tmp_path / "missing.json")
    with pytest.raises(RegistryError, match="--registry"):
        load()


def test_get_ignores_case_and_suggests(checkout):
    reg = load_checkout(checkout)
    assert reg.get(" Beeler_Reuter_1977 ").id == "beeler_reuter_1977"
    with pytest.raises(ModelNotFound) as e:
        reg.get("beeler_reuter_1978")
    assert e.value.suggestions == ["beeler_reuter_1977"] and "did you mean" in str(e.value)


def test_resolve_commit(tmp_path):
    assert resolve_commit(tmp_path) is None
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t"]
        + ["commit", "-q", "--allow-empty", "-m", "x"],
        check=True,
    )
    commit = resolve_commit(tmp_path)
    assert commit is not None and re.fullmatch(r"[0-9a-f]{40}", commit)


def test_wheel_bundles_registry_and_no_model_files(tmp_path, monkeypatch):
    monkeypatch.delenv("ODEZOO_REGISTRY_COMMIT", raising=False)
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", str(REPO), "--no-deps", "--no-build-isolation"]
        + ["-q", "-w", str(tmp_path)],
        check=True,
    )
    with zipfile.ZipFile(next(tmp_path.glob("odezoo-*.whl"))) as wheel:
        names = wheel.namelist()
        data = json.loads(wheel.read("odezoo/registry.json"))
    assert not [n for n in names if n.endswith((".cellml", ".ode", ".toml"))]
    assert data["commit"] == resolve_commit(REPO)
