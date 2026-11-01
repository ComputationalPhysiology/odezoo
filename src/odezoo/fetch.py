"""Get a version's bytes from wherever they are, and prove they are the recorded ones

The order is: the file in a local checkout, the cache, the mirror (this repository on GitHub,
pinned to the registry's commit), then upstream. Every candidate is checked against the
version's sha256, so the order only changes speed and reliability, never the bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from odezoo.cache import Cache, write_atomically
from odezoo.errors import Attempt, FetchError, OdezooError, OutputExistsError
from odezoo.http import Http, HttpError
from odezoo.registry import Registry
from odezoo.schema import Model, Version


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def mirror_url(registry: Registry, model: Model, version: Version) -> str | None:
    """The copy of the file in this repository on GitHub, at the registry's commit"""
    if version.file is None or registry.commit is None:
        return None
    return f"{registry.mirror_base}/{registry.commit}/models/{model.id}/{version.file}"


def fetch_bytes(
    registry: Registry, model: Model, version: Version, *, cache: Cache | None, http: Http
) -> tuple[bytes, Path | None]:
    """The version's bytes, and the path where they are kept (None if they are only in memory)"""
    attempts: list[Attempt] = []

    def verified(data: bytes, source: str) -> bool:
        if sha256_hex(data) == version.sha256:
            return True
        attempts.append(Attempt(source, "sha256 mismatch"))
        return False

    if registry.root is not None and version.file is not None:
        path = registry.root / "models" / model.id / version.file
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            attempts.append(Attempt(str(path), "not found"))
        else:
            if verified(data, str(path)):
                return data, path

    if cache is not None:
        cached = cache.read(version.sha256, version.ext)
        if cached is not None:
            return cached, cache.path_for(version.sha256, version.ext)

    upstream = None if version.source is None else version.source.url_for_download()
    for url in (mirror_url(registry, model, version), upstream):
        if url is None:
            continue
        try:
            data = http.get(url)
        except HttpError as e:
            attempts.append(Attempt(url, e.reason))
            continue
        if verified(data, url):
            stored = None
            if cache is not None:
                try:
                    stored = cache.write(version.sha256, version.ext, data)
                except OSError:
                    pass  # an unusable cache folder must not cost the download
            return data, stored

    raise FetchError(model.id, version.id, attempts)


def write_output(data: bytes, target: Path, *, force: bool = False) -> Path:
    """Write `data` to `target`, creating folders; an identical file there is left alone"""
    target = Path(target)
    if target.is_dir():
        raise OdezooError(f"{target} is a folder, not a file")
    if target.exists():
        if target.read_bytes() == data:
            return target
        if not force:
            raise OutputExistsError(target)
    write_atomically(target, data)
    return target
