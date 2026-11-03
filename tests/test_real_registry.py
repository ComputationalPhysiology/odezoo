"""The registry in this repository: it must pass its own check, and match its sources"""

import hashlib
from datetime import date

import pytest
from helpers import REPO

from odezoo.fetch import fetch_bytes
from odezoo.http import Http
from odezoo.maintain.check import check
from odezoo.registry import build, from_json, load_checkout


def test_real_registry_passes_check():
    report = check(REPO)
    assert report.ok, report.errors


def test_beeler_reuter_matches_the_survey():
    m = load_checkout(REPO).get("beeler_reuter_1977")
    assert (
        m.versions[0].sha256 == "f9bcc643f7a9e85f56176521cc08b86c00a14b66bd0c14be1a8f05a956818274"
    )


@pytest.mark.network
def test_upstream_pmr_serves_the_same_bytes():
    reg = from_json(build(REPO, commit=None, built=date.today()))  # no commit → upstream only
    m = reg.get("beeler_reuter_1977")
    data, _ = fetch_bytes(reg, m, m.versions[0], cache=None, http=Http())
    assert hashlib.sha256(data).hexdigest() == m.versions[0].sha256


def test_seed_models():
    models = load_checkout(REPO).models
    assert len(models) == 41
    for family in ("tentusscher_2004", "tentusscher_2006", "sakmann_2000"):
        assert sorted(m.id for m in models.values() if m.family == family) == [
            f"{family}_endo",
            f"{family}_epi",
            f"{family}_m",
        ]
    assert [m.id for m in models.values() if not m.reviewed] == ["puglisi_bers_2001"]
    assert models["tworld"].versions[0].license == "MIT"
    assert models["torord_dyn_cl"].versions[0].license == "GPL-3.0-only"
    assert "Marbán E" in models["winslow_1999"].paper.authors
    assert models["noble_1998"].paper.pubmed == 9487284
