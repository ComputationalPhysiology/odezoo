import io
from pathlib import Path
from unittest.mock import Mock

import pytest
from helpers import CELLML_BYTES, CELLML_SHA, run
from rich.console import Console

import odezoo.api
from odezoo.cache import Cache
from odezoo.cli import main
from odezoo.render import print_fetched


def test_fetch_writes_file(capsys, checkout, tmp_path):
    code, out, _ = run(capsys, "--registry", str(checkout), "--cache-dir", str(tmp_path / "c"),
                       "fetch", "beeler_reuter_1977", "-o", str(tmp_path / "out/new"))  # fmt: skip
    written = tmp_path / "out/new/beeler_reuter_1977.cellml"
    assert code == 0 and written.read_bytes() == CELLML_BYTES
    assert "beeler_reuter_1977.cellml" in out


def test_fetch_refuses_different_file(capsys, checkout, tmp_path):
    (tmp_path / "beeler_reuter_1977.cellml").write_bytes(b"mine")
    args = ["--registry", str(checkout), "fetch", "beeler_reuter_1977", "-o", str(tmp_path)]
    code, _, err = run(capsys, *args)
    assert code == 1 and "--force" in err
    assert run(capsys, *args, "--force")[0] == 0
    assert (tmp_path / "beeler_reuter_1977.cellml").read_bytes() == CELLML_BYTES


def test_fetch_continues_after_failure(capsys, checkout, tmp_path):
    code, _, err = run(capsys, "--registry", str(checkout), "fetch", "nope",
                       "beeler_reuter_1977", "-o", str(tmp_path))  # fmt: skip
    assert code == 1 and "nope" in err and (tmp_path / "beeler_reuter_1977.cellml").exists()


def test_fetch_version_with_two_ids_is_usage_error(checkout):
    with pytest.raises(SystemExit) as e:
        main(["--registry", str(checkout), "fetch", "a", "b", "--version", "v1"])
    assert e.value.code == 2


def test_fetch_duplicates_once(capsys, checkout, tmp_path):
    out = run(capsys, "--registry", str(checkout), "fetch", "beeler_reuter_1977",
              "beeler_reuter_1977", "-o", str(tmp_path))[1]  # fmt: skip
    assert out.count("beeler_reuter_1977.cellml") == 1


def test_fetch_output_that_is_a_file(capsys, checkout, tmp_path):
    (tmp_path / "file").write_text("x")
    code, _, err = run(capsys, "--registry", str(checkout), "fetch", "beeler_reuter_1977",
                       "-o", str(tmp_path / "file"))  # fmt: skip
    assert code == 1 and "not a folder" in err


def test_no_cache_leaves_cache_empty(capsys, remote_checkout, tmp_path):
    cache = tmp_path / "c"
    args = ["--registry", str(remote_checkout), "--cache-dir", str(cache), "fetch"]
    code, _, _ = run(capsys, *args, "beeler_reuter_1977", "--no-cache", "-o", str(tmp_path / "out"))
    assert code == 0 and (tmp_path / "out/beeler_reuter_1977.cellml").exists()
    assert not [p for p in cache.rglob("*") if p.is_file()]


def test_cache_dir_flag_and_env(capsys, tmp_path, monkeypatch):
    assert run(capsys, "--cache-dir", str(tmp_path / "a"), "cache", "dir")[1].strip() == str(
        tmp_path / "a"
    )
    monkeypatch.setenv("ODEZOO_CACHE_DIR", str(tmp_path / "b"))
    assert run(capsys, "cache", "dir")[1].strip() == str(tmp_path / "b")


def test_cache_clear_counts(capsys, tmp_path):
    Cache(tmp_path).write(CELLML_SHA, ".cellml", CELLML_BYTES)
    assert "Removed 1 file" in run(capsys, "--cache-dir", str(tmp_path), "cache", "clear")[1]


def test_cache_without_subcommand_is_usage_error(capsys):
    assert run(capsys, "cache")[0] == 2


def test_ascii_fallback_on_cp1252():
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    print_fetched("beeler_reuter_1977", Path("x.cellml"), Console(file=stream, highlight=False))
    stream.flush()
    assert b"OK beeler_reuter_1977 -> x.cellml" in buffer.getvalue()


def test_ctrl_c_returns_130(monkeypatch, checkout):
    monkeypatch.setattr(odezoo.api, "get", Mock(side_effect=KeyboardInterrupt))
    assert main(["--registry", str(checkout), "fetch", "beeler_reuter_1977"]) == 130


def test_fetched_path_is_never_wrapped():
    stream = io.StringIO()
    path = Path(
        "/a/very/long/folder/name/that/is/longer/than/the/console/beeler_reuter_1977.cellml"
    )
    print_fetched("beeler_reuter_1977", path, Console(file=stream, width=40))
    assert str(path) in stream.getvalue()


def test_output_under_a_file_is_a_clean_error(capsys, checkout, tmp_path):
    (tmp_path / "a_file").write_text("x")
    args = ["--registry", str(checkout), "fetch", "beeler_reuter_1977"]
    code, _, err = run(capsys, *args, "-o", str(tmp_path / "a_file/sub"))
    assert code == 1 and "a_file" in err


def test_an_os_error_on_one_id_does_not_stop_the_rest(capsys, checkout, tmp_path, monkeypatch):
    real_get = odezoo.api.get

    def get(id, **kwargs):
        if id == "first":
            raise PermissionError(13, "Permission denied", str(tmp_path / "first.cellml"))
        return real_get(id, **kwargs)

    monkeypatch.setattr(odezoo.api, "get", get)
    args = ["--registry", str(checkout), "fetch", "first", "beeler_reuter_1977"]
    code, _, err = run(capsys, *args, "-o", str(tmp_path))
    assert code == 1 and "first" in err and "Permission denied" in err
    assert (tmp_path / "beeler_reuter_1977.cellml").exists()


def test_unusable_cache_folder_does_not_stop_a_fetch(capsys, remote_checkout, tmp_path):
    (tmp_path / "cachefile").write_text("x")
    args = ["--registry", str(remote_checkout), "--cache-dir", str(tmp_path / "cachefile")]
    code, _, _ = run(capsys, *args, "fetch", "beeler_reuter_1977", "-o", str(tmp_path / "out"))
    assert code == 0
    assert (tmp_path / "out/beeler_reuter_1977.cellml").read_bytes() == CELLML_BYTES


def test_other_filesystem_errors_are_clean(capsys, checkout, tmp_path):
    (tmp_path / "a_file").write_text("x")
    args = ["--registry", str(checkout), "registry", "build", "-o", str(tmp_path / "a_file/r.json")]
    code, _, err = run(capsys, *args)
    assert code == 1 and "a_file" in err
