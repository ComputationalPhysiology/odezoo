"""What a model is: the dataclasses behind `model.toml`, and the rules a `model.toml` must follow

`parse_model` checks every rule that can be checked without the files on disk; the rest (files
exist, hashes match, licence texts are there) is `odezoo registry check`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from .errors import RegistryError, VersionNotFound

# PMR's top-level categories, as slugs.
CATEGORIES: tuple[str, ...] = (
    "calcium_dynamics",
    "cardiovascular_circulation",
    "cell_cycle",
    "cell_migration",
    "circadian_rhythms",
    "electrophysiology",
    "endocrine",
    "excitation_contraction_coupling",
    "gene_regulation",
    "hepatology",
    "immunology",
    "ion_transport",
    "mechanical_constitutive_laws",
    "metabolism",
    "myofilament_mechanics",
    "neurobiology",
    "ph_regulation",
    "protein_modules",
    "signal_transduction",
    "synthetic_biology",
)

FORMATS: dict[str, str] = {"cellml": ".cellml", "ode": ".ode"}

# SPDX ids of licences that allow a copy of the file to be kept in this repository.
MIRROR_LICENSES: frozenset[str] = frozenset(
    {
        "CC-BY-3.0",
        "CC-BY-4.0",
        "CC-BY-SA-3.0",
        "CC-BY-SA-4.0",
        "CC0-1.0",
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Apache-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
        "LGPL-2.1-or-later",
        "LGPL-3.0-or-later",
    }
)

MODEL_ID = re.compile(r"^[a-z][a-z0-9_]*$")
VERSION_ID = re.compile(r"^[a-z0-9][a-z0-9.-]*$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
GITHUB_REPO = re.compile(r"^[^/\s]+/[^/\s]+$")
# The characters of an SPDX licence id, such as CC-BY-4.0, GPL-2.0+ or LicenseRef-PMR.
LICENSE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+-]*$")
# The licence ids odezoo knows, by their lowercase form, to catch them written in another case.
KNOWN_LICENSES: dict[str, str] = {id.lower(): id for id in (*MIRROR_LICENSES, "unknown")}
DOI = re.compile(r"^10\.\d{4,9}/\S+$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# For each source type: the fields it requires, and the ones it may have.
SOURCE_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "pmr": (("workspace", "commit", "path"), ("exposure",)),
    "github": (("repo", "commit", "path"), ()),
    "zenodo": (("record", "filename"), ()),
    "url": (("url",), ()),
}

PAPER_FIELDS = ("title", "authors", "journal", "year", "doi", "pubmed")
VERSION_FIELDS = (
    "id",
    "format",
    "sha256",
    "license",
    "file",
    "source",
    "derived_from",
    "added",
    "notes",
)
MODEL_FIELDS = (
    "id",
    "name",
    "family",
    "description",
    "categories",
    "keywords",
    "species",
    "cell_type",
    "reviewed",
    "default_version",
    "paper",
    "references",
    "versions",
)


@dataclass(frozen=True)
class Paper:
    """A paper: the one that describes a model, or another one it refers to

    Attributes
    ----------
    title : str
        The paper's title
    authors : tuple[str, ...]
        The authors, in the paper's order
    journal : str
        The journal it was published in
    year : int
        The year it was published
    doi : str | None
        The DOI, without `https://doi.org/`
    pubmed : int | None
        The PubMed id; a paper has a DOI, a PubMed id or both
    note : str | None
        For a reference, how it relates to the model
    """

    title: str
    authors: tuple[str, ...]
    journal: str
    year: int
    doi: str | None = None
    pubmed: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class Source:
    """Where upstream keeps a file; which fields are set depends on `type`

    Attributes
    ----------
    type : str
        `pmr`, `github`, `zenodo` or `url`
    workspace : str | None
        PMR: the workspace URL
    commit : str | None
        PMR and GitHub: the full commit id the file is pinned to
    path : str | None
        PMR and GitHub: the file's path in the workspace or repository
    exposure : str | None
        PMR: the exposure page, if the workspace has one
    repo : str | None
        GitHub: the repository, as `owner/name`
    record : int | None
        Zenodo: the record id
    filename : str | None
        Zenodo: the file's name in the record
    url : str | None
        Any other host: the URL the file downloads from
    """

    type: str
    workspace: str | None = None
    commit: str | None = None
    path: str | None = None
    exposure: str | None = None
    repo: str | None = None
    record: int | None = None
    filename: str | None = None
    url: str | None = None

    def url_for_download(self) -> str:
        """Return the URL that serves the file's bytes

        Returns
        -------
        str
            For PMR the workspace's `rawfile` URL at `commit`, for GitHub the
            `raw.githubusercontent.com` URL at `commit`, for Zenodo the record's download URL,
            and otherwise `url`
        """
        if self.type == "pmr":
            assert self.workspace and self.commit and self.path
            return f"{self.workspace.rstrip('/')}/rawfile/{self.commit}/{quote(self.path)}"
        if self.type == "github":
            assert self.repo and self.commit and self.path
            return f"https://raw.githubusercontent.com/{self.repo}/{self.commit}/{quote(self.path)}"
        if self.type == "zenodo":
            assert self.record is not None and self.filename
            return (
                f"https://zenodo.org/records/{self.record}/files/{quote(self.filename)}?download=1"
            )
        assert self.url
        return self.url

    def page_url(self) -> str:
        """Return a page about the file for people to open, rather than the file itself

        Returns
        -------
        str
            For PMR the exposure (else the workspace), for GitHub the file at `commit`, for
            Zenodo the record, and otherwise `url`
        """
        if self.type == "pmr":
            assert self.workspace
            return self.exposure or self.workspace
        if self.type == "github":
            return f"https://github.com/{self.repo}/blob/{self.commit}/{self.path}"
        if self.type == "zenodo":
            return f"https://zenodo.org/records/{self.record}"
        assert self.url
        return self.url


@dataclass(frozen=True)
class Version:
    """One version of a model: a file, identified by its sha256

    Attributes
    ----------
    id : str
        The version's id, such as `pmr-cb090c9` for a file from PMR or `v1` for one of our own
    format : str
        `cellml` or `ode`
    sha256 : str
        The sha256 of the file's bytes, in lowercase hex
    license : str
        The SPDX id of the file's licence
    added : date
        When the version was added to the registry
    file : str | None
        The name of the copy kept in the model's folder, `<id>.<ext>`, if there is one
    source : Source | None
        Where upstream keeps the file, if anywhere
    derived_from : str | None
        The id of the version this one was edited from
    notes : str | None
        What was changed, and why
    """

    id: str
    format: str
    sha256: str
    license: str
    added: date
    file: str | None = None
    source: Source | None = None
    derived_from: str | None = None
    notes: str | None = None

    @property
    def ext(self) -> str:
        """The file extension of the version's format, such as `.cellml`"""
        return FORMATS[self.format]


