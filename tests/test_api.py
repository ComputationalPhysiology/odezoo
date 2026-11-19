import pytest
from helpers import CELLML_BYTES

import odezoo
from odezoo.errors import OdezooError


def test_get_returns_checkout_path(checkout):
    assert odezoo.get("beeler_reuter_1977", registry=checkout).read_bytes() == CELLML_BYTES


def test_get_into_folder(checkout, tmp_path):
    path = odezoo.get("beeler_reuter_1977", dest=tmp_path, registry=checkout)
    assert path == tmp_path / "beeler_reuter_1977.cellml"


def test_get_to_file_path(checkout, tmp_path):
    path = odezoo.get("beeler_reuter_1977", dest=tmp_path / "x.cellml", registry=checkout)
    assert path.name == "x.cellml" and path.read_bytes() == CELLML_BYTES


def test_get_without_cache_needs_dest(checkout):
    with pytest.raises(ValueError):
        odezoo.get("beeler_reuter_1977", cache=False, registry=checkout)


def test_get_caches_downloads_under_cache_dir(remote_checkout, tmp_path):
    path = odezoo.get("beeler_reuter_1977", cache_dir=tmp_path / "c", registry=remote_checkout)
    assert path.is_relative_to(tmp_path / "c" / "sha256") and path.read_bytes() == CELLML_BYTES


def test_model_and_search(checkout):
    assert odezoo.model("beeler_reuter_1977", registry=checkout).paper.year == 1977
    assert [m.id for m in odezoo.search("beeler", registry=checkout)] == ["beeler_reuter_1977"]
    assert [m.id for m in odezoo.models(registry=checkout)] == ["beeler_reuter_1977"]


def test_get_without_dest_needs_a_usable_cache(remote_checkout, tmp_path):
    (tmp_path / "cachefile").write_text("x")
    with pytest.raises(OdezooError, match="cache"):
        odezoo.get("beeler_reuter_1977", cache_dir=tmp_path / "cachefile", registry=remote_checkout)


def test_values(checkout):
    assert odezoo.values("species", registry=checkout) == {"canine": 1}
    assert odezoo.values("species", species="human", registry=checkout) == {}
