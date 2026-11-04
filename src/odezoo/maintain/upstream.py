"""Check that upstream still serves each version's file with the recorded sha256

`registry.yml` checks the versions a pull request adds this way, so a version is never recorded
with a source that does not give its bytes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ..fetch import sha256_hex
from ..http import Http, HttpError
from ..registry import Registry
from ..schema import Model, Version


@dataclass(frozen=True)
class Checked:
    """One upstream source that was downloaded, and what was wrong with it

    Attributes
    ----------
    model : str
        The model's id
    version : str
        The version's id
    url : str
        The URL that was downloaded
    problem : str | None
        None if the bytes have the recorded sha256; else `sha256 mismatch`, or why the download
        failed, such as `HTTP 404`
    """

    model: str
    version: str
    url: str
    problem: str | None


def upstream_versions(registry: Registry) -> list[tuple[Model, Version]]:
    """List the versions that have an upstream source

    Parameters
    ----------
    registry : Registry
        The registry

    Returns
    -------
    list[tuple[Model, Version]]
        Each model and version with a source, sorted by model id, then version id
    """
    pairs = [(m, v) for m in registry.models.values() for v in m.versions if v.source is not None]
    return sorted(pairs, key=lambda pair: (pair[0].id, pair[1].id))


def new_since(registry: Registry, old: Mapping[str, Any]) -> list[tuple[Model, Version]]:
    """List the versions with an upstream source that an older `registry.json` does not have

    Parameters
    ----------
    registry : Registry
        The registry
    old : Mapping[str, Any]
        The older `registry.json` document, such as `main`'s

    Returns
    -------
    list[tuple[Model, Version]]
        The new versions, in the order of `upstream_versions`
    """
    known = {(m["id"], v["id"]) for m in old.get("models", []) for v in m.get("versions", [])}
    return [(m, v) for m, v in upstream_versions(registry) if (m.id, v.id) not in known]


def check_upstream(pairs: Sequence[tuple[Model, Version]], *, http: Http) -> list[Checked]:
    """Download each version's file from its source, and compare its sha256

    The mirror and the cache are never used: the point is to ask upstream.

    Parameters
    ----------
    pairs : Sequence[tuple[Model, Version]]
        The models and versions to check; each version has a source
    http : Http
        The client to download with, which spaces out requests to each host

    Returns
    -------
    list[Checked]
        One result per version, in the order of `pairs`
    """
    results = []
    for model, version in pairs:
        assert version.source is not None
        url = version.source.url_for_download()
        try:
            data = http.get(url)
        except HttpError as e:
            problem: str | None = e.reason
        else:
            problem = None if sha256_hex(data) == version.sha256 else "sha256 mismatch"
        results.append(Checked(model.id, version.id, url, problem))
    return results