@dataclass(frozen=True)
class Model:
    """A model in the registry: its paper, how to find it, and its versions

    Attributes
    ----------
    id : str
        The model's id, which is also its folder's name, such as `beeler_reuter_1977`
    name : str
        A name for people to read
    categories : tuple[str, ...]
        Categories from `CATEGORIES`, PMR's top-level ones
    reviewed : bool
        True once a maintainer has run the model and compared it with the paper
    paper : Paper
        The paper that describes the model
    versions : tuple[Version, ...]
        Every version, oldest first
    family : str | None
        An id shared by models that are cell-type variants of one another
    description : str | None
        A few sentences about the model
    keywords : tuple[str, ...]
        Keywords for search, as `normalize_keyword` writes them
    species : str | None
        The species, in lowercase
    cell_type : str | None
        The cell type, such as `ventricular myocyte, epicardial`
    default_version : str | None
        The version to fetch when none is asked for; without it, the newest
    references : tuple[Paper, ...]
        Other papers the model draws on
    """

    id: str
    name: str
    categories: tuple[str, ...]
    reviewed: bool
    paper: Paper
    versions: tuple[Version, ...]
    family: str | None = None
    description: str | None = None
    keywords: tuple[str, ...] = ()
    species: str | None = None
    cell_type: str | None = None
    default_version: str | None = None
    references: tuple[Paper, ...] = ()

    @property
    def formats(self) -> tuple[str, ...]:
        """The formats the versions are in, each once, in the order of the versions"""
        return tuple(dict.fromkeys(v.format for v in self.versions))

    def version(self, id: str) -> Version:
        """Return the version with the id `id`

        Parameters
        ----------
        id : str
            A version id, such as `pmr-cb090c9`

        Returns
        -------
        Version
            The version

        Raises
        ------
        VersionNotFound
            If the model has no such version
        """
        for v in self.versions:
            if v.id == id:
                return v
        ids = ", ".join(v.id for v in self.versions)
        raise VersionNotFound(f"{self.id} has no version {id!r}; it has {ids}")


