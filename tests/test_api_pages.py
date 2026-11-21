"""The API reference generator, `tools/generate_api_pages.py`"""

import importlib.util

import pytest
from helpers import REPO

pytest.importorskip("griffe", reason="griffe reads the source for the API reference")
_spec = importlib.util.spec_from_file_location(
    "generate_api_pages", REPO / "tools" / "generate_api_pages.py"
)
assert _spec is not None and _spec.loader is not None
api_pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api_pages)


@pytest.fixture
def pages(tmp_path):
    written = api_pages.write_pages(tmp_path)
    return {p.name: p.read_text(encoding="utf-8") for p in written}


def test_one_page_per_documented_module(pages):
    assert sorted(pages) == ["odezoo.api.md", "odezoo.errors.md", "odezoo.schema.md"]


def test_api_page_documents_the_functions_and_their_parameters(pages):
    text = pages["odezoo.api.md"]
    for name in ("models", "model", "search", "values", "get"):
        assert f"## `{name}`" in text
    assert "`registry`" in text and "**Raises**" in text


def test_schema_page_documents_the_dataclasses(pages):
    text = pages["odezoo.schema.md"]
    assert all(f"## `{name}`" in text for name in ("Model", "Version", "Source", "Paper"))


def test_imported_names_are_not_documented_twice(pages):
    assert "## `Model`" not in pages["odezoo.api.md"]


def test_errors_page_names_each_error(pages):
    text = pages["odezoo.errors.md"]
    assert all(f"## `{n}`" in text for n in ("OdezooError", "ModelNotFound", "FetchError"))
