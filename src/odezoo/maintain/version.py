"""`odezoo registry add version`: add one of our own files as a new version of a model"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from ..errors import RegistryError
from ..fetch import sha256_hex
from ..registry import load_checkout, read_model
from ..schema import FORMATS, Model, Version
from .toml import version_block

OWN_VERSION = re.compile(r"^v(\d+)$")


def next_version_id(model: Model) -> str:
    """Choose the id for our next own version of `model`

    Parameters
    ----------
    model : Model
        The model

    Returns
    -------
    str
        `v<N>`, with N one more than the highest such id so far, or `v1` if there is none
    """
    numbers = [int(m.group(1)) for v in model.versions if (m := OWN_VERSION.fullmatch(v.id))]
    return f"v{max(numbers, default=0) + 1}"


def add_version(
    root: Path,
    model_id: str,
    file: Path,
    *,
    derived_from: str,
    license: str | None = None,
    notes: str | None = None,
    today: date | None = None,
) -> Version:
    """Copy `file` into the model's folder as version v<N> and record it in model.toml

    If the model no longer reads back, model.toml and the folder are put back as they were.

    Parameters
    ----------
    root : Path
        The registry checkout
    model_id : str
        The model to add a version to
    file : Path
        The edited `.cellml` or `.ode` file
    derived_from : str
        The id of the version `file` was edited from
    license : str, optional
        The SPDX id of the new version's licence, by default that of `derived_from`
    notes : str, optional
        What was changed, and why
    today : date, optional
        The day to record as `added`, by default today

    Returns
    -------
    Version
        The new version

    Raises
    ------
    ModelNotFound
        If the checkout has no model `model_id`
    RegistryError
        If `file` is not `.cellml` or `.ode`, there is no version `derived_from`, the copy's
        name is taken, or the model does not read back with the new version
    """
    root, file = Path(root), Path(file)
    formats = {ext: format for format, ext in FORMATS.items()}
    format = formats.get(file.suffix)
    if format is None:
        raise RegistryError(
            f"{file.name}: {file.suffix or 'no suffix'} is not one of {', '.join(formats)}"
        )
    model = load_checkout(root).get(model_id)
    if derived_from not in {v.id for v in model.versions}:
        ids = ", ".join(v.id for v in model.versions)
        raise RegistryError(
            f"{model.id} has no version {derived_from!r} to derive from; it has {ids}"
        )
    parent = model.version(derived_from)
    data = file.read_bytes()
    vid = next_version_id(model)
    version = Version(
        id=vid,
        format=format,
        sha256=sha256_hex(data),
        license=license or parent.license,
        added=today or date.today(),
        file=f"{vid}{FORMATS[format]}",
        derived_from=derived_from,
        notes=notes,
    )

    folder = root / "models" / model.id
    toml = folder / "model.toml"
    original = toml.read_text(encoding="utf-8")
    copy = folder / f"{vid}{FORMATS[format]}"
    if copy.exists():
        raise RegistryError(f"{copy.name} already exists in models/{model.id}; move it away first")
    copy.write_bytes(data)
    separator = "" if original.endswith("\n") else "\n"
    toml.write_text(original + separator + "\n" + version_block(version), encoding="utf-8")
    try:
        read_model(folder)
    except RegistryError:
        toml.write_text(original, encoding="utf-8")
        copy.unlink()
        raise
    return version
