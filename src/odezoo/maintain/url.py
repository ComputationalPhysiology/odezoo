"""`odezoo registry add url`: add a model's file from GitHub, Zenodo, PMR or any other URL

GitHub, Zenodo and PMR URLs become sources of their own type, pinned to a commit or a record, so
the file they name can never change; any other URL is kept as it is, and its sha256 is what
catches a change.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import SplitResult, unquote, urlsplit

from ..errors import RegistryError
from ..fetch import sha256_hex
from ..http import Http
from ..schema import FORMATS, GIT_COMMIT, MIRROR_LICENSES, Source, Version
from .add import Outcome, write_version
from .check import cellml_problem

GITHUB_API = "https://api.github.com"
GITHUB_SHA = "application/vnd.github.sha"  # asks the commits API for the bare commit id
PMR_HOST = "models.physiomeproject.org"


def _github(owner: str, repo: str, ref: str, path: str, *, http: Http, api: str) -> Source:
    """Make a GitHub source, resolving a branch or tag to the commit it points at

    Parameters
    ----------
    owner : str
        The repository's owner
    repo : str
        The repository's name
    ref : str
        A full commit id, or a branch or tag
    path : str
        The file's path in the repository
    http : Http
        The client to ask GitHub's API with, if `ref` is not a full commit id
    api : str
        GitHub's API

    Returns
    -------
    Source
        A `github` source pinned to a full commit id

    Raises
    ------
    RegistryError
        If `path` is empty, or GitHub does not answer with a commit id
    HttpError
        If GitHub's API cannot be reached, or does not know `ref`
    """
    if not path:
        raise RegistryError(f"github.com/{owner}/{repo}: the URL names no file")
    if not GIT_COMMIT.fullmatch(ref):
        answer = http.get(f"{api}/repos/{owner}/{repo}/commits/{ref}", accept=GITHUB_SHA)
        commit = answer.decode("ascii", "replace").strip()
        if not GIT_COMMIT.fullmatch(commit):
            raise RegistryError(f"GitHub gave no commit id for {ref} in {owner}/{repo}")
        ref = commit
    return Source(type="github", repo=f"{owner}/{repo}", commit=ref, path=path)


def _pmr(url: str, parts: SplitResult) -> Source:
    """Make a PMR source from the URL of a file in a workspace, at a commit

    Parameters
    ----------
    url : str
        The URL, for error messages
    parts : SplitResult
        The URL, split

    Returns
    -------
    Source
        A `pmr` source

    Raises
    ------
    RegistryError
        If the URL is not `.../workspace/<name>/(rawfile|file)/<commit>/<path>` or
        `.../w/<user>/<name>/(rawfile|file)/<commit>/<path>` with a full commit id
    """
    raw = parts.path.split("/")[1:]
    head = 2 if raw[:1] == ["workspace"] else 3 if raw[:1] == ["w"] else 0
    rest = [unquote(s) for s in raw[head:]] if head else []
    if len(rest) >= 3 and rest[0] in ("rawfile", "file") and GIT_COMMIT.fullmatch(rest[1]):
        workspace = f"{parts.scheme}://{parts.netloc}/{'/'.join(raw[:head])}"
        return Source(type="pmr", workspace=workspace, commit=rest[1], path="/".join(rest[2:]))
    raise RegistryError(
        f"{url} is not a PMR file pinned to a commit; use the file's rawfile URL, "
        f"https://{PMR_HOST}/workspace/<name>/rawfile/<commit>/<file>, with the full "
        "40-character commit id"
    )


def url_source(url: str, *, http: Http, api: str = GITHUB_API) -> Source:
    """Turn the URL of a model's file into a source

    Parameters
    ----------
    url : str
        A GitHub blob or raw URL, a Zenodo record file URL, a PMR file URL at a commit, or any
        other http(s) URL
    http : Http
        The client to ask GitHub's API with, for a GitHub URL on a branch or tag
    api : str, optional
        GitHub's API, by default `https://api.github.com`

    Returns
    -------
    Source
        A `github`, `zenodo` or `pmr` source, pinned to a commit or a record, or a `url` source

    Raises
    ------
    RegistryError
        If the URL is not http(s), or is a PMR URL that is not a file at a full commit
    HttpError
        If a GitHub branch or tag cannot be resolved
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise RegistryError(f"{url} must be an http:// or https:// URL")
    segments = [unquote(s) for s in parts.path.split("/")[1:]]
    host = parts.hostname
    if host in ("github.com", "www.github.com") and len(segments) >= 4:
        if segments[2] in ("blob", "raw"):
            owner, repo, _, ref, *path = segments
            return _github(owner, repo, ref, "/".join(path), http=http, api=api)
    if host == "raw.githubusercontent.com" and len(segments) >= 3:
        owner, repo, ref, *path = segments
        if ref == "refs" and len(path) >= 2 and path[0] in ("heads", "tags"):
            ref, path = path[1], path[2:]  # GitHub's Raw button: refs/heads/<branch>/<path>
        return _github(owner, repo, ref, "/".join(path), http=http, api=api)
    if (
        host == "zenodo.org"
        and len(segments) == 4
        and (segments[0], segments[2]) == ("records", "files")
        and segments[1].isdigit()
    ):
        return Source(type="zenodo", record=int(segments[1]), filename=segments[3])
    if host == PMR_HOST:
        return _pmr(url, parts)
    return Source(type="url", url=url)


