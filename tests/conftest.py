from collections.abc import Iterator
from pathlib import Path

import pytest
from helpers import CELLML_BYTES, FakeServer, make_model, write_checkout

LOCALHOST = ["127.0.0.1", "::1"]


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tests may only connect to localhost, unless they are marked `network`

    pytest-socket applies the `allow_hosts` marker in its own setup, so a stray request to PMR
    or GitHub fails the test instead of leaving the machine.
    """
    for item in items:
        if item.get_closest_marker("network") is None:
            item.add_marker(pytest.mark.allow_hosts(LOCALHOST))


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
