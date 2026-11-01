import importlib.metadata
import socket
import subprocess
import sys
import urllib.request

import pytest
from helpers import REPO
from pytest_socket import SocketConnectBlockedError

import odezoo


def test_version_matches_metadata():
    assert odezoo.__version__ == importlib.metadata.version("odezoo") == "0.1.0"


def test_import_does_not_load_rich():
    code = "import sys, odezoo; print('rich' in sys.modules)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False"


@pytest.mark.filterwarnings("ignore:A test tried to use socket:UserWarning")
def test_outside_network_is_blocked():
    with pytest.raises(SocketConnectBlockedError):
        socket.create_connection(("192.0.2.1", 80), timeout=1)


def test_fake_server_serves_and_records(http_server):
    url = http_server.add("/a", b"hello")
    with urllib.request.urlopen(url) as response:
        assert response.read() == b"hello"
    assert http_server.requests[0][0] == "/a"


def test_gitattributes_keeps_model_bytes():
    assert "models/** -text" in (REPO / ".gitattributes").read_text().splitlines()
