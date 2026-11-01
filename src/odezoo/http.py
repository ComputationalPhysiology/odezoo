"""The one HTTP client odezoo uses: polite to the hosts it downloads from

Requests to one host are spaced out, and only "slow down" answers (429, 503) are retried, so
odezoo never hammers PMR, GitHub, Zenodo or NCBI, and is not blocked by them.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from odezoo import __version__
from odezoo.errors import OdezooError

USER_AGENT = f"odezoo/{__version__} (+https://github.com/ComputationalPhysiology/odezoo)"
DEFAULT_INTERVAL = 1.0  # seconds between requests to one host
HOST_INTERVALS: Mapping[str, float] = {"raw.githubusercontent.com": 0.2}  # the mirror
TIMEOUT = 30.0
RETRY_STATUSES = frozenset({429, 503})
RETRY_WAITS = (2.0, 4.0, 8.0)
MAX_RETRY_AFTER = 60.0


class HttpError(OdezooError):
    def __init__(self, url: str, status: int | None, reason: str):
        self.url = url
        self.status = status
        self.reason = reason
        super().__init__(f"{url}: {reason}")


class Http:
    def __init__(
        self,
        *,
        default_interval: float = DEFAULT_INTERVAL,
        host_intervals: Mapping[str, float] = HOST_INTERVALS,
        timeout: float = TIMEOUT,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.default_interval = default_interval
        self.host_intervals = dict(host_intervals)
        self.timeout = timeout
        self.clock = clock
        self._sleep = sleep
        self._last: dict[str, float] = {}

    def _pause(self, seconds: float) -> None:
        if seconds > 0:
            self._sleep(seconds)

    def _space(self, host: str) -> None:
        """Wait until the host's interval has passed since the last request to it"""
        last = self._last.get(host)
        if last is not None:
            interval = self.host_intervals.get(host, self.default_interval)
            self._pause(last + interval - self.clock())
        self._last[host] = self.clock()

    @staticmethod
    def _retry_wait(retry_after: str | None, attempt: int) -> float:
        if retry_after is not None and retry_after.strip().isdigit():
            return min(float(retry_after), MAX_RETRY_AFTER)
        return RETRY_WAITS[attempt]

    def get(self, url: str) -> bytes:
        host = urlsplit(url).hostname or ""
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        for attempt in range(len(RETRY_WAITS) + 1):
            self._space(host)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as e:
                status, retry_after = e.code, e.headers.get("Retry-After")
                e.close()
                if status in RETRY_STATUSES and attempt < len(RETRY_WAITS):
                    self._pause(self._retry_wait(retry_after, attempt))
                    continue
                raise HttpError(url, status, f"HTTP {status}") from None
            except urllib.error.URLError as e:
                raise HttpError(url, None, str(e.reason)) from None
            except (TimeoutError, OSError) as e:
                raise HttpError(url, None, str(e) or type(e).__name__) from None
        raise AssertionError("unreachable: the last attempt returns or raises")


_client: Http | None = None


def client() -> Http:
    """The process-wide client, so request spacing holds across every download in a run"""
    global _client
    if _client is None:
        _client = Http()
    return _client