def _version_id(source: Source, today: date) -> str:
    """Name the version of a file from `source`, as the registry's conventions say

    Parameters
    ----------
    source : Source
        Where the file comes from
    today : date
        The day it is added

    Returns
    -------
    str
        `pmr-` or `github-` and the commit's first 7 hex digits, `zenodo-<record>`, or
        `url-<YYYY-MM-DD>`
    """
    if source.type in ("pmr", "github"):
        assert source.commit is not None
        return f"{source.type}-{source.commit[:7]}"
    if source.type == "zenodo":
        return f"zenodo-{source.record}"
    return f"url-{today.isoformat()}"


def add_url(
    root: Path,
    url: str,
    *,
    id: str,
    license: str = "unknown",
    http: Http,
    api: str = GITHUB_API,
    today: date | None = None,
    dry_run: bool = False,
) -> Outcome:
    """Download the file at `url` and add it to the model `id`, making the model if need be

    A new model gets only its id as its name, and no paper or categories: the maintainer fills
    those in, and `odezoo registry check` fails until they have.

    Parameters
    ----------
    root : Path
        The registry checkout
    url : str
        The file's URL; see `url_source`
    id : str
        The model to add the file to, or to make
    license : str, optional
        The file's licence, an SPDX id, by default `unknown`; a copy is kept in the checkout only
        under a licence in `MIRROR_LICENSES`
    http : Http
        The client to download with
    api : str, optional
        GitHub's API, by default `https://api.github.com`
    today : date, optional
        The day to record as `added`, by default today
    dry_run : bool, optional
        Whether to only say what would happen, by default False

    Returns
    -------
    Outcome
        What was done, or would be done

    Raises
    ------
    RegistryError
        If the URL's file is not `.cellml` or `.ode`, is CellML with an `<import>`, or cannot be
        added (see `url_source` and `write_version`)
    HttpError
        If the file cannot be downloaded
    """
    parts = urlsplit(url)
    if parts.hostname == PMR_HOST:
        _pmr(url, parts)  # a PMR page is told which URL to use, before the suffix is read
    formats = {ext: format for format, ext in FORMATS.items()}
    suffix = PurePosixPath(parts.path).suffix
    format = formats.get(suffix)
    if format is None:
        raise RegistryError(f"{url}: {suffix or 'no extension'} is not one of {', '.join(formats)}")
    source = url_source(url, http=http, api=api)
    data = http.get(source.url_for_download())
    if format == "cellml" and (problem := cellml_problem(data)):
        raise RegistryError(f"{url}: {problem}")
    vid = _version_id(source, today or date.today())
    version = Version(
        id=vid,
        format=format,
        sha256=sha256_hex(data),
        license=license,
        added=today or date.today(),
        file=f"{vid}{FORMATS[format]}" if license in MIRROR_LICENSES else None,
        source=source,
    )
    new_model = {"id": id, "name": id, "categories": [], "reviewed": False}
    return write_version(root, id, version, data, new_model=new_model, dry_run=dry_run)
