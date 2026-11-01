from collections.abc import Iterator

import pytest
from helpers import FakeServer

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
