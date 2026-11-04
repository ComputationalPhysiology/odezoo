from datetime import date

import pytest
from helpers import CELLML_BYTES, run

from odezoo.errors import RegistryError
from odezoo.http import Http
from odezoo.maintain.url import add_url, url_source
from odezoo.registry import read_model

C = "581e711a300357e867319e7e67151ff7c834db12"
PMR = "https://models.physiomeproject.org"
BR = "models/beeler_reuter_1977"
OTHER_CELLML = (
    b'<?xml version="1.0"?>\n<model xmlns="http://www.cellml.org/cellml/1.0#" name="other"/>\n'
)
IMPORTING_CELLML = (
    b'<?xml version="1.0"?>\n<model xmlns="http://www.cellml.org/cellml/1.1#" '
    b'xmlns:xlink="http://www.w3.org/1999/xlink" name="m">'
    b'<import xlink:href="other.cellml"/></model>\n'
)
TODAY = date(2026, 11, 3)


class NoRequests(Http):
    """An `Http` that fails the test if it is asked for anything"""

    def get(self, url: str, *, accept: str | None = None) -> bytes:
        raise AssertionError(f"unexpected request for {url}")


FAIL = NoRequests()


@pytest.fixture
def empty_checkout(tmp_path):
    (tmp_path / "reg/models").mkdir(parents=True)
    (tmp_path / "reg/LICENSES").mkdir()
    return tmp_path / "reg"


def http() -> Http:
    return Http(default_interval=0)


def model_files(root) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in (root / "models").rglob("*")
            if p.is_file()}  # fmt: skip


# --- url_source -------------------------------------------------------------------------------


def test_github_blob_url_with_a_commit():
    s = url_source(f"https://github.com/jtmff/TWorld/blob/{C}/CellML/TWorld.cellml", http=FAIL)
    assert (s.type, s.repo, s.commit, s.path) == (
        "github",
        "jtmff/TWorld",
        C,
        "CellML/TWorld.cellml",
    )


def test_github_raw_url_with_a_commit():
    s = url_source(f"https://raw.githubusercontent.com/jtmff/torord/{C}/cellml/a.cellml", http=FAIL)
    assert (s.type, s.repo, s.commit, s.path) == ("github", "jtmff/torord", C, "cellml/a.cellml")


def test_github_branch_is_pinned_to_its_commit(http_server):
    http_server.add("/repos/jtmff/TWorld/commits/main", C.encode())
    s = url_source(
        "https://github.com/jtmff/TWorld/blob/main/CellML/TWorld.cellml",
        http=http(),
        api=http_server.url,
    )
    assert s.commit == C
    assert http_server.requests[0][1]["Accept"] == "application/vnd.github.sha"


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/jtmff/TWorld/raw/main/CellML/TWorld.cellml",
        "https://www.github.com/jtmff/TWorld/blob/main/CellML/TWorld.cellml",
        "https://raw.githubusercontent.com/jtmff/TWorld/refs/heads/main/CellML/TWorld.cellml",
    ],
)
def test_other_github_branch_urls_are_pinned(http_server, url):
    http_server.add("/repos/jtmff/TWorld/commits/main", C.encode())
    s = url_source(url, http=http(), api=http_server.url)
    assert (s.type, s.repo, s.commit, s.path) == (
        "github",
        "jtmff/TWorld",
        C,
        "CellML/TWorld.cellml",
    )


def test_pmr_rawfile_url():
    s = url_source(
        f"{PMR}/workspace/beeler_reuter_1977/rawfile/{C}/beeler_reuter_1977.cellml", http=FAIL
    )
    assert (s.type, s.workspace, s.commit, s.path) == (
        "pmr",
        f"{PMR}/workspace/beeler_reuter_1977",
        C,
        "beeler_reuter_1977.cellml",
    )


def test_pmr_user_workspace_and_file_url():
    s = url_source(f"{PMR}/w/andre/SAN-ORd/file/{C}/Ohara_Rudy_2011.cellml", http=FAIL)
    assert (s.workspace, s.commit, s.path) == (
        f"{PMR}/w/andre/SAN-ORd",
        C,
        "Ohara_Rudy_2011.cellml",
    )


@pytest.mark.parametrize("url", [f"{PMR}/workspace/x/rawfile/HEAD/x.cellml", f"{PMR}/e/c1"])
def test_pmr_url_without_a_commit_is_refused(url):
    with pytest.raises(RegistryError, match="pinned to a commit"):
        url_source(url, http=FAIL)


def test_zenodo_url():
    s = url_source("https://zenodo.org/records/7277154/files/m.cellml?download=1", http=FAIL)
    assert (s.type, s.record, s.filename) == ("zenodo", 7277154, "m.cellml")


def test_plain_url():
    s = url_source("https://example.org/models/m.cellml?v=2", http=FAIL)
    assert (s.type, s.url) == ("url", "https://example.org/models/m.cellml?v=2")


@pytest.mark.parametrize("url", ["ftp://x/m.cellml", "file:///m.cellml", "m.cellml"])
def test_not_http_is_refused(url):
    with pytest.raises(RegistryError, match="http"):
        url_source(url, http=FAIL)


# --- add_url ----------------------------------------------------------------------------------