def normalize_keyword(text: str) -> str:
    """Write a keyword the way the registry stores it

    Parameters
    ----------
    text : str
        A keyword as typed

    Returns
    -------
    str
        `text` in lowercase, each run of whitespace made one space, none at the ends
    """
    return " ".join(text.lower().split())


class _Fields:
    """Typed access to one TOML table, with errors that name the file and the field

    Parameters
    ----------
    data : Any
        The table, as `tomllib` or `json` parsed it
    where : str
        The file it comes from, for error messages
    prefix : str, optional
        The table's own field name, such as `versions[1]`; empty for the top level

    Raises
    ------
    RegistryError
        If `data` is not a table
    """

    def __init__(self, data: Any, where: str, prefix: str = ""):
        self.where = where
        self.prefix = prefix
        if not isinstance(data, Mapping):
            raise self.error("", "must be a table")
        self.data = data

    def name(self, key: str) -> str:
        """Return the full name of the field `key`, as error messages print it

        Parameters
        ----------
        key : str
            A field of this table, or the empty string for the table itself

        Returns
        -------
        str
            The name with the table's prefix, such as `versions[1].sha256`
        """
        return f"{self.prefix}.{key}" if self.prefix and key else self.prefix or key

    def error(self, key: str, message: str) -> RegistryError:
        """Make the error for a broken rule about the field `key`

        Parameters
        ----------
        key : str
            The field, or the empty string for the table itself
        message : str
            The rule that is broken, such as "is required"

        Returns
        -------
        RegistryError
            The error, naming the file and the field, for the caller to raise
        """
        return RegistryError(message, where=self.where, field=self.name(key) or None)

    def only(self, allowed: tuple[str, ...]) -> None:
        """Check that the table has no fields but the ones in `allowed`

        Parameters
        ----------
        allowed : tuple[str, ...]
            The names of the fields the table may have

        Raises
        ------
        RegistryError
            At the first field not in `allowed`
        """
        for key in self.data:
            if key not in allowed:
                raise self.error(key, "unknown field")

    def _get(self, key: str, kinds: tuple[type, ...], what: str, required: bool) -> Any:
        """Return the value of the field `key`, which must be one of `kinds`

        Parameters
        ----------
        key : str
            The field
        kinds : tuple[type, ...]
            The types the value may have; `bool` counts only if it is listed, though it is an
            `int`
        what : str
            The kinds in words, for the error message, such as "a string"
        required : bool
            Whether a missing field is an error

        Returns
        -------
        Any
            The value, or None if the field is missing and not required

        Raises
        ------
        RegistryError
            If the field is missing and required, or has another type
        """
        value = self.data.get(key)
        if value is None:
            if required:
                raise self.error(key, "is required")
            return None
        if isinstance(value, bool) and bool not in kinds or not isinstance(value, kinds):
            raise self.error(key, f"must be {what}")
        return value

    def string(self, key: str, required: bool = False) -> str | None:
        """Return the string field `key`

        Parameters
        ----------
        key : str
            The field
        required : bool, optional
            Whether a missing field is an error, by default False

        Returns
        -------
        str | None
            The string, or None if the field is missing

        Raises
        ------
        RegistryError
            If the field is required and missing, is not a string, or is only whitespace
        """
        value = self._get(key, (str,), "a string", required)
        if value is not None and not value.strip():
            raise self.error(key, "must not be empty")
        return value

    def required_string(self, key: str) -> str:
        """Return the string field `key`, which must be there

        Parameters
        ----------
        key : str
            The field

        Returns
        -------
        str
            The string

        Raises
        ------
        RegistryError
            If the field is missing, is not a string, or is only whitespace
        """
        value = self.string(key, required=True)
        assert value is not None
        return value

    def integer(self, key: str, required: bool = False) -> int | None:
        """Return the integer field `key`

        Parameters
        ----------
        key : str
            The field
        required : bool, optional
            Whether a missing field is an error, by default False

        Returns
        -------
        int | None
            The integer, or None if the field is missing

        Raises
        ------
        RegistryError
            If the field is required and missing, or is not an integer (true and false are not)
        """
        return self._get(key, (int,), "an integer", required)

    def boolean(self, key: str) -> bool:
        """Return the boolean field `key`, which must be there

        Parameters
        ----------
        key : str
            The field

        Returns
        -------
        bool
            The value

        Raises
        ------
        RegistryError
            If the field is missing, or is not true or false
        """
        return self._get(key, (bool,), "true or false", True)

    def strings(self, key: str, required: bool = False) -> tuple[str, ...]:
        """Return the field `key`, a list of strings that are not only whitespace

        Parameters
        ----------
        key : str
            The field
        required : bool, optional
            Whether a missing field is an error, by default False

        Returns
        -------
        tuple[str, ...]
            The strings; empty if the field is missing

        Raises
        ------
        RegistryError
            If the field is required and missing, is not a list, or holds anything else
        """
        value = self._get(key, (list, tuple), "a list of strings", required)
        if value is None:
            return ()
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise self.error(key, "must be a list of non-empty strings")
        return tuple(value)

    def table(self, key: str, required: bool = False) -> _Fields | None:
        """Return the field `key`, a table whose errors are named after it

        Parameters
        ----------
        key : str
            The field
        required : bool, optional
            Whether a missing field is an error, by default False

        Returns
        -------
        _Fields | None
            The table, or None if the field is missing

        Raises
        ------
        RegistryError
            If the field is required and missing, or is not a table
        """
        value = self._get(key, (Mapping,), "a table", required)
        return None if value is None else _Fields(value, self.where, self.name(key))

    def tables(self, key: str) -> list[_Fields]:
        """Return the field `key`, an array of tables whose errors are named after their index

        Parameters
        ----------
        key : str
            The field

        Returns
        -------
        list[_Fields]
            The tables; empty if the field is missing

        Raises
        ------
        RegistryError
            If the field is not a list, or an item of it is not a table
        """
        value = self._get(key, (list, tuple), "a list of tables", False)
        if value is None:
            return []
        return [_Fields(item, self.where, f"{self.name(key)}[{i}]") for i, item in enumerate(value)]

    def date(self, key: str) -> date:
        """Return the date field `key`, which must be there

        Parameters
        ----------
        key : str
            The field

        Returns
        -------
        date
            The date, from a TOML date or from a `YYYY-MM-DD` string (as in `registry.json`)

        Raises
        ------
        RegistryError
            If the field is missing, is a date and time, or is not a date
        """
        value = self._get(key, (date, str), "a date (YYYY-MM-DD)", True)
        if isinstance(value, datetime):
            raise self.error(key, "must be a date (YYYY-MM-DD), not a date and time")
        if isinstance(value, date):
            return value
        # fromisoformat also reads forms such as 20261101 and 2026-W44-1.
        if not ISO_DATE.fullmatch(value):
            raise self.error(key, "must be a date (YYYY-MM-DD)")
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise self.error(key, "must be a date (YYYY-MM-DD)") from None


