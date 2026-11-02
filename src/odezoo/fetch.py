"""Get a version's bytes from wherever they are, and prove they are the recorded ones

The order is: the file in a local checkout, the cache, the mirror (this repository on GitHub,
pinned to the registry's commit), then upstream. Every candidate is checked against the
version's sha256, so the order only changes speed and reliability, never the bytes.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .cache import Cache, write_atomically
from .errors import Attempt, FetchError, OdezooError, OutputExistsError
from .http import Http, HttpError
from .registry import Registry
from .schema import Model, Version


def sha256_hex(data: bytes) -> str:
    """Hash `data` the way the registry records files

    Parameters
    ----------
    data : bytes
        A file's bytes

    Returns
    -------
    str
        The sha256, as 64 lowercase hex digits
    """
    return hashlib.sha256(data).hexdigest()


def mirror_url(registry: Registry, model: Model, version: Version) -> str | None:
    """Return the URL of this repository's copy of the file on GitHub, at the registry's commit

    Parameters
    ----------
    registry : Registry
        The registry the model is from; its `commit` pins the URL
    model : Model
        The model
    version : Version
        The version

    Returns
    -------
    str | None
        The URL, or None if the version has no copy here or the registry's commit is not known
    """
    if version.file is None or registry.commit is None:
        return None
    return f"{registry.mirror_base}/{registry.commit}/models/{model.id}/{version.file}"


def fetch_bytes(
    registry: Registry, model: Model, version: Version, *, cache: Cache | None, http: Http
) -> tuple[bytes, Path | None]:
    """Get a version's bytes from the first place that has them with the recorded sha256

    The places are the file in a registry checkout, the cache, the mirror and upstream, in that
    order. Downloaded bytes are written to the cache; a cache that cannot be written is skipped.

    Parameters
    ----------
    registry : Registry
        The registry the model is from
    model : Model
        The model
    version : Version
        The version to fetch
    cache : Cache | None
        The cache to read and write, or None to leave it out
    http : Http
        The client to download with

    Returns
    -------
    tuple[bytes, Path | None]
        The bytes, and where they are kept: the file in the checkout or in the cache, or None if
        they are only in memory

    Raises
    ------
    FetchError
        If no place has the bytes, with every place tried and why it failed
    """
    attempts: list[Attempt] = []

    def verified(data: bytes, source: str) -> bool:
        """Check `data` against the version's sha256, recording a mismatch as an attempt

        Parameters
        ----------
        data : bytes
            Bytes from `source`
        source : str
            The path or URL they came from

        Returns
        -------
        bool
            Whether `data` has the recorded sha256
        """
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
        except OSError as e:
            attempts.append(Attempt(str(path), f"cannot be read ({e.strerror or e})"))
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
    """Write `data` to `target`, creating folders; an identical file there is left alone

    Parameters
    ----------
    data : bytes
        The file's bytes
    target : Path
        The file to write
    force : bool, optional
        Whether to overwrite a different file, by default False

    Returns
    -------
    Path
        `target`

    Raises
    ------
    OutputExistsError
        If `target` holds different bytes and `force` is False
    OdezooError
        If `target` is a folder
    """
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
