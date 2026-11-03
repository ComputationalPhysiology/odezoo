from dataclasses import replace

from helpers import CELLML_BYTES, CELLML_SHA, make_model, run, write_checkout

from odezoo.http import Http
from odezoo.maintain.upstream import Checked, check_upstream, new_since, upstream_versions
from odezoo.registry import Registry
from odezoo.schema import Source, model_to_dict

MODEL = "beeler_reuter_1977"


def with_url_sources(*urls: str):
    """The Beeler–Reuter test model with one version per URL, each from that URL, without a copy"""
    model = make_model(default_version=None)
    first = model.versions[0]
    versions = tuple(
        replace(
            first,
            id=f"url-{i}",
            sha256=CELLML_SHA if i == 0 else f"{i:064x}",
            file=None,
            source=Source(type="url", url=url),
        )
        for i, url in enumerate(urls)
    )
    return replace(model, versions=versions)


def registry(*models) -> Registry:
    return Registry(models={m.id: m for m in models})


def check(model) -> list[Checked]:
    return check_upstream(upstream_versions(registry(model)), http=Http(default_interval=0))


def test_matching_source_has_no_problem(http_server):
    url = http_server.add("/m.cellml", CELLML_BYTES)
    assert check(with_url_sources(url)) == [Checked(MODEL, "url-0", url, None)]


def test_changed_file_is_a_sha256_mismatch(http_server):
    url = http_server.add("/m.cellml", b"changed upstream")
    assert check(with_url_sources(url))[0].problem == "sha256 mismatch"


def test_404_is_reported_with_its_reason(http_server):
    assert check(with_url_sources(http_server.url + "/gone.cellml"))[0].problem == "HTTP 404"


def test_versions_without_a_source_are_skipped():
    model = make_model()
    only_a_copy = replace(model, versions=(replace(model.versions[0], source=None),))
    assert upstream_versions(registry(only_a_copy)) == []


def test_new_since_lists_only_added_versions():
    model = with_url_sources("https://example.org/a.cellml", "https://example.org/b.cellml")
    old_model = replace(model, versions=model.versions[:1])
    old = {"schema": 1, "models": [model_to_dict(old_model)]}
    assert [(m.id, v.id) for m, v in new_since(registry(model), old)] == [(MODEL, "url-1")]


def test_cli_upstream_fails_on_a_mismatch(capsys, http_server, tmp_path):
    model = with_url_sources(http_server.add("/m.cellml", b"changed upstream"))
    root = write_checkout(tmp_path / "reg", [(model, {})])
    code, out, _ = run(capsys, "--registry", str(root), "registry", "upstream")
    assert code == 1 and "sha256 mismatch" in out and "1 failed" in out


def test_cli_upstream_with_nothing_new(capsys, checkout, tmp_path):
    old = str(tmp_path / "old.json")
    run(capsys, "--registry", str(checkout), "registry", "build", "-o", old)
    # The checkout's source is on PMR, which the socket guard would refuse: no request is made.
    code, out, _ = run(capsys, "--registry", str(checkout), "registry", "upstream", "--new-since",
                       old)  # fmt: skip
    assert code == 0 and "No upstream versions to check" in out
