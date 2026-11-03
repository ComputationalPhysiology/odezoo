"""The one HTTP client odezoo uses: polite to the hosts it downloads from

Requests to one host are spaced out, and only "slow down" answers (429, 503) are retried, so
odezoo never hammers PMR, GitHub, Zenodo or NCBI, and is not blocked by them.
"""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

from ._version import __version__
from .errors import OdezooError

USER_AGENT = f"odezoo/{__version__} (+https://github.com/ComputationalPhysiology/odezoo)"
DEFAULT_INTERVAL = 1.0  # seconds between requests to one host
HOST_INTERVALS: Mapping[str, float] = {"raw.githubusercontent.com": 0.2}  # the mirror
TIMEOUT = 30.0
RETRY_STATUSES = frozenset({429, 503})
RETRY_WAITS = (2.0, 4.0, 8.0)
MAX_RETRY_AFTER = 60.0


class HttpError(OdezooError):
    """A download failed: an HTTP error status, or no answer at all

    Parameters
    ----------
    url : str
        The URL that was asked for
    status : int | None
        The HTTP status, or None if there was no HTTP answer
    reason : str
        A short reason, such as `HTTP 404` or the network error
    """

    def __init__(self, url: str, status: int | None, reason: str):
        self.url = url
        self.status = status
        self.reason = reason
        super().__init__(f"{url}: {reason}")


class Http:
    """An HTTP client that spaces out requests to each host and retries "slow down" answers

    Parameters
    ----------
    default_interval : float, optional
        Seconds between requests to one host, by default 1.0
    host_intervals : Mapping[str, float], optional
        Other intervals for some hosts, by default 0.2 seconds for the GitHub mirror
    timeout : float, optional
        Seconds to wait for a host to answer, by default 30.0
    clock : Callable[[], float], optional
        The clock intervals are measured with, by default `time.monotonic`
    sleep : Callable[[float], None], optional
        How to wait, by default `time.sleep`
    """

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
        """Wait `seconds`, if that is more than nothing

        Parameters
        ----------
        seconds : float
            How long to wait; zero or less returns at once
        """
        if seconds > 0:
            self._sleep(seconds)

    def _space(self, host: str) -> None:
        """Wait until the host's interval has passed since the last request to it

        Parameters
        ----------
        host : str
            The host the next request goes to
        """
        last = self._last.get(host)
        if last is not None:
            interval = self.host_intervals.get(host, self.default_interval)
            self._pause(last + interval - self.clock())
        self._last[host] = self.clock()

    @staticmethod
    def _retry_wait(retry_after: str | None, attempt: int) -> float:
        """Return how long to wait before retrying a "slow down" answer

        Parameters
        ----------
        retry_after : str | None
            The answer's Retry-After header, if it has one
        attempt : int
            How many retries there have been already, from 0

        Returns
        -------
        float
            The header's seconds, at most 60, if it gives seconds; else 2, 4 or 8 seconds for
            the first, second and third retry
        """
        if retry_after is not None and retry_after.strip().isdigit():
            return min(float(retry_after), MAX_RETRY_AFTER)
        return RETRY_WAITS[attempt]

    def get(self, url: str, *, accept: str | None = None) -> bytes:
        """Download `url`

        A 429 or 503 answer is retried up to three times; any other failure is final.

        Parameters
        ----------
        url : str
            The URL
        accept : str, optional
            The `Accept` header, such as `application/json`; by default none is sent

        Returns
        -------
        bytes
            The body

        Raises
        ------
        HttpError
            If the download fails, with the status or the network error as the reason
        """
        host = urlsplit(url).hostname or ""
        headers = {"User-Agent": USER_AGENT}
        if accept is not None:
            headers["Accept"] = accept
        request = urllib.request.Request(url, headers=headers)
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
            except (http.client.HTTPException, ValueError) as e:
                # A body cut short (IncompleteRead), or a URL urllib refuses (InvalidURL).
                raise HttpError(url, None, f"{type(e).__name__}: {e}") from None
        raise AssertionError("unreachable: the last attempt returns or raises")


_client: Http | None = None


def client() -> Http:
    """Return the process-wide client, so request spacing holds across every download in a run

    Returns
    -------
    Http
        The client, made on the first call
    """
    global _client
    if _client is None:
        _client = Http()
    return _client
