"""Add a version to the registry: as a new model, or as one more version of a model that is there

A new model is written with what is known, and the maintainer fills in the rest (`TO_FILL_IN`);
`odezoo registry check` fails until they have. Everything else about the version is checked
before anything is written.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import RegistryError
from ..schema import CATEGORIES, MODEL_ID, Version, parse_model, version_to_dict
from .toml import dump_dict, version_block

# The fields a new model may be written without, for the maintainer to fill in.
TO_FILL_IN = ("paper", "categories")
# Stand-ins for those fields, so that the rest of a new model can be checked before it is written.
_PLACEHOLDERS: dict[str, Any] = {
    "paper": {"title": "-", "authors": ["-"], "journal": "-", "year": 1, "doi": "10.0000/-"},
    "categories": [CATEGORIES[0]],
}


@dataclass(frozen=True)
class Outcome:
    """What adding a version did

    Attributes
    ----------
    id : str
        The model
    version : str
        The version that was added, or the one that already holds the same file
    action : str
        `added model`, `added version` or `unchanged`
    detail : str
        For a new model, what is still to be filled in, such as `fill in: paper, categories`;
        for `unchanged`, why
    """

    id: str
    version: str
    action: str
    detail: str = ""


def _check(data: Mapping[str, Any], where: str) -> None:
    """Check a model by the schema's rules, except for the fields still to be filled in

    Parameters
    ----------
    data : Mapping[str, Any]
        The model, as `model.toml` parses
    where : str
        The file, for error messages

    Raises
    ------
    RegistryError
        At the first rule that is broken
    """
    filled = {**data, **{k: v for k, v in _PLACEHOLDERS.items() if not data.get(k)}}
    parse_model(filled, where=where)


def write_version(
    root: Path,
    model_id: str,
    version: Version,
    data: bytes,
    *,
    new_model: Mapping[str, Any],
    dry_run: bool = False,
) -> Outcome:
    """Add `version` to the model `model_id`, making the model from `new_model` if it is not there

    Parameters
    ----------
    root : Path
        The registry checkout
    model_id : str
        The model's id, which is also its folder's name
    version : Version
        The version; its `file`, if set, is written from `data`
    data : bytes
        The version's file, whose sha256 is `version.sha256`
    new_model : Mapping[str, Any]
        The model-level fields of a new model, in `model.toml`'s order, without `versions`
    dry_run : bool, optional
        Whether to only say what would happen, by default False

    Returns
    -------
    Outcome
        What was done, or would be done

    Raises
    ------
    RegistryError
        If `model_id` is not a valid id, the model already has a version with that id and
        another file, a file is in the way, or the model would break the schema's rules (other
        than the fields still to fill in); nothing is written then
    """
    if not MODEL_ID.fullmatch(model_id):
        raise RegistryError(f"{model_id!r} is not a model id; it must match {MODEL_ID.pattern}")
    folder = root / "models" / model_id
    toml = folder / "model.toml"
    where = f"models/{model_id}/model.toml"
    copy = folder / version.file if version.file else None

    if not toml.is_file():
        if folder.exists():
            raise RegistryError(f"models/{model_id} exists but has no model.toml")
        model = {**new_model, "versions": [version_to_dict(version)]}
        _check(model, where)
        missing = [key for key in TO_FILL_IN if not model.get(key)]
        if not dry_run:
            folder.mkdir(parents=True)
            if copy is not None:
                copy.write_bytes(data)
            toml.write_bytes(dump_dict(model).encode("utf-8"))
        detail = f"fill in: {', '.join(missing)}" if missing else ""
        return Outcome(model_id, version.id, "added model", detail)

    original = toml.read_bytes()
    try:
        existing = tomllib.loads(original.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as e:
        raise RegistryError(f"cannot be read ({e})", where=where) from None
    for other in existing.get("versions", []):
        if other.get("sha256") == version.sha256:
            same = other.get("id", "?")
            return Outcome(model_id, same, "unchanged", f"the same file as version {same}")
        if other.get("id") == version.id:
            raise RegistryError(
                f"{model_id} already has a version {version.id} with another file; "
                "versions never change, so add the file on another day or from another commit"
            )
    _check({**existing, "versions": [*existing.get("versions", []), version_to_dict(version)]},
           where)  # fmt: skip
    if dry_run:
        return Outcome(model_id, version.id, "added version")
    if copy is not None and copy.exists():
        raise RegistryError(f"{copy.name} already exists in models/{model_id}; move it away first")

    separator = b"" if original.endswith(b"\n") else b"\n"
    if copy is not None:
        copy.write_bytes(data)
    toml.write_bytes(original + separator + b"\n" + version_block(version).encode("utf-8"))
    try:
        _check(tomllib.loads(toml.read_text(encoding="utf-8")), where)
    except (RegistryError, tomllib.TOMLDecodeError):
        toml.write_bytes(original)
        if copy is not None:
            copy.unlink()
        raise
    return Outcome(model_id, version.id, "added version")
