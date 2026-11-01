"""The registry: every model, from a checkout or from the `registry.json` bundled in a release"""

from __future__ import annotations

import difflib
import json
import os
import subprocess
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from odezoo.errors import ModelNotFound, RegistryError
from odezoo.schema import GIT_COMMIT, Model, model_to_dict, parse_model

MIRROR_BASE = "https://raw.githubusercontent.com/ComputationalPhysiology/odezoo"
SCHEMA_VERSION = 1
ENV_VAR = "ODEZOO_REGISTRY"


@dataclass(frozen=True)
class Registry:
    models: Mapping[str, Model]
    commit: str | None = None  # the registry commit the mirror URLs are pinned to
    root: Path | None = None  # set for a checkout, whose files are read from disk
    mirror_base: str = MIRROR_BASE

    def get(self, id: str) -> Model:
        """The model `id`, also when typed with other capitals or surrounding spaces"""
        if id in self.models:
            return self.models[id]
        key = id.strip().lower()
        if key in self.models:
            return self.models[key]
        raise ModelNotFound(id, difflib.get_close_matches(key, list(self.models), n=3))


def read_model(folder: Path) -> Model:
    """Parse `folder/model.toml` and check that the folder is named after the model's id"""
    where = f"models/{folder.name}/model.toml"
    try:
        data = tomllib.loads((folder / "model.toml").read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise RegistryError(f"not valid TOML: {e}", where=where) from None
    model = parse_model(data, where=where)
    if model.id != folder.name:
        raise RegistryError(
            f"the folder is named {folder.name!r} but the id is {model.id!r}",
            where=where,
            field="id",
        )
    return model


def load_checkout(root: Path) -> Registry:
    root = Path(root)
    if not (root / "models").is_dir():
        raise RegistryError(f"{root} has no models/ folder, so it is not a registry checkout")
    models = {}
    for toml in sorted((root / "models").glob("*/model.toml")):
        model = read_model(toml.parent)
        models[model.id] = model
    return Registry(models=models, commit=None, root=root)


def bundled_path() -> Path:
    return Path(__file__).parent / "registry.json"


def load_bundled() -> Registry:
    path = bundled_path()
    if not path.is_file():
        raise RegistryError(
            "this installation of odezoo has no bundled registry.json; "
            f"pass --registry PATH or set {ENV_VAR} to a registry checkout"
        )
    return from_json(json.loads(path.read_text(encoding="utf-8")))


def load(registry: Path | str | None = None) -> Registry:
    """The registry at `registry`, else at $ODEZOO_REGISTRY, else the one bundled in odezoo"""
    if registry is None:
        registry = os.environ.get(ENV_VAR) or None
    if registry is not None:
        return load_checkout(Path(registry))
    return load_bundled()


def build(root: Path, *, commit: str | None, built: date) -> dict[str, Any]:
    """The `registry.json` document for the checkout at `root`"""
    registry = load_checkout(root)
    return {
        "schema": SCHEMA_VERSION,
        "commit": commit,
        "built": built.isoformat(),
        "models": [model_to_dict(registry.models[id]) for id in sorted(registry.models)],
    }


def from_json(data: Mapping[str, Any]) -> Registry:
    if data.get("schema") != SCHEMA_VERSION:
        raise RegistryError(
            f"registry.json has schema {data.get('schema')!r} and this odezoo reads schema "
            f"{SCHEMA_VERSION}; install a matching version of odezoo"
        )
    models = {}
    for item in data.get("models", []):
        model = parse_model(item, where=f"registry.json: {item.get('id', '?')}")
        models[model.id] = model
    return Registry(models=models, commit=data.get("commit"), root=None)


def resolve_commit(root: Path) -> str | None:
    """The commit checked out at `root`, or None if that cannot be found out"""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip()
    return commit if out.returncode == 0 and GIT_COMMIT.match(commit) else None
