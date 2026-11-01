"""`odezoo registry add version`: add one of our own files as a new version of a model"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from odezoo.errors import RegistryError
from odezoo.fetch import sha256_hex
from odezoo.maintain.toml import version_block
from odezoo.registry import load_checkout, read_model
from odezoo.schema import FORMATS, Model, Version

OWN_VERSION = re.compile(r"^v(\d+)$")


def next_version_id(model: Model) -> str:
    numbers = [int(m.group(1)) for v in model.versions if (m := OWN_VERSION.match(v.id))]
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
    """
    root, file = Path(root), Path(file)
    formats = {ext: format for format, ext in FORMATS.items()}
    format = formats.get(file.suffix)
    if format is None:
        raise RegistryError(
            f"{file.name}: {file.suffix or 'no suffix'} is not one of {', '.join(formats)}"
        )
    model = load_checkout(root).get(model_id)
    parent = model.version(derived_from) if derived_from in {v.id for v in model.versions} else None
    data = file.read_bytes()
    vid = next_version_id(model)
    version = Version(
        id=vid,
        format=format,
        sha256=sha256_hex(data),
        license=license or (parent.license if parent else "unknown"),
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