def _paper(f: _Fields, *, with_note: bool) -> Paper:
    """Read a `[paper]` or `[[references]]` table

    Parameters
    ----------
    f : _Fields
        The table
    with_note : bool
        Whether the table may have a `note`, as references may

    Returns
    -------
    Paper
        The paper

    Raises
    ------
    RegistryError
        At the first broken rule, such as a missing title, or neither a DOI nor a PubMed id
    """
    f.only(PAPER_FIELDS + (("note",) if with_note else ()))
    authors = f.strings("authors", required=True)
    if not authors:
        raise f.error("authors", "needs at least one author")
    year = f.integer("year", required=True)
    assert year is not None
    paper = Paper(
        title=f.required_string("title"),
        authors=authors,
        journal=f.required_string("journal"),
        year=year,
        doi=f.string("doi"),
        pubmed=f.integer("pubmed"),
        note=f.string("note") if with_note else None,
    )
    if paper.doi is None and paper.pubmed is None:
        raise f.error("", "needs a doi or a pubmed id")
    if paper.doi is not None and not DOI.fullmatch(paper.doi):
        raise f.error("doi", f"{paper.doi!r} must be a bare DOI, 10.<number>/<suffix>")
    return paper


def _source(f: _Fields) -> Source:
    """Read a `[versions.source]` table

    Parameters
    ----------
    f : _Fields
        The table

    Returns
    -------
    Source
        The source

    Raises
    ------
    RegistryError
        At the first broken rule: an unknown type, a field the type lacks or does not have, a
        commit that is not a full commit id, a malformed repo, or a URL that is not http(s)
    """
    type = f.required_string("type")
    if type not in SOURCE_FIELDS:
        raise f.error("type", f"must be one of {', '.join(SOURCE_FIELDS)}")
    required, optional = SOURCE_FIELDS[type]
    f.only(("type", *required, *optional))
    values: dict[str, Any] = {}
    for key in required:
        values[key] = f.integer(key, required=True) if key == "record" else f.string(key, True)
    for key in optional:
        values[key] = f.string(key)
    if "commit" in values and not GIT_COMMIT.fullmatch(values["commit"]):
        raise f.error("commit", "must be a full commit id: 40 lowercase hex characters")
    if type == "github" and not GITHUB_REPO.fullmatch(values["repo"]):
        raise f.error("repo", "must be owner/name")
    for key in ("workspace", "exposure", "url"):
        if values.get(key) and not values[key].startswith(("http://", "https://")):
            raise f.error(key, "must be an http:// or https:// URL")
    return Source(type=type, **values)


