"""Shared test helpers: a local HTTP server and model fixtures"""

from __future__ import annotations

import hashlib
import http.server
import threading
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from odezoo.maintain.toml import dump_model
from odezoo.schema import Model, parse_model

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
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )

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


# --- Model fixtures ---------------------------------------------------------------------------

CELLML_BYTES = (
    b'<?xml version="1.0"?>\n<model xmlns="http://www.cellml.org/cellml/1.0#" name="br"/>\n'
)
CELLML_SHA = hashlib.sha256(CELLML_BYTES).hexdigest()
COMMIT = "cb090c96a2ce627457b14def4910ac39219b8340"


def model_dict() -> dict[str, Any]:
    """The first version of the spec's Beeler–Reuter example, as `model.toml` would parse"""
    return {
        "id": "beeler_reuter_1977",
        "name": "Beeler–Reuter 1977",
        "categories": ["electrophysiology"],
        "keywords": ["cardiac", "ventricular myocyte"],
        "species": "canine",
        "cell_type": "ventricular myocyte",
        "reviewed": True,
        "default_version": "pmr-cb090c9",
        "paper": {
            "title": "Reconstruction of the action potential of ventricular myocardial fibres",
            "authors": ["Beeler GW", "Reuter H"],
            "journal": "Journal of Physiology",
            "year": 1977,
            "doi": "10.1113/jphysiol.1977.sp011853",
            "pubmed": 874889,
        },
        "versions": [
            {
                "id": "pmr-cb090c9",
                "format": "cellml",
                "sha256": CELLML_SHA,
                "license": "CC-BY-3.0",
                "file": "pmr-cb090c9.cellml",
                "added": date(2026, 11, 1),
                "source": {
                    "type": "pmr",
                    "workspace": "https://models.physiomeproject.org/workspace/beeler_reuter_1977",
                    "commit": COMMIT,
                    "path": "beeler_reuter_1977.cellml",
                    "exposure": "https://models.physiomeproject.org/e/c1",
                },
            }
        ],
    }


def make_model(**top_level_overrides: Any) -> Model:
    data = model_dict()
    data.update(top_level_overrides)
    return parse_model(data, where="test")


def write_checkout(root: Path, models: Sequence[tuple[Model, Mapping[str, bytes]]]) -> Path:
    """A registry checkout in `root`: one folder per model with its `model.toml` and files"""
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "LICENSES").mkdir(exist_ok=True)
    (root / "LICENSES/CC-BY-3.0.txt").write_bytes(b"licence text")
    for model, files in models:
        folder = root / "models" / model.id
        folder.mkdir()
        (folder / "model.toml").write_text(dump_model(model), encoding="utf-8")
        for name, data in files.items():
            (folder / name).write_bytes(data)
    return root
