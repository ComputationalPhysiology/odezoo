"""Write a page for every model, and the search page, from a built `registry.json`

    odezoo --registry . registry build -o registry.json
    python tools/simulate_models.py registry.json models docs/simulations
    BASE_URL=/odezoo python tools/generate_model_pages.py registry.json docs docs/simulations

`docs/models/<id>.md` holds a model's paper, details, versions, the command that fetches each
version and its simulation (from `docs/simulations/`, which `tools/simulate_models.py` writes);
`docs/search.md` holds the search widget, with every model inline; `docs/simulations.md` lists
every model's simulation, failures first. mystmd serves
`models/<id>.md` at `/<slug>`, the id with `_` as `-`, which is where the search links to.

mystmd turns every link to doi.org into a citation, and looks up any DOI it does not have at
doi.org, which would make each build depend on doi.org answering for every paper.
`docs/references.bib`, written from the papers the registry records, gives it every DOI.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from odezoo.fetch import mirror_url
from odezoo.registry import Registry, from_json
from odezoo.schema import Model, Paper

# BibTeX's special characters, escaped in titles and journals
BIBTEX_SPECIAL = str.maketrans({c: f"\\{c}" for c in "&%$#_{}"})
SOURCE_NAMES = {"pmr": "PMR", "github": "GitHub", "zenodo": "Zenodo", "url": "upstream"}


def slug(model_id: str) -> str:
    """Give the part of the URL mystmd serves a model's page at

    Parameters
    ----------
    model_id : str
        The model's id

    Returns
    -------
    str
        The id with `_` replaced by `-`
    """
    return model_id.replace("_", "-")


def _citation(paper: Paper) -> str:
    """Write a paper as a one-line citation

    Parameters
    ----------
    paper : Paper
        The paper

    Returns
    -------
    str
        Authors (year). Title. Journal.
    """
    return f"{', '.join(paper.authors)} ({paper.year}). {paper.title}. {paper.journal}."


def _linked_citation(paper: Paper) -> str:
    """Write a paper's citation, linked to its DOI if it has one

    Parameters
    ----------
    paper : Paper
        The paper

    Returns
    -------
    str
        The citation, as a markdown link to `https://doi.org/<doi>` or as plain text
    """
    text = _citation(paper)
    return f"[{text}](https://doi.org/{paper.doi})" if paper.doi else text


def _bibtex_author(author: str) -> str:
    """Write an author, `Surname Initials` as the registry has them, as BibTeX does

    Parameters
    ----------
    author : str
        Such as `ten Tusscher KHWJ`

    Returns
    -------
    str
        Such as `ten Tusscher, K. H. W. J.`; an author without initials is left as it is
    """
    surname, _, initials = author.rpartition(" ")
    if not surname or not initials.isalpha() or not initials.isupper():
        return author
    return f"{surname}, {' '.join(f'{c}.' for c in initials)}"


def bibtex(registry: Registry) -> str:
    """Write a BibTeX entry for every DOI among the models' papers and references

    Parameters
    ----------
    registry : Registry
        The registry

    Returns
    -------
    str
        One `@article` per DOI, keyed by the id of the first model, by id, that cites it
    """
    entries: dict[str, str] = {}
    for model in sorted(registry.models.values(), key=lambda m: m.id):
        for n, paper in enumerate((model.paper, *model.references)):
            if not paper.doi or paper.doi.lower() in entries:
                continue
            key = model.id if n == 0 else f"{model.id}_ref{n}"
            authors = " and ".join(_bibtex_author(a) for a in paper.authors)
            entries[paper.doi.lower()] = "\n".join(
                [
                    f"@article{{{key},",
                    f"  author = {{{authors}}},",
                    f"  title = {{{paper.title.translate(BIBTEX_SPECIAL)}}},",
                    f"  journal = {{{paper.journal.translate(BIBTEX_SPECIAL)}}},",
                    f"  year = {{{paper.year}}},",
                    f"  doi = {{{paper.doi}}}",
                    "}",
                ]
            )
    return "".join(f"{entry}\n\n" for entry in entries.values())


def _cell(text: str) -> str:
    """Make text safe in a markdown table cell

    Parameters
    ----------
    text : str
        The text

    Returns
    -------
    str
        The text on one line, with `|` escaped
    """
    return " ".join(text.split()).replace("|", "\\|")


def _details(model: Model, registry: Registry) -> list[str]:
    """List a model's details, leaving out those it does not have

    Parameters
    ----------
    model : Model
        The model
    registry : Registry
        The registry, for the other members of its family

    Returns
    -------
    list[str]
        One markdown list item per detail
    """
    paper = model.paper
    rows = [("Paper", _linked_citation(paper))]
    if paper.doi:
        rows.append(("DOI", f"`{paper.doi}`"))
    if paper.pubmed:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{paper.pubmed}/"
        rows.append(("PubMed", f"[{paper.pubmed}]({url})"))
    for ref in model.references:
        note = f" ({ref.note})" if ref.note else ""
        rows.append(("Reference", _linked_citation(ref) + note))
    if model.family:
        others = sorted(m.id for m in registry.models.values()
                        if m.family == model.family and m.id != model.id)  # fmt: skip
        links = ", ".join(f"[{id}](./{id}.md)" for id in others)
        rows.append(("Family", f"{model.family}" + (f": also {links}" if links else "")))
    rows.append(("Categories", ", ".join(model.categories)))
    if model.keywords:
        rows.append(("Keywords", ", ".join(model.keywords)))
    if model.species:
        rows.append(("Species", model.species))
    if model.cell_type:
        rows.append(("Cell type", model.cell_type))
    rows.append(("Reviewed", "yes" if model.reviewed else "no"))
    return [f"- **{label}**: {value}" for label, value in rows]


def _versions(model: Model, registry: Registry) -> list[str]:
    """Make the table of a model's versions

    The Derived from and Notes columns are there only when some version fills them. A version's
    file links to this repository's copy at the registry's commit, when there is one.

    Parameters
    ----------
    model : Model
        The model
    registry : Registry
        The registry, for its commit

    Returns
    -------
    list[str]
        The table's lines
    """
    derived = any(v.derived_from for v in model.versions)
    notes = any(v.notes for v in model.versions)
    headers = ["Version", "Format", "Added", "Licence"]
    headers += ["Derived from"] * derived + ["Notes"] * notes + ["File", "Source"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join([" --- "] * len(headers)) + "|"]
    for v in model.versions:
        default = " (default)" if v.id == model.default_version else ""
        mirror = mirror_url(registry, model, v)
        cells = [f"`{v.id}`{default}", v.format, v.added.isoformat(), v.license]
        if derived:
            cells.append(f"`{v.derived_from}`" if v.derived_from else "")
        if notes:
            cells.append(v.notes or "")
        cells.append(f"[{v.file}]({mirror})" if mirror else "—")
        if v.source:
            cells.append(f"[{SOURCE_NAMES[v.source.type]}]({v.source.page_url()})")
        else:
            cells.append("this repository")
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return lines


def model_page(
    model: Model, registry: Registry, status: dict[str, dict[str, Any]] | None = None
) -> str:
    """Write one model's page

    Parameters
    ----------
    model : Model
        The model
    registry : Registry
        The registry it is in
    status : dict[str, dict[str, Any]] | None, optional
        Every model's simulation outcome, by id, as `read_status` gives it, by default `None`:
        the simulation did not run

    Returns
    -------
    str
        The page, as MyST markdown
    """
    lines = ["---", f"title: {json.dumps(model.name, ensure_ascii=False)}", "---", ""]
    if model.description:
        lines += [model.description, ""]
    lines += [*_details(model, registry), "", "## Versions", "", *_versions(model, registry), ""]
    lines += ["## Fetch it", ""]
    for v in model.versions:
        lines += ["```", f"odezoo fetch {model.id} --version {v.id}", "```", ""]
    lines += [*simulation_section(model, status), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


#: What drives each category of model in the simulation, for the pages
DRIVEN_BY = {
    "electrophysiology": "with the stimulus protocol the file defines, if it has one",
    "myofilament_mechanics": (
        "with `Ca` following the calcium transient crossbridge drives this model with, repeated "
        "every beat, and `SL` held at the file's default"
    ),
    "cardiovascular_circulation": "on its default parameters, with no input",
}
STATUS_ORDER = {"failed": 0, "timeout": 1, "ok": 2}
NOT_RUN = "The simulation did not run in this build."


def read_status(folder: Path | None) -> dict[str, dict[str, Any]] | None:
    """Read the outcomes `tools/simulate_models.py` wrote

    Parameters
    ----------
    folder : Path | None
        The simulation's output folder, or `None`

    Returns
    -------
    dict[str, dict[str, Any]] | None
        Every model's outcome, by id, or `None` when there is no folder or no `status.json` in it
    """
    if folder is None or not (folder / "status.json").is_file():
        return None
    data = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    return dict(data["models"])


def _code(text: str) -> str:
    """Put text in a code span that backticks inside it cannot end

    Parameters
    ----------
    text : str
        The text, on one line

    Returns
    -------
    str
        The text between double backticks, padded with spaces
    """
    return f"`` {' '.join(text.split())} ``"


def simulation_section(model: Model, status: dict[str, dict[str, Any]] | None) -> list[str]:
    """Write the Simulation section of a model's page

    Parameters
    ----------
    model : Model
        The model
    status : dict[str, dict[str, Any]] | None
        Every model's simulation outcome, by id, or `None` when the simulation did not run

    Returns
    -------
    list[str]
        The section's lines: the figure, or a warning that says where and how it failed
    """
    lines = ["## Simulation", ""]
    outcome = (status or {}).get(model.id)
    if outcome is None:
        return [*lines, ":::{note}", NOT_RUN, ":::"]
    version = f"`{outcome['version']}`"
    if outcome["status"] == "ok":
        driven = DRIVEN_BY.get(model.categories[0], "from its initial values")
        return [
            *lines,
            f"Version {version}, loaded with gotranx and integrated for 3 s {driven}. It took "
            f"{outcome['seconds']:.1f} s to simulate and plot.",
            "",
            f"![Simulation of {model.id}](../simulations/{outcome['figure']})",
        ]
    if outcome["status"] == "timeout":
        said = f"Version {version} did not finish within the time limit"
    else:
        stage = f" at the {outcome['stage']} stage" if outcome["stage"] else ""
        said = f"Version {version} failed to simulate{stage}"
    error = f": {_code(outcome['error'])}" if outcome["error"] else "."
    return [*lines, ":::{warning}", said + error, ":::"]


def simulations_page(registry: Registry, status: dict[str, dict[str, Any]] | None) -> str:
    """Write the overview of every model's simulation, failures first

    Parameters
    ----------
    registry : Registry
        The registry
    status : dict[str, dict[str, Any]] | None
        Every model's simulation outcome, by id, or `None` when the simulation did not run

    Returns
    -------
    str
        The page, as MyST markdown
    """
    lines = ["---", "title: Simulations", "---", ""]
    lines += [
        "Every time the site is built, the default version of every model is loaded with "
        "gotranx and integrated for 3 s: electrophysiology models with their own stimulus, "
        "contraction models with a calcium transient as input, circulation models on their "
        "defaults. Each model's page shows the result. A model that fails is reported here and "
        "on its page; it does not stop the build.",
        "",
    ]
    if status is None:
        return "\n".join([*lines, ":::{note}", NOT_RUN, ":::", ""])
    outcomes = [status.get(i) for i in sorted(registry.models)]
    counts = [
        f"{sum(o is not None and o['status'] == s for o in outcomes)} {label}"
        for s, label in (("ok", "ok"), ("failed", "failed"), ("timeout", "timed out"))
    ]
    missing = sum(o is None for o in outcomes)
    lines += [", ".join(counts) + (f", {missing} not run" if missing else "") + ".", ""]
    lines += ["| Model | Version | Status | Stage | Seconds |", "| --- | --- | --- | --- | --- |"]

    def order(model_id: str) -> tuple[int, str]:
        o = status.get(model_id)
        return (STATUS_ORDER.get(o["status"], -1) if o else -1, model_id)

    for model_id in sorted(registry.models, key=order):
        o = status.get(model_id)
        link = f"[{model_id}](./models/{model_id}.md)"
        if o is None:
            cells = [link, "", "not run", "", ""]
        else:
            seconds = f"{o['seconds']:.1f}"
            cells = [link, f"`{o['version']}`", o["status"], o["stage"] or "", seconds]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join([*lines, ""])


def search_data(registry: Registry, base_url: str) -> list[dict[str, Any]]:
    """Collect what the search page needs about each model, sorted by id

    Parameters
    ----------
    registry : Registry
        The registry
    base_url : str
        Where the site is served from, such as `/odezoo`; empty at the root

    Returns
    -------
    list[dict[str, Any]]
        Per model: id, name, page URL, year, authors, family, keywords, categories, species,
        cell type, formats, and whether it is reviewed
    """
    return [
        {
            "id": m.id,
            "name": m.name,
            "url": f"{base_url}/{slug(m.id)}",
            "year": m.paper.year,
            "authors": list(m.paper.authors),
            "family": m.family,
            "keywords": list(m.keywords),
            "categories": list(m.categories),
            "species": m.species,
            "cell_type": m.cell_type,
            "formats": list(m.formats),
            "reviewed": m.reviewed,
        }
        for m in sorted(registry.models.values(), key=lambda m: m.id)
    ]


def search_page(registry: Registry, base_url: str) -> str:
    """Write the search page: the widget, with every model inline

    Parameters
    ----------
    registry : Registry
        The registry
    base_url : str
        Where the site is served from

    Returns
    -------
    str
        The page, as MyST markdown
    """
    data = json.dumps({"models": search_data(registry, base_url)}, ensure_ascii=False)
    return "\n".join(
        [
            "---",
            "title: Search",
            "---",
            "",
            "Search the models by name, author, keyword, family, cell type or species, and narrow",
            "them down by category, species, format and review status.",
            "",
            ":::{anywidget} ./_static/search.mjs",
            data,
            ":::",
            "",
        ]
    )


def write_pages(
    registry_json: Path, docs: Path, base_url: str, simulations: Path | None = None
) -> list[Path]:
    """Write every model's page, the search and simulations pages, and `references.bib`

    Parameters
    ----------
    registry_json : Path
        A `registry.json`, as `odezoo registry build` writes it
    docs : Path
        The docs folder
    base_url : str
        Where the site is served from, such as `/odezoo`
    simulations : Path | None, optional
        The folder `tools/simulate_models.py` wrote, by default `None`: the pages then say that
        the simulation did not run

    Returns
    -------
    list[Path]
        The files written: the models' pages, the search page, the simulations page and
        `references.bib`

    Raises
    ------
    RegistryError
        If `registry_json` is not a registry this odezoo reads
    """
    registry = from_json(json.loads(registry_json.read_text(encoding="utf-8")))
    folder = docs / "models"
    folder.mkdir(parents=True, exist_ok=True)
    status = read_status(simulations)
    written = []
    for model_id in sorted(registry.models):
        page = folder / f"{model_id}.md"
        text = model_page(registry.models[model_id], registry, status)
        page.write_text(text, encoding="utf-8")
        written.append(page)
    search = docs / "search.md"
    search.write_text(search_page(registry, base_url), encoding="utf-8")
    overview = docs / "simulations.md"
    overview.write_text(simulations_page(registry, status), encoding="utf-8")
    bib = docs / "references.bib"
    bib.write_text(bibtex(registry), encoding="utf-8")
    return [*written, search, overview, bib]


def main(argv: Sequence[str] | None = None) -> int:
    """Write the pages; `BASE_URL` in the environment says where the site is served from

    Parameters
    ----------
    argv : Sequence[str], optional
        `REGISTRY_JSON DOCS_DIR [SIMULATIONS_DIR]`, by default `sys.argv[1:]`

    Returns
    -------
    int
        The exit code: 0, or 2 for a usage error
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) not in (2, 3):
        name = Path(__file__).name
        print(f"usage: {name} REGISTRY_JSON DOCS_DIR [SIMULATIONS_DIR]", file=sys.stderr)
        return 2
    simulations = Path(arguments[2]) if len(arguments) == 3 else None
    base_url = os.environ.get("BASE_URL", "")
    written = write_pages(Path(arguments[0]), Path(arguments[1]), base_url, simulations)
    print(
        f"wrote {len(written) - 3} model pages, the search and simulations pages and references.bib"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
