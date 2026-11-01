"""Shared test helpers: a local HTTP server and, later, model fixtures"""

from __future__ import annotations

import http.server
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

Response = tuple[int, bytes, Mapping[str, str]]


class FakeServer:
    """An HTTP server on 127.0.0.1 that serves routes added by the test and records every request

    A route has a list of responses served in turn; the last one repeats. Unknown paths are 404.
    """

    def __init__(self) -> None:
        self.routes: dict[str, list[Response]] = {}
        self.served: dict[str, int] = {}
        self.requests: list[tuple[str, dict[str, str]]] = []
        self._httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def add(
        self,
        path: str,
        body: bytes = b"",
        *,
        status: int = 200,
        headers: Mapping[str, str] | None = None,
        responses: Sequence[Response] | None = None,
    ) -> str:
        self.routes[path] = list(responses) if responses else [(status, body, headers or {})]
        self.served[path] = 0
        return self.url + path

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()

    def _respond(self, path: str) -> Response:
        if path not in self.routes:
            return (404, b"not found", {})
        responses = self.routes[path]
        response = responses[min(self.served[path], len(responses) - 1)]
        self.served[path] += 1
        return response

    def _handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 (name set by BaseHTTPRequestHandler)
                server.requests.append((self.path, dict(self.headers.items())))
                status, body, headers = server._respond(self.path)
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                pass

        return Handler
