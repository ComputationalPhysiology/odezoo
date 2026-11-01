from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from helpers import CELLML_BYTES, FakeServer, make_model, write_checkout

import odezoo.http
from odezoo.http import Http
from odezoo.schema import Source

LOCALHOST = ["127.0.0.1", "::1"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tests may only connect to localhost, unless they are marked `network`

    pytest-socket applies the `allow_hosts` marker in its own setup, so a stray request to PMR
    or GitHub fails the test instead of leaving the machine.
    """
    for item in items:
        if item.get_closest_marker("network") is None:
            item.add_marker(pytest.mark.allow_hosts(LOCALHOST))


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Plain, wide output, and no test touches the real cache or a registry set by the user"""
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("ODEZOO_REGISTRY", raising=False)
    monkeypatch.setenv("ODEZOO_CACHE_DIR", str(tmp_path / "user-cache"))


@pytest.fixture(autouse=True)
def fast_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """The process-wide client, without request spacing: tests talk to one local server"""
    monkeypatch.setattr(odezoo.http, "_client", Http(default_interval=0.0, host_intervals={}))


@pytest.fixture
def http_server() -> Iterator[FakeServer]:
    server = FakeServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A registry checkout holding the Beeler–Reuter test model and its CellML file"""
    return write_checkout(tmp_path / "reg", [(make_model(), {"pmr-cb090c9.cellml": CELLML_BYTES})])


@pytest.fixture
def remote_checkout(http_server: FakeServer, tmp_path: Path) -> Path:
    """A checkout whose one version is not kept in it: every fetch goes to the local server"""
    model = make_model()
    url = http_server.add("/up/br.cellml", CELLML_BYTES)
    version = replace(model.versions[0], file=None, source=Source(type="url", url=url))
    return write_checkout(tmp_path / "remote", [(replace(model, versions=(version,)), {})])
