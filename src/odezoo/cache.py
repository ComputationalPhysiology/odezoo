"""The download cache: files stored under their sha256, so each is downloaded once"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
import tempfile
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
    """The platform's usual cache folder for odezoo"""
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
    """`explicit` (the --cache-dir flag), else $ODEZOO_CACHE_DIR, else the platform default"""
    if explicit is not None:
        return Path(explicit)
    if os.environ.get(ENV_VAR):
        return Path(os.environ[ENV_VAR])
    return default_cache_dir()


def _umask() -> int:
    current = os.umask(0)
    os.umask(current)
    return current


def write_atomically(path: Path, data: bytes) -> None:
    """Write `data` to `path` so that `path` never holds part of it

    The file gets the mode a plain write would give it: that of the file it replaces, or else
    0666 less the umask (mkstemp alone would make every file private to its owner).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        mode = 0o666 & ~_umask()
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


class Cache:
    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, sha256: str, ext: str) -> Path:
        return self.root / "sha256" / sha256[:2] / f"{sha256}{ext}"

    def read(self, sha256: str, ext: str) -> bytes | None:
        """The cached bytes, or None; an entry whose hash is wrong is deleted

        A cache folder that cannot be read counts as empty, so it never stops a fetch.
        """
        path = self.path_for(sha256, ext)
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if hashlib.sha256(data).hexdigest() != sha256:
            path.unlink(missing_ok=True)
            return None
        return data

    def write(self, sha256: str, ext: str, data: bytes) -> Path:
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ValueError(f"refusing to cache bytes whose sha256 is not {sha256}")
        path = self.path_for(sha256, ext)
        write_atomically(path, data)
        return path

    def clear(self) -> int:
        """Remove every file odezoo cached; return the number of files removed

        Only files named the way odezoo names them are removed, then the folders this leaves
        empty, so a --cache-dir that points at a folder with other files in it loses none of them.
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