def _version(f: _Fields) -> Version:
    """Read one `[[versions]]` table

    Parameters
    ----------
    f : _Fields
        The table

    Returns
    -------
    Version
        The version

    Raises
    ------
    RegistryError
        At the first broken rule, such as a malformed id or sha256, a `file` not named after the
        id, neither a file nor a source, or a copy kept under a licence that does not allow one
    """
    f.only(VERSION_FIELDS)
    id = f.required_string("id")
    if not VERSION_ID.fullmatch(id):
        raise f.error("id", f"{id!r} must match {VERSION_ID.pattern}")
    format = f.required_string("format")
    if format not in FORMATS:
        raise f.error("format", f"must be one of {', '.join(FORMATS)}, not {format!r}")
    sha256 = f.required_string("sha256")
    if not SHA256.fullmatch(sha256):
        raise f.error("sha256", "must be 64 lowercase hex characters")
    license = f.required_string("license")
    known = KNOWN_LICENSES.get(license.lower(), license)
    if license != known:
        raise f.error("license", f"write {license!r} as {known!r}")
    if not LICENSE_ID.fullmatch(license):
        raise f.error("license", f"{license!r} must be an SPDX id, such as CC-BY-4.0, or unknown")
    file = f.string("file")
    if file is not None and file != f"{id}{FORMATS[format]}":
        raise f.error("file", f"must be {id}{FORMATS[format]}, the version id and the extension")
    source_fields = f.table("source")
    source = None if source_fields is None else _source(source_fields)
    if file is None and source is None:
        raise f.error("source", "a version needs a file, a source, or both")
    if file is not None and license not in MIRROR_LICENSES:
        raise f.error(
            "license",
            f"{license} does not allow a copy here; leave out file and fetch from the source",
        )
    return Version(
        id=id,
        format=format,
        sha256=sha256,
        license=license,
        added=f.date("added"),
        file=file,
        source=source,
        derived_from=f.string("derived_from"),
        notes=f.string("notes"),
    )


