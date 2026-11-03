"""Write `model.toml` files

There is no TOML writer in the standard library, and the schema is small and fixed, so this
writes it directly. The layout follows `schema.model_to_dict`, which owns the field order.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ..schema import Model, Version, model_to_dict, version_to_dict


def _value(key: str, value: Any) -> str:
    """Write one value as TOML

    Parameters
    ----------
    key : str
        The value's field; `added` holds an ISO date string, which is written as a bare date
    value : Any
        A boolean, an integer, a string, or a list of them

    Returns
    -------
    str
        The value as TOML

    Raises
    ------
    TypeError
        For a value of any other type
    """
    if key == "added":  # an ISO date in the dict form; bare in TOML, so it reads back as a date
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        # A JSON string is also a valid TOML basic string.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(_value("", item) for item in value) + "]"
    raise TypeError(f"cannot write {key} = {value!r} as TOML")


def _is_table(value: Any) -> bool:
    """Tell whether a value is written as a table (or array of tables) rather than inline

    Parameters
    ----------
    value : Any
        A value from the dict form of a model

    Returns
    -------
    bool
        True for a dict, or a list of dicts that is not empty
    """
    return isinstance(value, dict) or (
        isinstance(value, list) and bool(value) and isinstance(value[0], dict)
    )


def _pairs(table: Mapping[str, Any]) -> list[str]:
    """Write a table's plain fields as `key = value` lines, leaving out the tables in it

    Parameters
    ----------
    table : Mapping[str, Any]
        A table from the dict form of a model

    Returns
    -------
    list[str]
        One line per field, in the table's order
    """
    return [f"{key} = {_value(key, value)}" for key, value in table.items() if not _is_table(value)]


def _version_lines(version: Mapping[str, Any]) -> list[str]:
    """Write one version as a `[[versions]]` table, then its `[versions.source]` if it has one

    Parameters
    ----------
    version : Mapping[str, Any]
        The version's dict form

    Returns
    -------
    list[str]
        The lines
    """
    lines = ["[[versions]]", *_pairs(version)]
    if "source" in version:
        lines += ["", "[versions.source]", *_pairs(version["source"])]
    return lines


def dump_model(model: Model) -> str:
    """Write a model as the text of its `model.toml`

    Parameters
    ----------
    model : Model
        The model

    Returns
    -------
    str
        The TOML, which `parse_model` reads back as the same model
    """
    return dump_dict(model_to_dict(model))


def dump_dict(data: Mapping[str, Any]) -> str:
    """Write the dict form of a model as the text of its `model.toml`

    Unlike `dump_model`, this also writes a model that breaks the schema's rules, such as one
    that `odezoo registry add url` made and whose paper is still to be filled in.

    Parameters
    ----------
    data : Mapping[str, Any]
        The model in `model_to_dict`'s form; `paper`, `references` and `versions` may be missing

    Returns
    -------
    str
        The TOML
    """
    lines = _pairs(data)
    if "paper" in data:
        lines += ["", "[paper]", *_pairs(data["paper"])]
    for reference in data.get("references", []):
        lines += ["", "[[references]]", *_pairs(reference)]
    for version in data.get("versions", []):
        lines += ["", *_version_lines(version)]
    return "\n".join(lines) + "\n"


def version_block(version: Version) -> str:
    """Write one version as a `[[versions]]` table, for appending to the end of a `model.toml`

    Parameters
    ----------
    version : Version
        The version

    Returns
    -------
    str
        The table, ending in a newline
    """
    return "\n".join(_version_lines(version_to_dict(version))) + "\n"
