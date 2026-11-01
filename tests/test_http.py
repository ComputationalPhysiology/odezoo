import socket

import pytest

from odezoo.http import USER_AGENT, Http, HttpError, client


class FakeClock:
    """A clock that only moves when something sleeps, recording every sleep"""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_get_returns_body_and_user_agent(http_server):
    url = http_server.add("/x", b"body")
    assert Http(default_interval=0).get(url) == b"body"
    assert http_server.requests[0][1]["User-Agent"] == USER_AGENT
    assert USER_AGENT.startswith("odezoo/")


def test_same_host_is_spaced(http_server):
    c = FakeClock()
    h = Http(default_interval=1.0, host_intervals={}, clock=c, sleep=c.sleep)
    url = http_server.add("/x", b"")
    h.get(url)
    h.get(url)
    assert c.slept == [1.0]


def test_host_interval_override(http_server):
    c = FakeClock()
    h = Http(host_intervals={"127.0.0.1": 0.2}, clock=c, sleep=c.sleep)
    url = http_server.add("/x", b"")
    h.get(url)
    h.get(url)
    assert c.slept == [0.2]


def test_retry_after_on_429(http_server):
    c = FakeClock()
    h = Http(default_interval=0, clock=c, sleep=c.sleep)
    url = http_server.add("/x", responses=[(429, b"", {"Retry-After": "5"}), (200, b"ok", {})])
    assert h.get(url) == b"ok"
    assert c.slept == [5.0]


def test_retry_after_is_capped(http_server):
    c = FakeClock()
    h = Http(default_interval=0, clock=c, sleep=c.sleep)
    url = http_server.add("/x", responses=[(429, b"", {"Retry-After": "3600"}), (200, b"ok", {})])
    h.get(url)
    assert c.slept == [60.0]


def test_503_backs_off_then_gives_up(http_server):
    c = FakeClock()
    h = Http(default_interval=0, clock=c, sleep=c.sleep)
    url = http_server.add("/x", status=503)
    with pytest.raises(HttpError) as e:
        h.get(url)
    assert e.value.status == 503 and c.slept == [2.0, 4.0, 8.0]
    assert len(http_server.requests) == 4


def test_404_is_not_retried(http_server):
    with pytest.raises(HttpError) as e:
        Http(default_interval=0).get(http_server.url + "/missing")
    assert e.value.status == 404 and e.value.reason == "HTTP 404"
    assert len(http_server.requests) == 1


def test_refused_connection_is_http_error():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    with pytest.raises(HttpError) as e:
        Http(default_interval=0, timeout=2).get(f"http://127.0.0.1:{port}/")
    assert e.value.status is None


def test_client_is_one_per_process():
    assert client() is client()