def parse_model(data: Mapping[str, Any], *, where: str) -> Model:
    """Build a `Model` from a parsed `model.toml` (or its `model_to_dict` form)

    Parameters
    ----------
    data : Mapping[str, Any]
        The parsed TOML or JSON
    where : str
        The file it comes from, which error messages name

    Returns
    -------
    Model
        The model

    Raises
    ------
    RegistryError
        At the first rule that is broken, naming `where` and the field
    """
    f = _Fields(data, where)
    f.only(MODEL_FIELDS)

    id = f.required_string("id")
    if not MODEL_ID.fullmatch(id):
        raise f.error("id", f"{id!r} must match {MODEL_ID.pattern}")
    family = f.string("family")
    if family is not None and not MODEL_ID.fullmatch(family):
        raise f.error("family", f"{family!r} must match {MODEL_ID.pattern}")

    categories = f.strings("categories", required=True)
    if not categories:
        raise f.error("categories", "needs at least one category")
    for category in categories:
        if category not in CATEGORIES:
            raise f.error("categories", f"{category!r} is not one of the categories")

    keywords = f.strings("keywords")
    for keyword in keywords:
        if keyword != normalize_keyword(keyword):
            raise f.error("keywords", f"write {keyword!r} as {normalize_keyword(keyword)!r}")
    if len(set(keywords)) != len(keywords):
        raise f.error("keywords", "lists a keyword twice")

    species = f.string("species")
    if species is not None and species != species.lower():
        raise f.error("species", "must be lowercase")

    paper_fields = f.table("paper", required=True)
    assert paper_fields is not None
    paper = _paper(paper_fields, with_note=False)
    references = tuple(_paper(t, with_note=True) for t in f.tables("references"))

    version_tables = f.tables("versions")
    if not version_tables:
        raise f.error("versions", "needs at least one version")
    versions = tuple(_version(t) for t in version_tables)
    ids = [v.id for v in versions]
    hashes = [v.sha256 for v in versions]
    for i, v in enumerate(versions):
        if ids.index(v.id) != i:
            raise f.error(f"versions[{i}].id", f"version id {v.id!r} is used twice")
        if hashes.index(v.sha256) != i:
            same = versions[hashes.index(v.sha256)].id
            raise f.error(f"versions[{i}].sha256", f"is the same file as version {same}")
        if v.derived_from is not None and (v.derived_from == v.id or v.derived_from not in ids):
            raise f.error(
                f"versions[{i}].derived_from", f"{v.derived_from!r} is not another version"
            )
    default_version = f.string("default_version")
    if default_version is not None and default_version not in ids:
        raise f.error("default_version", f"{default_version!r} is not a version of this model")

    return Model(
        id=id,
        name=f.required_string("name"),
        categories=categories,
        reviewed=f.boolean("reviewed"),
        paper=paper,
        versions=versions,
        family=family,
        description=f.string("description"),
        keywords=keywords,
        species=species,
        cell_type=f.string("cell_type"),
        default_version=default_version,
        references=references,
    )


def _without_empty(data: dict[str, Any]) -> dict[str, Any]:
    """Leave out the fields that are None or an empty list, as `model.toml` does

    Parameters
    ----------
    data : dict[str, Any]
        A table, in field order

    Returns
    -------
    dict[str, Any]
        The table without its empty fields, in the same order
    """
    return {key: value for key, value in data.items() if value is not None and value != []}


def _paper_to_dict(paper: Paper) -> dict[str, Any]:
    """Return the dict form of a paper, as in `model.toml`

    Parameters
    ----------
    paper : Paper
        The paper

    Returns
    -------
    dict[str, Any]
        The fields that are set
    """
    return _without_empty(
        {
            "title": paper.title,
            "authors": list(paper.authors),
            "journal": paper.journal,
            "year": paper.year,
            "doi": paper.doi,
            "pubmed": paper.pubmed,
            "note": paper.note,
        }
    )


def _source_to_dict(source: Source) -> dict[str, Any]:
    """Return the dict form of a source, as in `model.toml`

    Parameters
    ----------
    source : Source
        The source

    Returns
    -------
    dict[str, Any]
        The type, and those of the type's fields that are set
    """
    required, optional = SOURCE_FIELDS[source.type]
    return _without_empty(
        {"type": source.type, **{key: getattr(source, key) for key in required + optional}}
    )


def _version_to_dict(version: Version) -> dict[str, Any]:
    """Return the dict form of a version, as in `model.toml`

    Parameters
    ----------
    version : Version
        The version

    Returns
    -------
    dict[str, Any]
        The fields that are set, with `added` as a `YYYY-MM-DD` string
    """
    return _without_empty(
        {
            "id": version.id,
            "format": version.format,
            "sha256": version.sha256,
            "license": version.license,
            "file": version.file,
            "derived_from": version.derived_from,
            "added": version.added.isoformat(),
            "notes": version.notes,
            "source": None if version.source is None else _source_to_dict(version.source),
        }
    )


def model_to_dict(model: Model) -> dict[str, Any]:
    """Return the JSON form of a model, in the field order of `model.toml`

    Parameters
    ----------
    model : Model
        The model

    Returns
    -------
    dict[str, Any]
        The fields that are set, which `parse_model` reads back as the same model
    """
    return _without_empty(
        {
            "id": model.id,
            "name": model.name,
            "family": model.family,
            "description": model.description,
            "categories": list(model.categories),
            "keywords": list(model.keywords),
            "species": model.species,
            "cell_type": model.cell_type,
            "reviewed": model.reviewed,
            "default_version": model.default_version,
            "paper": _paper_to_dict(model.paper),
            "references": [_paper_to_dict(p) for p in model.references],
            "versions": [_version_to_dict(v) for v in model.versions],
        }
    )
