"""How the command line shows things, with rich

Only the command line imports this module, so `import odezoo` does not load rich. Text that comes
from the registry or the user goes into `rich.text.Text`, which never reads it as markup, so a `[`
in a note or a path is printed as it is.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

from .errors import FetchError
from .schema import Model, Paper

if TYPE_CHECKING:  # only for the type hint; printing a report needs nothing from check
    from .maintain.check import Report


def console(*, stderr: bool = False) -> Console:
    """Make a console on the current stdout or stderr; one per call, so captured streams are used

    Parameters
    ----------
    stderr : bool, optional
        Whether to write to stderr instead of stdout, by default False

    Returns
    -------
    Console
        The console, without automatic highlighting
    """
    return Console(stderr=stderr, highlight=False)


def symbols(out: Console) -> tuple[str, str, str]:
    """Return success, failure and arrow marks; plain ASCII when the output cannot encode ✓ and ✗

    Parameters
    ----------
    out : Console
        The console the marks will be printed on

    Returns
    -------
    tuple[str, str, str]
        `✓`, `✗` and `→` for a UTF encoding, else `OK`, `FAIL` and `->`
    """
    if out.encoding.lower().replace("-", "").startswith("utf"):
        return ("✓", "✗", "→")
    return ("OK", "FAIL", "->")


def _link(url: str) -> Text:
    """Make a URL clickable, in terminals that support links

    Parameters
    ----------
    url : str
        The URL

    Returns
    -------
    Text
        The URL as text that links to itself
    """
    return Text(url, style=Style(link=url))


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


def print_models(models: Sequence[Model], out: Console) -> None:
    """Print models as a table of id, name, year, formats and categories

    Parameters
    ----------
    models : Sequence[Model]
        The models, in the order to print them
    out : Console
        Where to print
    """
    table = Table()
    table.add_column("ID", no_wrap=True, style="bold cyan")
    table.add_column("Name")
    table.add_column("Year", justify="right")
    table.add_column("Formats", style="green")
    table.add_column("Categories", style="magenta")
    for m in models:
        table.add_row(
            Text(m.id),
            Text(m.name),
            str(m.paper.year),
            ", ".join(m.formats),
            ", ".join(m.categories),
        )
    out.print(table)


def print_model(model: Model, out: Console) -> None:
    """Print one model: its details, then a table of its versions

    Parameters
    ----------
    model : Model
        The model
    out : Console
        Where to print
    """
    out.print(Text.assemble((model.name, "bold"), f"  ({model.id})"))
    rows: list[tuple[str, Text | str]] = []
    if model.family:
        rows.append(("Family", Text(model.family)))
    rows.append(("Paper", Text(_citation(model.paper))))
    if model.paper.doi:
        rows.append(("DOI", _link(f"https://doi.org/{model.paper.doi}")))
    if model.paper.pubmed:
        rows.append(("PubMed", _link(f"https://pubmed.ncbi.nlm.nih.gov/{model.paper.pubmed}/")))
    for ref in model.references:
        note = f" ({ref.note})" if ref.note else ""
        rows.append(("Reference", Text(_citation(ref) + note)))
    rows.append(("Categories", ", ".join(model.categories)))
    if model.keywords:
        rows.append(("Keywords", Text(", ".join(model.keywords))))
    if model.species:
        rows.append(("Species", Text(model.species)))
    if model.cell_type:
        rows.append(("Cell type", Text(model.cell_type)))
    rows.append(("Reviewed", "yes" if model.reviewed else "no"))
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold")
    grid.add_column()
    for label, value in rows:
        grid.add_row(label, value)
    out.print(grid)

    # Columns that are empty for every version are left out; URLs wrap rather than being cut.
    derived = any(v.derived_from for v in model.versions)
    notes = any(v.notes for v in model.versions)
    versions = Table(title="Versions", title_justify="left")
    versions.add_column("Version", no_wrap=True)
    versions.add_column("Format")
    versions.add_column("Added", no_wrap=True)
    versions.add_column("Licence", no_wrap=True)
    if derived:
        versions.add_column("Derived from")
    if notes:
        versions.add_column("Notes")
    versions.add_column("Source", overflow="fold")
    for v in model.versions:
        default = " (default)" if v.id == model.default_version else ""
        cells: list[Text | str] = [Text(v.id + default), v.format, v.added.isoformat()]
        cells.append(Text(v.license))
        if derived:
            cells.append(Text(v.derived_from or ""))
        if notes:
            cells.append(Text(v.notes or ""))
        cells.append(_link(v.source.page_url()) if v.source else "this repository")
        versions.add_row(*cells)
    out.print(versions)


def print_fetched(model_id: str, path: Path, out: Console) -> None:
    """Print that a model's file was fetched, and where it is

    Parameters
    ----------
    model_id : str
        The model id, as it was asked for
    path : Path
        Where the file is
    out : Console
        Where to print
    """
    ok, _, arrow = symbols(out)
    # soft_wrap: a path split over two lines is a broken path for whoever copies or parses it.
    out.print(Text.assemble((ok, "bold green"), f" {model_id} {arrow} {path}"), soft_wrap=True)


def print_error(error: Exception, out: Console, *, prefix: str = "") -> None:
    """Print an error on one line, and for a `FetchError` a table of the places tried

    Parameters
    ----------
    error : Exception
        The error
    out : Console
        Where to print
    prefix : str, optional
        Text to put before the message, such as the model id; by default none
    """
    _, fail, _ = symbols(out)
    if isinstance(error, FetchError):
        message = f"could not fetch {error.model_id} {error.version_id}"
    else:
        message = str(error)
    out.print(Text.assemble((fail, "bold red"), f" {prefix}{message}"), soft_wrap=True)
    if isinstance(error, FetchError) and error.attempts:
        table = Table("Tried", "Why it failed")
        for attempt in error.attempts:
            table.add_row(Text(attempt.source), Text(attempt.reason))
        out.print(table)


def print_report(report: Report, out: Console) -> None:
    """Print what `odezoo registry check` found: errors, warnings, then the counts

    Parameters
    ----------
    report : Report
        The report
    out : Console
        Where to print
    """
    for error in report.errors:
        out.print(Text(error, style="red"))
    for warning in report.warnings:
        out.print(Text(warning, style="yellow"))
    out.print(
        f"{report.checked} models checked, {len(report.errors)} errors, "
        f"{len(report.warnings)} warnings"
    )
