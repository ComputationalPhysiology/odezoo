import os
import stat
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from helpers import CELLML_BYTES, make_model, write_checkout

from odezoo.cache import Cache
from odezoo.errors import FetchError, OutputExistsError
from odezoo.fetch import fetch_bytes, write_output
from odezoo.http import Http
from odezoo.registry import Registry, load_checkout
from odezoo.schema import Source

MIRROR = f"/{'c' * 40}/models/beeler_reuter_1977/pmr-cb090c9.cellml"
UP = "/up/br.cellml"


def with_source(url: str):
    """The Beeler–Reuter test model, with its one version's source at `url`"""
    model = make_model()
    version = replace(model.versions[0], source=Source(type="url", url=url))
    return replace(model, versions=(version,))


@pytest.fixture
def remote(http_server):
    model = with_source(http_server.url + UP)
    reg = Registry(
        models={model.id: model}, commit="c" * 40, root=None, mirror_base=http_server.url
    )
    return SimpleNamespace(reg=reg, model=model, version=model.versions[0])


def fetch(remote, *, cache=None, reg=None):
    reg = reg or remote.reg
    return fetch_bytes(
        reg, remote.model, remote.version, cache=cache, http=Http(default_interval=0)
    )


def paths(http_server):
    return [path for path, _ in http_server.requests]


def test_mirror_first(remote, http_server):
    http_server.add(MIRROR, CELLML_BYTES)
    http_server.add(UP, CELLML_BYTES)
    data, _ = fetch(remote)
    assert data == CELLML_BYTES and paths(http_server) == [MIRROR]


def test_falls_back_after_404(remote, http_server):
    http_server.add(UP, CELLML_BYTES)
    data, _ = fetch(remote)
    assert data == CELLML_BYTES and paths(http_server) == [MIRROR, UP]


def test_hash_mismatch_moves_on(remote, http_server):
    http_server.add(MIRROR, b"x")
    http_server.add(UP, CELLML_BYTES)
    assert fetch(remote)[0] == CELLML_BYTES


def test_all_fail_lists_attempts(remote, http_server):
    http_server.add(UP, b"wrong")
    with pytest.raises(FetchError) as e:
        fetch(remote)
    sources = [a.source for a in e.value.attempts]
    assert sources == [http_server.url + MIRROR, http_server.url + UP]
    assert "404" in e.value.attempts[0].reason
    assert e.value.attempts[1].reason == "sha256 mismatch"


def test_no_commit_skips_mirror(remote, http_server):
    http_server.add(UP, CELLML_BYTES)
    fetch(remote, reg=replace(remote.reg, commit=None))
    assert paths(http_server) == [UP]


def test_cache_hit_makes_no_request(remote, http_server, tmp_path):
    http_server.add(MIRROR, CELLML_BYTES)
    cache = Cache(tmp_path)
    _, first = fetch(remote, cache=cache)
    data, second = fetch(remote, cache=cache)
    assert data == CELLML_BYTES and first == second == cache.path_for(
        remote.version.sha256, ".cellml"
    )
    assert len(http_server.requests) == 1


def test_no_cache_downloads_each_time(remote, http_server):
    http_server.add(MIRROR, CELLML_BYTES)
    _, path = fetch(remote)
    fetch(remote)
    assert path is None and len(http_server.requests) == 2


def test_checkout_file_needs_no_network(checkout):
    reg = load_checkout(checkout)
    m = reg.get("beeler_reuter_1977")
    data, path = fetch_bytes(reg, m, m.versions[0], cache=None, http=Http(default_interval=0))
    assert data == CELLML_BYTES
    assert path == checkout / "models/beeler_reuter_1977/pmr-cb090c9.cellml"


def test_checkout_file_with_wrong_hash_falls_through(http_server, tmp_path):
    model = with_source(http_server.add(UP, CELLML_BYTES))
    root = write_checkout(tmp_path, [(model, {"pmr-cb090c9.cellml": b"edited by hand"})])
    reg = load_checkout(root)
    m = reg.get(model.id)
    data, _ = fetch_bytes(reg, m, m.versions[0], cache=None, http=Http(default_interval=0))
    assert data == CELLML_BYTES and paths(http_server) == [UP]


def test_write_output_creates_folders_and_keeps_bytes(tmp_path):
    t = write_output(b"a\r\nb\n", tmp_path / "new/dir/m.cellml")
    assert t.read_bytes() == b"a\r\nb\n"
    assert [p.name for p in t.parent.iterdir()] == ["m.cellml"]  # no temporary file left


def test_write_output_same_bytes_is_fine(tmp_path):
    t = write_output(b"a", tmp_path / "m.ode")
    assert write_output(b"a", t) == t


def test_write_output_refuses_then_forces(tmp_path):
    t = write_output(b"a", tmp_path / "m.ode")
    with pytest.raises(OutputExistsError, match="--force"):
        write_output(b"b", t)
    assert write_output(b"b", t, force=True).read_bytes() == b"b"


def test_truncated_mirror_falls_back_to_upstream(remote, http_server):
    http_server.add(MIRROR, b"<?xml", headers={"Content-Length": "500"})
    http_server.add(UP, CELLML_BYTES)
    data, _ = fetch(remote)
    assert data == CELLML_BYTES and paths(http_server) == [MIRROR, UP]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")
def test_written_files_follow_the_umask(tmp_path):
    old = os.umask(0o022)
    try:
        t = write_output(b"a", tmp_path / "m.ode")
        assert stat.S_IMODE(t.stat().st_mode) == 0o644
        t.chmod(0o640)
        write_output(b"b", t, force=True)
        assert stat.S_IMODE(t.stat().st_mode) == 0o640
    finally:
        os.umask(old)
