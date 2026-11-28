"""The model page generator, `tools/generate_model_pages.py`"""

import importlib.util
import json
from dataclasses import replace
from datetime import date

from helpers import REPO, make_model

from odezoo.registry import Registry
from odezoo.schema import Paper, model_to_dict

_spec = importlib.util.spec_from_file_location(
    "generate_model_pages", REPO / "tools" / "generate_model_pages.py"
)
assert _spec is not None and _spec.loader is not None
model_pages = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(model_pages)

COMMIT = "0123456789abcdef0123456789abcdef01234567"
br = make_model()
endo, epi = (
    make_model(
        id=f"tentusscher_2006_{v}", name=f"ten Tusscher 2006, {v}", family="tentusscher_2006"
    )
    for v in ("endo", "epi")
)
_first = br.versions[0]
bare = replace(
    make_model(id="bare_2000", name="Bare 2000", species=None, cell_type=None, keywords=[]),
    paper=Paper(title="A model", authors=("Doe J",), journal="J", year=2000, pubmed=1),
    default_version=None,
    versions=(
        replace(_first, file=None, notes="steps | stairs"),
        replace(
            _first,
            id="v1",
            sha256="1" * 64,
            file="v1.cellml",
            source=None,
            derived_from="pmr-cb090c9",
        ),
    ),
)


def registry(*models, commit=COMMIT) -> Registry:
    return Registry(models={m.id: m for m in models}, commit=commit)


def page(model, reg=None) -> str:
    return model_pages.model_page(model, reg or registry(br, endo, epi, bare))


def test_slug():
    assert model_pages.slug("tentusscher_2006_epi") == "tentusscher-2006-epi"


def test_page_has_the_paper_and_its_links():
    text = page(br)
    assert text.startswith('---\ntitle: "Beeler–Reuter 1977"\n---\n')
    # The citation links to the DOI; references.bib lets mystmd resolve it without doi.org.
    assert "Reuter H (1977). Reconstruction" in text
    assert "](https://doi.org/10.1113/jphysiol.1977.sp011853)" in text
    assert "- **DOI**: `10.1113/jphysiol.1977.sp011853`" in text
    assert "https://pubmed.ncbi.nlm.nih.gov/874889/" in text


def test_bibtex_has_one_entry_per_doi():
    shared = replace(br.paper, title="Fast & slow")
    reg = registry(replace(endo, paper=shared), replace(epi, paper=shared), bare)
    text = model_pages.bibtex(reg)
    assert text.count("@article{") == 1  # the family shares a paper; bare has no DOI
    assert "@article{tentusscher_2006_endo," in text
    assert "author = {Beeler, G. W. and Reuter, H.}" in text
    assert "title = {Fast \\& slow}" in text
    assert "doi = {10.1113/jphysiol.1977.sp011853}" in text


def test_page_names_the_rest_of_the_family():
    text = page(endo)
    assert "[tentusscher_2006_epi](./tentusscher_2006_epi.md)" in text
    assert "[tentusscher_2006_endo]" not in text


def test_missing_fields_leave_no_empty_rows():
    text = page(bare)
    for label in ("DOI", "Family", "Species", "Cell type", "Keywords"):
        assert f"**{label}**" not in text


def test_versions_table_links_the_mirror_at_the_commit():
    text = page(br)
    mirror = (
        "https://raw.githubusercontent.com/ComputationalPhysiology/odezoo/"
        f"{COMMIT}/models/beeler_reuter_1977/pmr-cb090c9.cellml"
    )
    assert f"]({mirror})" in text
    assert br.versions[0].source.page_url() in text


def test_no_mirror_link_without_a_commit_or_a_kept_file():
    assert "raw.githubusercontent.com" not in page(br, registry(br, commit=None))
    text = page(bare)
    assert text.count("raw.githubusercontent.com") == 1  # only v1 is kept
    assert "this repository" in text  # v1 has no upstream source


def test_fetch_command_is_a_code_block():
    assert "```\nodezoo fetch beeler_reuter_1977 --version pmr-cb090c9\n```" in page(br)


def test_a_pipe_in_a_note_is_escaped():
    assert "steps \\| stairs" in page(bare)


def test_derived_from_and_notes_columns_only_when_used():
    assert "Derived from" not in page(br) and "Notes" not in page(br)
    assert "Derived from" in page(bare) and "Notes" in page(bare)


