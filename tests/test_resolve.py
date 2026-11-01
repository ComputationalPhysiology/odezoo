import pytest
from search_models import br, tt

from odezoo.errors import VersionNotFound
from odezoo.resolve import choose_version


def test_choose_default_version():
    assert choose_version(br).id == "pmr-cb090c9"


def test_choose_by_format_newest():
    assert choose_version(tt, format="ode").id == "v1"


def test_choose_last_without_default():
    assert choose_version(tt).id == "v1"


def test_choose_explicit():
    assert choose_version(tt, version="pmr-1").id == "pmr-1"


def test_choose_version_format_mismatch():
    with pytest.raises(VersionNotFound):
        choose_version(tt, version="pmr-1", format="ode")


def test_choose_missing_format_lists_formats():
    with pytest.raises(VersionNotFound, match="cellml"):
        choose_version(br, format="ode")
