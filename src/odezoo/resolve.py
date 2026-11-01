"""Choose which version of a model to fetch"""

from __future__ import annotations

from odezoo.errors import VersionNotFound
from odezoo.schema import Model, Version


def choose_version(
    model: Model, *, version: str | None = None, format: str | None = None
) -> Version:
    """The version asked for; else the default version, if it has the format asked for; else the
    newest version in that format (or of any format)"""
    if version is not None:
        chosen = model.version(version)
        if format is not None and chosen.format != format:
            raise VersionNotFound(f"{model.id} version {version} is {chosen.format}, not {format}")
        return chosen
    candidates = [v for v in model.versions if format is None or v.format == format]
    if not candidates:
        raise VersionNotFound(
            f"{model.id} has no {format} version; it has {', '.join(model.formats)}"
        )
    for v in candidates:
        if v.id == model.default_version:
            return v
    return candidates[-1]