def test_search_data():
    [item] = model_pages.search_data(registry(br), "/odezoo")
    assert item == {
        "id": "beeler_reuter_1977",
        "name": "Beeler–Reuter 1977",
        "url": "/odezoo/beeler-reuter-1977",
        "year": 1977,
        "authors": ["Beeler GW", "Reuter H"],
        "family": None,
        "keywords": ["cardiac", "ventricular myocyte"],
        "categories": ["electrophysiology"],
        "species": "canine",
        "cell_type": "ventricular myocyte",
        "formats": ["cellml"],
        "reviewed": True,
    }


def test_write_pages_writes_one_page_per_model_and_the_search_page(tmp_path):
    reg = registry(br, endo, epi, bare)
    data = {"schema": 1, "commit": COMMIT, "built": date(2026, 11, 21).isoformat(),
            "models": [model_to_dict(m) for m in reg.models.values()]}  # fmt: skip
    registry_json = tmp_path / "registry.json"
    registry_json.write_text(json.dumps(data, default=str), encoding="utf-8")
    docs = tmp_path / "docs"
    written = model_pages.write_pages(registry_json, docs, "/odezoo")
    assert sorted(p.name for p in (docs / "models").iterdir()) == sorted(
        f"{id}.md" for id in reg.models
    )
    search = (docs / "search.md").read_text(encoding="utf-8")
    assert ":::{anywidget} ./_static/search.mjs" in search
    body = search.split(":::{anywidget} ./_static/search.mjs\n")[1].split("\n:::")[0]
    assert [m["id"] for m in json.loads(body)["models"]] == sorted(reg.models)
    assert len(written) == len(reg.models) + 3
    assert (docs / "simulations.md").exists()
    assert "@article{" in (docs / "references.bib").read_text(encoding="utf-8")


def outcome(model_id, status="ok", stage=None, error=None, figure=None):
    return {"id": model_id, "version": "pmr-cb090c9", "status": status, "stage": stage,
            "error": error, "seconds": 2.5, "figure": figure}  # fmt: skip


def test_read_status(tmp_path):
    assert model_pages.read_status(None) is None
    assert model_pages.read_status(tmp_path) is None
    status = {"models": {"beeler_reuter_1977": outcome("beeler_reuter_1977")}}
    (tmp_path / "status.json").write_text(json.dumps(status), encoding="utf-8")
    assert model_pages.read_status(tmp_path) == status["models"]


def test_section_ok_has_the_figure():
    status = {br.id: outcome(br.id, figure=f"{br.id}.png")}
    text = "\n".join(model_pages.simulation_section(br, status))
    assert text.startswith("## Simulation")
    assert f"![Simulation of {br.id}](../simulations/{br.id}.png)" in text
    assert "`pmr-cb090c9`" in text


def test_section_failure_is_a_warning_with_the_error():
    status = {br.id: outcome(br.id, "failed", "codegen", "NameError: `x` is not defined")}
    text = "\n".join(model_pages.simulation_section(br, status))
    assert ":::{warning}" in text and "codegen" in text
    assert "NameError" in text and "![" not in text
    # The error sits in a code span that its own backticks cannot end.
    assert "`` NameError: `x` is not defined ``" in text


def test_section_timeout():
    status = {br.id: outcome(br.id, "timeout", None, "stopped after 300 s")}
    text = "\n".join(model_pages.simulation_section(br, status))
    assert ":::{warning}" in text and "time limit" in text


def test_section_without_status():
    for status in (None, {}):
        text = "\n".join(model_pages.simulation_section(br, status))
        assert ":::{note}" in text and "did not run" in text


def test_section_mentions_the_calcium_input_for_contraction_models():
    land = make_model(id="land_2017", categories=["myofilament_mechanics"])
    status = {land.id: outcome(land.id, figure="land_2017.png")}
    assert "transient" in "\n".join(model_pages.simulation_section(land, status))


def test_model_page_has_the_section():
    assert "## Simulation" in model_pages.model_page(br, registry(br), None)


def test_simulations_page_lists_failures_first():
    reg = registry(br, endo, epi)
    status = {
        br.id: outcome(br.id, figure="x.png"),
        endo.id: outcome(endo.id, "timeout", None, "stopped"),
        epi.id: outcome(epi.id, "failed", "load", "bad"),
    }
    text = model_pages.simulations_page(reg, status)
    assert text.startswith("---\ntitle: Simulations\n---")
    assert "1 ok, 1 failed, 1 timed out" in text
    rows = [line for line in text.splitlines() if line.startswith("| [")]
    assert [r.split("]")[0][3:] for r in rows] == [epi.id, endo.id, br.id]
    assert f"[{br.id}](./models/{br.id}.md)" in text


def test_simulations_page_without_status():
    text = model_pages.simulations_page(registry(br), None)
    assert "did not run" in text
