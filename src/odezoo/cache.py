"""The download cache: files stored under their sha256, so each is downloaded once"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
import sys
from collections.abc import Mapping
from pathlib import Path

ENV_VAR = "ODEZOO_CACHE_DIR"
# The names odezoo gives cached files and their temporary files; `clear` removes only these.
ENTRY = re.compile(r"[0-9a-f]{64}\.(cellml|ode)")
TEMPORARY = re.compile(r"\.[0-9a-f]{64}\.(cellml|ode)\..+\.part")
BUCKET = re.compile(r"[0-9a-f]{2}")


def default_cache_dir(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform's usual cache folder for odezoo

    Parameters
    ----------
    environ : Mapping[str, str], optional
        The environment, by default `os.environ`
    platform : str, optional
        The platform, as `sys.platform` names it, by default the running one
    home : Path, optional
        The home folder, by default the user's

    Returns
    -------
    Path
        `odezoo/Cache` in %LOCALAPPDATA% on Windows, `~/Library/Caches/odezoo` on macOS, and
        `odezoo` in $XDG_CACHE_HOME (by default `~/.cache`) elsewhere
    """
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    home = Path.home() if home is None else home
    if platform == "win32":
        local = environ.get("LOCALAPPDATA")
        return (Path(local) if local else home / "AppData" / "Local") / "odezoo" / "Cache"
    if platform == "darwin":
        return home / "Library" / "Caches" / "odezoo"
    xdg = environ.get("XDG_CACHE_HOME", "")
    # XDG requires an absolute path and says to ignore anything else.
    return (Path(xdg) if xdg.startswith("/") else home / ".cache") / "odezoo"


def cache_dir(explicit: Path | str | None = None) -> Path:
    """Choose the cache folder: `explicit`, else $ODEZOO_CACHE_DIR, else the platform default

    Parameters
    ----------
    explicit : Path | str, optional
        A folder given on purpose, such as with --cache-dir

    Returns
    -------
    Path
        The cache folder; it need not exist yet
    """
    if explicit is not None:
        return Path(explicit)
    if os.environ.get(ENV_VAR):
        return Path(os.environ[ENV_VAR])
    return default_cache_dir()


def write_atomically(path: Path, data: bytes) -> None:
    """Write `data` to `path` so that `path` never holds part of it

    The file gets the mode a plain write would give it: that of the file it replaces, or else
    0666 less the umask. (mkstemp would make every file private to its owner, and reading the
    umask means setting it, which changes it for every thread for a moment.)

    Parameters
    ----------
    path : Path
        The file to write; its folder is made if need be
    data : bytes
        The bytes to write

    Raises
    ------
    OSError
        If the folder or the file cannot be written; no partial file is left behind
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode: int | None = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = None
    temporary = path.parent / f".{path.name}.{secrets.token_hex(8)}.part"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    fd = os.open(temporary, flags, 0o666)  # the umask applies, as for a plain write
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        if mode is not None:
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


class Cache:
    """Downloaded files, each kept as `sha256/<first two hex digits>/<sha256><ext>` in `root`

    Parameters
    ----------
    root : Path
        The cache folder; it is made when the first file is written
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, sha256: str, ext: str) -> Path:
        """Return where the file with this sha256 and extension is kept

        Parameters
        ----------
        sha256 : str
            The file's sha256, in lowercase hex
        ext : str
            The file's extension, such as `.cellml`

        Returns
        -------
        Path
            The path, whether or not the file is there
        """
        return self.root / "sha256" / sha256[:2] / f"{sha256}{ext}"

    def read(self, sha256: str, ext: str) -> bytes | None:
        """Return the cached bytes, or None; an entry whose hash is wrong is deleted

        A cache folder that cannot be read, or a wrong entry that cannot be deleted, counts as
        a miss, so the cache never stops a fetch.

        Parameters
        ----------
        sha256 : str
            The file's sha256, in lowercase hex
        ext : str
            The file's extension, such as `.cellml`

        Returns
        -------
        bytes | None
            The file's bytes, or None if they are not cached
        """
        path = self.path_for(sha256, ext)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if hashlib.sha256(data).hexdigest() != sha256:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass  # a read-only cache: the entry stays, and is never used
            return None
        return data

    def write(self, sha256: str, ext: str, data: bytes) -> Path:
        """Keep `data` in the cache

        Parameters
        ----------
        sha256 : str
            The sha256 of `data`, in lowercase hex
        ext : str
            The file's extension, such as `.cellml`
        data : bytes
            The file's bytes

        Returns
        -------
        Path
            Where the file is kept

        Raises
        ------
        ValueError
            If the sha256 of `data` is not `sha256`
        OSError
            If the file cannot be written
        """
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError(f"refusing to cache bytes whose sha256 is not {sha256}")
        path = self.path_for(sha256, ext)
        write_atomically(path, data)
        return path

    def clear(self) -> int:
        """Remove every file odezoo cached

        Only files named the way odezoo names them are removed, then the folders this leaves
        empty, so a --cache-dir that points at a folder with other files in it loses none of them.

        Returns
        -------
        int
            The number of files removed
        """
        removed = 0
        store = self.root / "sha256"
        if not store.is_dir():
            return 0
        for bucket in store.iterdir():
            if not (bucket.is_dir() and BUCKET.fullmatch(bucket.name)):
                continue
            for path in bucket.iterdir():
                ours = ENTRY.fullmatch(path.name) and path.name.startswith(bucket.name)
                if path.is_file() and (ours or TEMPORARY.fullmatch(path.name)):
                    path.unlink()
                    removed += 1
            if not any(bucket.iterdir()):
                bucket.rmdir()
        if not any(store.iterdir()):
            store.rmdir()
        return removed
