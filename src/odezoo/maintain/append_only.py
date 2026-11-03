"""The append-only rule: a version, once released, never changes and is never removed

A file's identity is its sha256, so "same release, same bytes" holds only if the fields that pick
the bytes never change. This compares two `registry.json` documents: an older one, such as
`main`'s, and the one a change would make.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..errors import RegistryError
from ..registry import SCHEMA_VERSION

# The fields of a version that may never change; `license` and `notes` may be corrected.
FROZEN = ("id", "format", "sha256", "file")


def _versions(doc: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    """Index a `registry.json` document's versions by model id, then by version id

    Parameters
    ----------
    doc : Mapping[str, Any]
        The document

    Returns
    -------
    dict[str, dict[str, Mapping[str, Any]]]
        Each model's versions, by id
    """
    return {m["id"]: {v["id"]: v for v in m.get("versions", [])} for m in doc.get("models", [])}


def append_only_problems(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    """List the ways `new` changes or removes a version that `old` has

    Parameters
    ----------
    old : Mapping[str, Any]
        The older `registry.json` document, such as `main`'s
    new : Mapping[str, Any]
        The newer one

    Returns
    -------
    list[str]
        One line per problem, such as `beeler_reuter_1977 v1: sha256 changed`, in the order of
        `old`; empty if every version of `old` is in `new` unchanged
    """
    before, after = _versions(old), _versions(new)
    problems = []
    for model_id, versions in before.items():
        for version_id, version in versions.items():
            now = after.get(model_id, {}).get(version_id)
            if now is None:
                problems.append(f"{model_id} {version_id}: removed")
                continue
            for field in FROZEN:
                if version.get(field) != now.get(field):
                    problems.append(f"{model_id} {version_id}: {field} changed")
    return problems


def read_registry_json(path: Path) -> dict[str, Any]:
    """Read a `registry.json` document written by `odezoo registry build`

    Parameters
    ----------
    path : Path
        The file

    Returns
    -------
    dict[str, Any]
        The document

    Raises
    ------
    RegistryError
        If the file cannot be read, is not JSON, or is not a `registry.json` of this schema
    """
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RegistryError(f"{path} cannot be read as a registry.json ({e})") from None
    if not isinstance(doc, dict) or doc.get("schema") != SCHEMA_VERSION:
        raise RegistryError(
            f"{path} is not a registry.json of schema {SCHEMA_VERSION}; "
            "make it with odezoo registry build"
        )
    return doc