def test_add_url_writes_a_model_to_fill_in(empty_checkout, http_server):
    url = http_server.add("/m.cellml", CELLML_BYTES)
    o = add_url(empty_checkout, url, id="m", http=http(), today=TODAY)
    assert (o.id, o.action, o.version) == ("m", "added model", "url-2026-11-03")
    assert "paper" in o.detail and "categories" in o.detail
    text = (empty_checkout / "models/m/model.toml").read_text(encoding="utf-8")
    assert 'id = "url-2026-11-03"' in text and "file =" not in text  # licence unknown: no copy
    assert f'url = "{url}"' in text


def test_licence_allows_a_copy(empty_checkout, http_server):
    url = http_server.add("/m.cellml", CELLML_BYTES)
    add_url(empty_checkout, url, id="m", license="MIT", http=http(), today=TODAY)
    assert (empty_checkout / "models/m/url-2026-11-03.cellml").read_bytes() == CELLML_BYTES


def test_unknown_extension_is_refused(empty_checkout, http_server):
    url = http_server.add("/m.mmt", b"x")
    with pytest.raises(RegistryError, match="mmt"):
        add_url(empty_checkout, url, id="m", http=http(), today=TODAY)
    assert http_server.requests == [] and model_files(empty_checkout) == {}


def test_import_is_refused(empty_checkout, http_server):
    url = http_server.add("/m.cellml", IMPORTING_CELLML)
    with pytest.raises(RegistryError, match="import"):
        add_url(empty_checkout, url, id="m", http=http(), today=TODAY)
    assert model_files(empty_checkout) == {}


def test_bad_model_id_is_refused(empty_checkout, http_server):
    url = http_server.add("/m.cellml", CELLML_BYTES)
    with pytest.raises(RegistryError, match="id"):
        add_url(empty_checkout, url, id="../m", http=http(), today=TODAY)
    assert model_files(empty_checkout) == {}


def test_same_file_again_is_unchanged(checkout, http_server):
    before = model_files(checkout)
    url = http_server.add("/br.cellml", CELLML_BYTES)
    o = add_url(checkout, url, id="beeler_reuter_1977", http=http(), today=TODAY)
    assert o.action == "unchanged" and model_files(checkout) == before


def test_new_file_is_added_as_a_version(checkout, http_server):
    url = http_server.add("/br.cellml", OTHER_CELLML)
    o = add_url(checkout, url, id="beeler_reuter_1977", license="CC-BY-3.0", http=http(),
                today=TODAY)  # fmt: skip
    assert o.action == "added version"
    m = read_model(checkout / BR)
    assert [v.id for v in m.versions] == ["pmr-cb090c9", "url-2026-11-03"]
    assert (checkout / BR / "url-2026-11-03.cellml").read_bytes() == OTHER_CELLML


def test_taken_version_id_with_another_file_is_refused(checkout, http_server):
    add_url(checkout, http_server.add("/a.cellml", OTHER_CELLML), id="beeler_reuter_1977",
            http=http(), today=TODAY)  # fmt: skip
    before = model_files(checkout)
    with pytest.raises(RegistryError, match="url-2026-11-03"):
        add_url(checkout, http_server.add("/b.cellml", OTHER_CELLML + b"\n"),
                id="beeler_reuter_1977", http=http(), today=TODAY)  # fmt: skip
    assert model_files(checkout) == before


def test_a_version_that_does_not_read_back_changes_nothing(checkout, http_server):
    before = model_files(checkout)
    url = http_server.add("/br.cellml", OTHER_CELLML)
    with pytest.raises(RegistryError, match="license"):
        add_url(checkout, url, id="beeler_reuter_1977", license="cc-by-3.0", http=http(),
                today=TODAY)  # fmt: skip
    assert model_files(checkout) == before


def test_a_model_being_filled_in_takes_another_version(empty_checkout, http_server):
    add_url(empty_checkout, http_server.add("/a.cellml", CELLML_BYTES), id="m", http=http(),
            today=TODAY)  # fmt: skip
    o = add_url(empty_checkout, http_server.add("/b.cellml", OTHER_CELLML), id="m", http=http(),
                today=date(2026, 11, 4))  # fmt: skip
    assert o.action == "added version"
    text = (empty_checkout / "models/m/model.toml").read_text(encoding="utf-8")
    assert "url-2026-11-03" in text and "url-2026-11-04" in text


def test_dry_run_writes_nothing(empty_checkout, http_server):
    url = http_server.add("/m.cellml", CELLML_BYTES)
    o = add_url(empty_checkout, url, id="m", http=http(), today=TODAY, dry_run=True)
    assert o.action == "added model" and model_files(empty_checkout) == {}


def test_cli_add_url(capsys, empty_checkout, http_server):
    url = http_server.add("/m.cellml", CELLML_BYTES)
    code, out, _ = run(capsys, "--registry", str(empty_checkout), "registry", "add", "url", url,
                       "--id", "m")  # fmt: skip
    assert code == 0 and "Added model m (url-" in out and "fill in" in out
    code, out, _ = run(capsys, "--registry", str(empty_checkout), "registry", "add", "url", url,
                       "--id", "m")  # fmt: skip
    assert code == 0 and "Unchanged m" in out


@pytest.mark.parametrize(
    "url", [f"{PMR}/exposure/abc", f"{PMR}/e/5f/x.cellml/view", f"{PMR}/workspace/x"]
)
def test_add_url_points_pmr_pages_to_a_file_url(empty_checkout, url):
    with pytest.raises(RegistryError, match="pinned to a commit"):
        add_url(empty_checkout, url, id="m", http=FAIL, today=TODAY)
    assert model_files(empty_checkout) == {}
