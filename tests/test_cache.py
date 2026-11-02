import os
from pathlib import Path

from helpers import CELLML_BYTES, CELLML_SHA

from odezoo.cache import Cache, cache_dir, default_cache_dir, write_atomically

H = Path("/h")


def test_default_linux():
    assert default_cache_dir(environ={}, platform="linux", home=H) == H / ".cache/odezoo"
    xdg = default_cache_dir(environ={"XDG_CACHE_HOME": "/x"}, platform="linux", home=H)
    assert xdg == Path("/x/odezoo")
    relative = default_cache_dir(environ={"XDG_CACHE_HOME": "rel"}, platform="linux", home=H)
    assert relative == H / ".cache/odezoo"


def test_default_macos():
    assert default_cache_dir(environ={}, platform="darwin", home=H) == H / "Library/Caches/odezoo"


def test_default_windows():
    local = default_cache_dir(environ={"LOCALAPPDATA": "/L"}, platform="win32", home=H)
    assert local == Path("/L/odezoo/Cache")
    fallback = default_cache_dir(environ={}, platform="win32", home=H)
    assert fallback == H / "AppData/Local/odezoo/Cache"


def test_cache_dir_precedence(monkeypatch, tmp_path):
    monkeypatch.setenv("ODEZOO_CACHE_DIR", str(tmp_path / "env"))
    assert cache_dir(tmp_path / "flag") == tmp_path / "flag"
    assert cache_dir() == tmp_path / "env"


def test_write_read_and_layout(tmp_path):
    c = Cache(tmp_path)
    p = c.write(CELLML_SHA, ".cellml", CELLML_BYTES)
    assert p == tmp_path / "sha256" / CELLML_SHA[:2] / f"{CELLML_SHA}.cellml"
    assert c.read(CELLML_SHA, ".cellml") == CELLML_BYTES
    assert sorted(x.name for x in p.parent.iterdir()) == [p.name]  # no temporary file left


def test_corrupt_entry_is_deleted(tmp_path):
    c = Cache(tmp_path)
    p = c.path_for(CELLML_SHA, ".cellml")
    p.parent.mkdir(parents=True)
    p.write_bytes(b"wrong")
    assert c.read(CELLML_SHA, ".cellml") is None and not p.exists()


def test_clear_removes_only_odezoo_files(tmp_path):
    c = Cache(tmp_path)
    c.write(CELLML_SHA, ".cellml", CELLML_BYTES)
    (tmp_path / "http/myproject").mkdir(parents=True)
    (tmp_path / "http/myproject/index.html").write_text("someone's site")
    (tmp_path / "sha256/notes.txt").write_text("mine")
    (tmp_path / "mine.txt").write_text("keep")
    assert c.clear() == 1
    assert not c.path_for(CELLML_SHA, ".cellml").exists()
    for kept in ("http/myproject/index.html", "sha256/notes.txt", "mine.txt"):
        assert (tmp_path / kept).exists(), kept


def test_writing_leaves_the_umask_alone(monkeypatch, tmp_path):
    # The umask is process-wide: setting it even briefly changes the mode of files that other
    # threads create meanwhile.
    def set_umask(mask: int) -> int:
        raise AssertionError("write_atomically set the umask")

    monkeypatch.setattr(os, "umask", set_umask)
    write_atomically(tmp_path / "new.cellml", b"x")
    assert (tmp_path / "new.cellml").read_bytes() == b"x"


def test_corrupt_entry_that_cannot_be_deleted_is_a_miss(monkeypatch, tmp_path):
    c = Cache(tmp_path)
    p = c.path_for(CELLML_SHA, ".cellml")
    p.parent.mkdir(parents=True)
    p.write_bytes(b"wrong")

    def refuse(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError(f"read-only: {self}")

    monkeypatch.setattr(Path, "unlink", refuse)
    assert c.read(CELLML_SHA, ".cellml") is None
