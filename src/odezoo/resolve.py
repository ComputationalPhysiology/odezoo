"""Choose which version of a model to fetch"""

from __future__ import annotations

from .errors import VersionNotFound
from .schema import Model, Version


def choose_version(
    model: Model, *, version: str | None = None, format: str | None = None
) -> Version:
    """Choose the version of `model` to fetch

    That is `version` if it is given; else the default version, if it is in `format`; else the
    newest version in `format` (or of any format).

    Parameters
    ----------
    model : Model
        The model
    version : str, optional
        The id of the version to fetch
    format : str, optional
        The format the version must be in, `cellml` or `ode`

    Returns
    -------
    Version
        The chosen version

    Raises
    ------
    VersionNotFound
        If the model has no version `version`, that version is not in `format`, or the model has
        no version in `format`
    """
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
