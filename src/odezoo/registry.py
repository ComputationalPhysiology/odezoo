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

from .errors import ModelNotFound, RegistryError
from .schema import GIT_COMMIT, Model, model_to_dict, parse_model

MIRROR_BASE = "https://raw.githubusercontent.com/ComputationalPhysiology/odezoo"
SCHEMA_VERSION = 1
ENV_VAR = "ODEZOO_REGISTRY"


@dataclass(frozen=True)
class Registry:
    """A set of models, and where their files can be found

    Attributes
    ----------
    models : Mapping[str, Model]
        The models, by id
    commit : str | None
        The registry commit the mirror URLs are pinned to; None for a checkout
    root : Path | None
        The checkout the models were read from, whose files are read from disk; None for the
        bundled registry
    mirror_base : str
        The mirror's URL without the commit, by default this repository on GitHub
    """

    models: Mapping[str, Model]
    commit: str | None = None  # the registry commit the mirror URLs are pinned to
    root: Path | None = None  # set for a checkout, whose files are read from disk
    mirror_base: str = MIRROR_BASE

    def get(self, id: str) -> Model:
        """Return the model `id`, also when typed with other capitals or surrounding spaces

        Parameters
        ----------
        id : str
            The model's id

        Returns
        -------
        Model
            The model

        Raises
        ------
        ModelNotFound
            If no model has that id; it suggests up to three similar ones
        """
        if id in self.models:
            return self.models[id]
        key = id.strip().lower()
        if key in self.models:
            return self.models[key]
        raise ModelNotFound(id, difflib.get_close_matches(key, list(self.models), n=3))


def read_model(folder: Path) -> Model:
    """Parse `folder/model.toml` and check that the folder is named after the model's id

    Parameters
    ----------
    folder : Path
        A model's folder in a checkout, `models/<id>`

    Returns
    -------
    Model
        The model

    Raises
    ------
    RegistryError
        If `model.toml` is not valid TOML, breaks a rule of the schema, or has another id than
        the folder's name
    """
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
    """Read every model in a registry checkout

    Parameters
    ----------
    root : Path
        The checkout: a folder with a `models/` folder in it

    Returns
    -------
    Registry
        The models, with `root` set so that their files are read from the checkout

    Raises
    ------
    RegistryError
        If `root` has no `models/` folder, or a model in it is not valid
    """
    root = Path(root)
    if not (root / "models").is_dir():
        raise RegistryError(f"{root} has no models/ folder, so it is not a registry checkout")
    models = {}
    for toml in sorted((root / "models").glob("*/model.toml")):
        model = read_model(toml.parent)
        models[model.id] = model
    return Registry(models=models, commit=None, root=root)


def bundled_path() -> Path:
    """Return where the `registry.json` bundled with the package is

    Returns
    -------
    Path
        `registry.json` next to this module, which the build hook writes; a source tree that
        was never built or installed has none
    """
    return Path(__file__).parent / "registry.json"


def load_bundled() -> Registry:
    """Load the registry bundled with the package

    Returns
    -------
    Registry
        The models, with the commit the registry was built from

    Raises
    ------
    RegistryError
        If there is no bundled `registry.json`, or it is not valid for this version of odezoo
    """
    path = bundled_path()
    if not path.is_file():
        raise RegistryError(
            "this installation of odezoo has no bundled registry.json; "
            f"pass --registry PATH or set {ENV_VAR} to a registry checkout"
        )
    return from_json(json.loads(path.read_text(encoding="utf-8")))


def load(registry: Path | str | None = None) -> Registry:
    """Load the registry at `registry`, else at $ODEZOO_REGISTRY, else the one bundled in odezoo

    Parameters
    ----------
    registry : Path | str, optional
        A registry checkout to use instead of the bundled registry

    Returns
    -------
    Registry
        The registry

    Raises
    ------
    RegistryError
        If the checkout or the bundled registry cannot be read
    """
    if registry is None:
        registry = os.environ.get(ENV_VAR) or None
    if registry is not None:
        return load_checkout(Path(registry))
    return load_bundled()


def build(root: Path, *, commit: str | None, built: date) -> dict[str, Any]:
    """Make the `registry.json` document for the checkout at `root`

    Parameters
    ----------
    root : Path
        A registry checkout
    commit : str | None
        The commit the mirror URLs are pinned to; None if it is not known
    built : date
        The day of the build

    Returns
    -------
    dict[str, Any]
        The document: the schema version, `commit`, `built`, and every model in its JSON form,
        sorted by id

    Raises
    ------
    RegistryError
        If the checkout is not valid
    """
    registry = load_checkout(root)
    return {
        "schema": SCHEMA_VERSION,
        "commit": commit,
        "built": built.isoformat(),
        "models": [model_to_dict(registry.models[id]) for id in sorted(registry.models)],
    }


def from_json(data: Mapping[str, Any]) -> Registry:
    """Read a `registry.json` document

    Parameters
    ----------
    data : Mapping[str, Any]
        The parsed document, as `build` makes it

    Returns
    -------
    Registry
        The models, with the commit the document was built from

    Raises
    ------
    RegistryError
        If the document has another schema version, or a model in it is not valid
    """
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
    """Find the commit checked out at `root`

    Parameters
    ----------
    root : Path
        A git checkout

    Returns
    -------
    str | None
        The full commit id, or None if git is missing or `root` is not a checkout
    """
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
    return commit if out.returncode == 0 and GIT_COMMIT.fullmatch(commit) else None
