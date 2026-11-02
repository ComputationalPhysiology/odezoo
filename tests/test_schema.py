import json

import pytest
from helpers import COMMIT, make_model, model_dict

from odezoo.errors import RegistryError
from odezoo.schema import CATEGORIES, Source, model_to_dict, normalize_keyword, parse_model


def test_parse_valid_model():
    m = make_model()
    assert (m.id, m.paper.year, m.formats) == ("beeler_reuter_1977", 1977, ("cellml",))
    assert m.version("pmr-cb090c9").ext == ".cellml"


def test_source_urls():
    pmr = make_model().versions[0].source
    assert pmr is not None
    assert pmr.url_for_download() == (
        "https://models.physiomeproject.org/workspace/beeler_reuter_1977/rawfile/"
        f"{COMMIT}/beeler_reuter_1977.cellml"
    )
    assert pmr.page_url() == "https://models.physiomeproject.org/e/c1"
    gh = Source(
        type="github",
        repo="jtmff/TWorld",
        commit="581e711a300357e867319e7e67151ff7c834db12",
        path="CellML/TWorld.cellml",
    )
    assert gh.url_for_download() == (
        "https://raw.githubusercontent.com/jtmff/TWorld/"
        "581e711a300357e867319e7e67151ff7c834db12/CellML/TWorld.cellml"
    )
    assert gh.page_url().startswith("https://github.com/jtmff/TWorld/blob/581e711")
    zen = Source(type="zenodo", record=7277154, filename="m.cellml")
    assert zen.url_for_download() == "https://zenodo.org/records/7277154/files/m.cellml?download=1"


def without_copy(d, **changes):
    """Leave out the first version's copy, so that only `changes` can break a rule"""
    d["versions"][0].pop("file")
    d["versions"][0].update(changes)


@pytest.mark.parametrize(
    "mutate, field",
    [
        (lambda d: d.update(id="Beeler"), "id"),
        (lambda d: d.update(categories=["cardiac"]), "categories"),
        (lambda d: d.update(categories=[]), "categories"),
        (lambda d: d.update(keywords=["Cardiac"]), "keywords"),
        (lambda d: d.update(keywords=["a", "a"]), "keywords"),
        (lambda d: (d["paper"].pop("doi"), d["paper"].pop("pubmed")), "paper"),
        (lambda d: d.update(versions=[]), "versions"),
        (lambda d: d["versions"].append(dict(d["versions"][0])), "versions"),
        (lambda d: d["versions"][0].update(sha256="abc"), "sha256"),
        (lambda d: d["versions"][0].update(format="mmt"), "format"),
        (lambda d: d["versions"][0].update(file="other.cellml"), "file"),
        (lambda d: (d["versions"][0].pop("file"), d["versions"][0].pop("source")), "source"),
        (lambda d: d["versions"][0].update(license="unknown"), "license"),
        (lambda d: d.update(default_version="nope"), "default_version"),
        (lambda d: d["versions"][0].update(derived_from="nope"), "derived_from"),
        (lambda d: d.update(colour="red"), "colour"),
        (lambda d: d["versions"][0]["source"].update(commit="abc"), "commit"),
        (lambda d: d["versions"][0].update(added="yesterday"), "added"),
        # A trailing newline must not slip past a pattern.
        (lambda d: d.update(id="beeler_reuter_1977\n"), "id"),
        (lambda d: without_copy(d, id="pmr-cb090c9\n"), "id"),
        (lambda d: d["versions"][0].update(sha256=d["versions"][0]["sha256"] + "\n"), "sha256"),
        (lambda d: d["versions"][0]["source"].update(commit=COMMIT + "\n"), "commit"),
        # Licences are SPDX ids, written exactly.
        (lambda d: without_copy(d, license="CC BY 3.0"), "license"),
        (lambda d: without_copy(d, license="mit"), "license"),
        (lambda d: without_copy(d, license="Unknown"), "license"),
        # A DOI is the bare 10.x/... form; a date is YYYY-MM-DD, not another ISO form.
        (lambda d: d["paper"].update(doi="https://doi.org/10.1113/jphysiol.1977.sp011853"), "doi"),
        (lambda d: d["versions"][0].update(added="20261101"), "added"),
        (lambda d: d["versions"][0].update(added="2026-W44-1"), "added"),
        # Two versions with the same bytes are the same version.
        (
            lambda d: d["versions"].append({**d["versions"][0], "id": "v1", "file": "v1.cellml"}),
            "sha256",
        ),
    ],
)
def test_invalid_model_names_file_and_field(mutate, field):
    d = model_dict()
    mutate(d)
    with pytest.raises(RegistryError) as e:
        parse_model(d, where="models/x/model.toml")
    assert "models/x/model.toml" in str(e.value) and field in str(e.value)


def test_model_to_dict_round_trips():
    m = make_model()
    d = model_to_dict(m)
    json.dumps(d)
    assert d["versions"][0]["added"] == "2026-11-01"
    assert parse_model(d, where="x") == m


def test_normalize_keyword():
    assert normalize_keyword("  Ventricular   Myocyte ") == "ventricular myocyte"


def test_categories_are_pmrs_twenty():
    assert len(CATEGORIES) == 20 and "cardiovascular_circulation" in CATEGORIES


@pytest.mark.parametrize("license", ["unknown", "CC-BY-3.0", "LicenseRef-PMR", "GPL-2.0+"])
def test_licences_that_are_allowed(license):
    d = model_dict()
    d["versions"][0].pop("file")
    d["versions"][0]["license"] = license
    assert parse_model(d, where="x").versions[0].license == license
