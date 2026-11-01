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
    """List every model in the registry

    Parameters
    ----------
    registry : Path | str, optional
        A registry checkout to use instead of $ODEZOO_REGISTRY or the bundled registry

    Returns
    -------
    list[Model]
        The models, sorted by id
    """
    reg = load_registry(registry)
    return [reg.models[id] for id in sorted(reg.models)]


def model(id: str, *, registry: Path | str | None = None) -> Model:
    """Look up one model

    Parameters
    ----------
    id : str
        The model's id; other capitals and surrounding spaces are forgiven
    registry : Path | str, optional
        A registry checkout to use instead of $ODEZOO_REGISTRY or the bundled registry

    Returns
    -------
    Model
        The model: its paper, keywords, versions and sources

    Raises
    ------
    ModelNotFound
        If no model has that id; the message suggests similar ones
    """
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
    """Find models by text and filters

    Every word of `text` must occur somewhere in the model's id, name, family, paper title and
    authors, keywords, cell type or species. Several values for one filter are alternatives;
    different filters must all hold.

    Parameters
    ----------
    text : str, optional
        Words that must all occur, in any case; by default none
    category : str | Sequence[str], optional
        Categories, from `odezoo.schema.CATEGORIES`, of which a model must have one
    keyword : str | Sequence[str], optional
        Keywords of which a model must have one
    species : str | Sequence[str], optional
        Species, in any case, one of which must be the model's
    format : str, optional
        A format, `cellml` or `ode`, that the model must have a version in
    reviewed : bool, optional
        True for reviewed models only, False for unreviewed ones only
    registry : Path | str, optional
        A registry checkout to use instead of $ODEZOO_REGISTRY or the bundled registry

    Returns
    -------
    list[Model]
        The matching models, sorted by id
    """
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

    The file is taken from the registry checkout, the cache, this repository's copy on GitHub or
    upstream, in that order, and only with the sha256 the registry records for it.

    Parameters
    ----------
    id : str
        The model's id
    version : str, optional
        The version to fetch; by default the model's default version, else its newest
    format : str, optional
        `cellml` or `ode`: the version must be in this format
    dest : Path | str, optional
        Where to write the file: an existing folder gets `<id>.<ext>` in it, and anything else
        is the path of the file. By default the file is not copied, and its path in the cache
        (or in the registry checkout) is returned.
    cache : bool, optional
        Whether to read and write the cache, by default True; False needs `dest`
    cache_dir : Path | str, optional
        The cache folder, by default $ODEZOO_CACHE_DIR or else the platform's cache folder
    registry : Path | str, optional
        A registry checkout to use instead of $ODEZOO_REGISTRY or the bundled registry
    force : bool, optional
        Whether to overwrite a different file at the destination, by default False

    Returns
    -------
    Path
        The file

    Raises
    ------
    ModelNotFound
        If no model has that id
    VersionNotFound
        If the model has no such version, or none in `format`
    FetchError
        If no place gave the file with the recorded sha256
    OutputExistsError
        If the destination holds a different file and `force` is False
    OdezooError
        If the file cannot be kept in the cache and `dest` is not given
    ValueError
        If `cache` is False and `dest` is not given
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
