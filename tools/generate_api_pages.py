"""Write the API reference pages from odezoo's own source

    python tools/generate_api_pages.py docs/api

One page per public module, written at build time so that the reference is always the code in
the commit that built it. griffe reads the source without importing it. Adapted from sknm's
`tools/generate_api_pages.py` (ComputationalPhysiology/sknm at 6e8f65a, MIT): the same rendering,
for a fixed list of modules instead of every module in the package.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import griffe

ROOT = Path(__file__).resolve().parents[1]
# The modules whose names `odezoo/__init__.py` re-exports; the rest of the package is internal.
MODULES = ("odezoo.api", "odezoo.schema", "odezoo.errors")
DOCUMENTED_KINDS = ("class", "function", "attribute")
ATTRIBUTE_HEADERS = ("Name", "Type", "Value", "Description")


def load(name: str = "odezoo", search_paths: Sequence[Path] | None = None) -> Any:
    """Read a package from source, with its docstrings parsed as NumPy style

    Parameters
    ----------
    name : str, optional
        The package to read, by default `odezoo`
    search_paths : Sequence[Path], optional
        Where to look for it, by default this repository's `src/`

    Returns
    -------
    griffe.Module
        The package, with its modules and parsed docstrings
    """
    paths = [ROOT / "src"] if search_paths is None else list(search_paths)
    return griffe.load(name, search_paths=[str(path) for path in paths], docstring_parser="numpy")


def documented_members(module: Any) -> list[Any]:
    """List the members a module's page documents, in the order they are written in

    A member belongs to the module that defines it, so imported names are left out: they are
    documented on their own module's page. A module that declares `__all__` narrows the list to
    what it names.

    Parameters
    ----------
    module : griffe.Module
        The module, or a class

    Returns
    -------
    list[griffe.Object]
        Its public classes, functions and attributes
    """
    declared = set(module.exports) if module.exports is not None else None
    members = [
        member
        for name, member in module.members.items()
        if not member.is_alias
        and member.kind.value in DOCUMENTED_KINDS
        and not name.startswith("_")
        and (declared is None or name in declared)
    ]
    return sorted(members, key=lambda member: member.lineno or 0)


def _table(rows: list[tuple[str, ...]], headers: tuple[str, ...]) -> list[str]:
    """Render rows as a markdown table, leaving out the columns no row fills

    Parameters
    ----------
    rows : list[tuple[str, ...]]
        The cells, row by row
    headers : tuple[str, ...]
        The column headers

    Returns
    -------
    list[str]
        The table's lines, with `|` in a cell escaped
    """

    def cell(text: str) -> str:
        """Put a cell's text on one line, with `|` escaped

        Parameters
        ----------
        text : str
            The cell's text

        Returns
        -------
        str
            The text, safe in a table cell
        """
        return " ".join(text.split()).replace("|", "\\|")

    kept = [index for index in range(len(headers)) if any(row[index].strip() for row in rows)]
    lines = ["| " + " | ".join(headers[index] for index in kept) + " |"]
    lines += ["|" + "|".join([" --- "] * len(kept)) + "|"]
    lines += ["| " + " | ".join(cell(row[index]) for index in kept) + " |" for row in rows]
    return lines


def _definition(term: str, description: str) -> list[str]:
    """Render one entry of a markdown definition list, indenting what runs on

    Parameters
    ----------
    term : str
        The term
    description : str
        Its description

    Returns
    -------
    list[str]
        The entry's lines, ending with a blank one
    """
    body = description.strip().splitlines() or [""]
    return [term, f": {body[0]}", *[f"  {line}" for line in body[1:]], ""]


def _annotated(name: str, annotation: Any) -> str:
    """Make a definition term naming something and, where it is known, its type

    Parameters
    ----------
    name : str
        The name, or empty for an unnamed return value
    annotation : Any
        Its type, or None

    Returns
    -------
    str
        The term
    """
    if annotation is None:
        return f"`{name}`" if name else ""
    return f"`{name}` : *{annotation}*" if name else f"*{annotation}*"


def _sections(docstring: Any) -> list[str]:
    """Render a parsed NumPy-style docstring as markdown

    Parameters
    ----------
    docstring : griffe.Docstring | None
        The docstring

    Returns
    -------
    list[str]
        Its lines; none for no docstring
    """
    if docstring is None:
        return []
    lines: list[str] = []
    for section in docstring.parsed:
        kind = section.kind.value
        if kind == "text":
            lines += [section.value, ""]
        elif kind in ("parameters", "other_parameters", "attributes"):
            lines += [f"**{kind.replace('_', ' ').title()}**", ""]
            for item in section.value:
                lines += _definition(_annotated(item.name, item.annotation), item.description)
        elif kind in ("returns", "yields"):
            lines += [f"**{kind.title()}**", ""]
            for item in section.value:
                lines += _definition(_annotated(item.name or "", item.annotation), item.description)
        elif kind == "raises":
            lines += ["**Raises**", ""]
            for item in section.value:
                lines += _definition(f"`{item.annotation}`", item.description)
        elif kind == "examples":
            lines += ["**Examples**", ""]
            for example_kind, text in section.value:
                if example_kind.value == "examples":
                    lines += ["```pycon", text, "```", ""]
                else:
                    lines += [text, ""]
        elif kind == "admonition":
            lines += [f"**{section.title}**", "", section.value.description, ""]
    return lines


def _signature(member: Any) -> str | None:
    """Give how a member is called, or None for something that is not called

    A class that writes no `__init__`, such as an exception that only names itself, has no
    signature to show: griffe renders it as the bare name, which would read as a constructor
    taking no arguments.

    Parameters
    ----------
    member : griffe.Object
        A class or function

    Returns
    -------
    str | None
        The signature, with the name in front
    """
    try:
        signature = str(member.signature())
    except Exception:
        return None
    return signature if "(" in signature else None


def _documented_names(docstring: Any) -> set[str]:
    """Collect the names a docstring's own Parameters and Attributes sections cover

    Parameters
    ----------
    docstring : griffe.Docstring | None
        The docstring

    Returns
    -------
    set[str]
        The names
    """
    if docstring is None:
        return set()
    return {
        item.name
        for section in docstring.parsed
        if section.kind.value in ("parameters", "attributes")
        for item in section.value
    }


def _attribute_rows(members: list[Any]) -> list[tuple[str, ...]]:
    """Make the table rows for attributes: name, type, value and description

    Parameters
    ----------
    members : list[griffe.Attribute]
        The attributes

    Returns
    -------
    list[tuple[str, ...]]
        One row each
    """
    return [
        (
            f"`{member.name}`",
            f"`{member.annotation}`" if member.annotation is not None else "",
            f"`{member.value}`" if member.value is not None else "",
            member.docstring.value if member.docstring else "",
        )
        for member in members
    ]


def _render_member(member: Any, qualifier: str, level: int) -> list[str]:
    """Render one class or function, and a class's own members beneath it

    Parameters
    ----------
    member : griffe.Object
        The class or function
    qualifier : str
        What goes in front of its name, such as `Model.` for a method
    level : int
        The heading level

    Returns
    -------
    list[str]
        Its lines
    """
    name = f"{qualifier}{member.name}"
    lines = ["#" * level + f" `{name}`", ""]
    if member.kind.value == "class" and member.bases:
        lines += ["Bases: " + ", ".join(f"`{base}`" for base in member.bases), ""]
    signature = _signature(member)
    if signature is not None:
        lines += ["```python", f"{name}{signature[len(member.name) :]}", "```", ""]
    lines += _sections(member.docstring)

    if member.kind.value != "class":
        return lines

    covered = _documented_names(member.docstring)
    children = documented_members(member)
    attributes = [
        child for child in children if child.kind.value == "attribute" and child.name not in covered
    ]
    if attributes:
        lines += ["**Attributes**", "", *_table(_attribute_rows(attributes), ATTRIBUTE_HEADERS), ""]
    for child in children:
        if child.kind.value != "attribute":
            lines += _render_member(child, f"{name}.", level + 1)
    return lines


def render(module: Any) -> str:
    """Write one module's reference page

    Parameters
    ----------
    module : griffe.Module
        The module

    Returns
    -------
    str
        The page, as MyST markdown
    """
    lines = ["---", f"title: {module.path}", "---", "", f"# `{module.path}`", ""]
    lines += _sections(module.docstring)
    members = documented_members(module)
    for member in members:
        if member.kind.value != "attribute":
            lines += _render_member(member, "", 2)
    attributes = [member for member in members if member.kind.value == "attribute"]
    if attributes:
        lines += ["## Attributes", "", *_table(_attribute_rows(attributes), ATTRIBUTE_HEADERS), ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def write_pages(output_dir: Path, modules: Sequence[str] = MODULES) -> list[Path]:
    """Write a page for each module, as `<output_dir>/<module>.md`

    Parameters
    ----------
    output_dir : Path
        Where the pages go; made if it does not exist
    modules : Sequence[str], optional
        The modules, by default `MODULES`

    Returns
    -------
    list[Path]
        The pages written
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    package = load()
    written = []
    for path in modules:
        module = package[path.removeprefix("odezoo.")]
        page = output_dir / f"{module.path}.md"
        page.write_text(render(module), encoding="utf-8")
        written.append(page)
    return written


def main(argv: Sequence[str] | None = None) -> int:
    """Write the reference pages to the folder named on the command line

    Parameters
    ----------
    argv : Sequence[str], optional
        The arguments, by default `sys.argv[1:]`

    Returns
    -------
    int
        The exit code: 0, or 2 for a usage error
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print(f"usage: {Path(__file__).name} OUTPUT_DIR", file=sys.stderr)
        return 2
    for page in write_pages(Path(arguments[0])):
        print(f"wrote {page}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
