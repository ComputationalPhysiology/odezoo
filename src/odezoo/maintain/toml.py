"""Write `model.toml` files

There is no TOML writer in the standard library, and the schema is small and fixed, so this
writes it directly. The layout follows `schema.model_to_dict`, which owns the field order.
"""

from __future__ import annotations

import json
from typing import Any

from odezoo.schema import Model, Version, _version_to_dict, model_to_dict


def _value(key: str, value: Any) -> str:
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
    return isinstance(value, dict) or (
        isinstance(value, list) and bool(value) and isinstance(value[0], dict)
    )


def _pairs(table: dict[str, Any]) -> list[str]:
    return [f"{key} = {_value(key, value)}" for key, value in table.items() if not _is_table(value)]


def _version_lines(version: dict[str, Any]) -> list[str]:
    lines = ["[[versions]]", *_pairs(version)]
    if "source" in version:
        lines += ["", "[versions.source]", *_pairs(version["source"])]
    return lines


def dump_model(model: Model) -> str:
    data = model_to_dict(model)
    lines = _pairs(data)
    lines += ["", "[paper]", *_pairs(data["paper"])]
    for reference in data.get("references", []):
        lines += ["", "[[references]]", *_pairs(reference)]
    for version in data["versions"]:
        lines += ["", *_version_lines(version)]
    return "\n".join(lines) + "\n"


def version_block(version: Version) -> str:
    """One `[[versions]]` table, for appending to the end of a `model.toml`"""
    return "\n".join(_version_lines(_version_to_dict(version))) + "\n"
