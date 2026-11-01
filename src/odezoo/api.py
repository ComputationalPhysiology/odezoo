"""The Python interface to odezoo: list, search and fetch models"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from . import http
from .cache import Cache
from .cache import cache_dir as resolve_cache_dir
from .errors import OdezooError
from .fetch import fetch_bytes, write_output
from .registry import load as load_registry
from .resolve import choose_version
from .schema import Model
from .search import search as search_models


def models(*, registry: Path | str | None = None) -> list[Model]:
    """Every model in the registry, sorted by id"""
    reg = load_registry(registry)
    return [reg.models[id] for id in sorted(reg.models)]


def model(id: str, *, registry: Path | str | None = None) -> Model:
    return load_registry(registry).get(id)


def search(
    text: str = "",
    *,
    category: str | Sequence[str] | None = None,
    keyword: str | Sequence[str] | None = None,
    species: str | Sequence[str] | None = None,
    format: str | None = None,
    reviewed: bool | None = None,
    registry: Path | str | None = None,
) -> list[Model]:
    return search_models(
        load_registry(registry).models.values(),
        text,
        category=category,
        keyword=keyword,
        species=species,
        format=format,
        reviewed=reviewed,
    )


def get(
    id: str,
    *,
    version: str | None = None,
    format: str | None = None,
    dest: Path | str | None = None,
    cache: bool = True,
    cache_dir: Path | str | None = None,
    registry: Path | str | None = None,
    force: bool = False,
) -> Path:
    """Fetch a model's file, verified by its sha256, and return where it is

    Without `dest` this is the file in the cache (or in the registry checkout). An existing
    folder as `dest` gets `<id>.<ext>` in it; anything else is the path to write.
    """
    if not cache and dest is None:
        raise ValueError("get(cache=False) needs dest: without the cache the file has no home")
    reg = load_registry(registry)
    m = reg.get(id)
    v = choose_version(m, version=version, format=format)
    store = Cache(resolve_cache_dir(cache_dir)) if cache else None
    data, path = fetch_bytes(reg, m, v, cache=store, http=http.client())
    if dest is None:
        if path is None:
            assert store is not None
            raise OdezooError(
                f"could not keep {m.id} in the cache folder {store.root}; "
                "fix --cache-dir / ODEZOO_CACHE_DIR, or pass dest"
            )
        return path
    dest = Path(dest)
    target = dest / f"{m.id}{v.ext}" if dest.is_dir() else dest
    return write_output(data, target, force=force)
