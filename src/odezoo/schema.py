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
    title: str
    authors: tuple[str, ...]
    journal: str
    year: int
    doi: str | None = None
    pubmed: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class Source:
    """Where upstream keeps a file; which fields are set depends on `type`"""

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
        """A page about the file for people to open, rather than the file itself"""
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
        return FORMATS[self.format]


@dataclass(frozen=True)
class Model:
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
        return tuple(dict.fromkeys(v.format for v in self.versions))

    def version(self, id: str) -> Version:
        for v in self.versions:
            if v.id == id:
                return v
        ids = ", ".join(v.id for v in self.versions)
        raise VersionNotFound(f"{self.id} has no version {id!r}; it has {ids}")


def normalize_keyword(text: str) -> str:
    return " ".join(text.lower().split())


class _Fields:
    """Typed access to one TOML table, with errors that name the file and the field"""

    def __init__(self, data: Any, where: str, prefix: str = ""):
        self.where = where
        self.prefix = prefix
        if not isinstance(data, Mapping):
            raise self.error("", "must be a table")
        self.data = data

    def name(self, key: str) -> str:
        return f"{self.prefix}.{key}" if self.prefix and key else self.prefix or key

    def error(self, key: str, message: str) -> RegistryError:
        return RegistryError(message, where=self.where, field=self.name(key) or None)

    def only(self, allowed: tuple[str, ...]) -> None:
        for key in self.data:
            if key not in allowed:
                raise self.error(key, "unknown field")

    def _get(self, key: str, kinds: tuple[type, ...], what: str, required: bool) -> Any:
        value = self.data.get(key)
        if value is None:
            if required:
                raise self.error(key, "is required")
            return None
        if isinstance(value, bool) and bool not in kinds or not isinstance(value, kinds):
            raise self.error(key, f"must be {what}")
        return value

    def string(self, key: str, required: bool = False) -> str | None:
        value = self._get(key, (str,), "a string", required)
        if value is not None and not value.strip():
            raise self.error(key, "must not be empty")
        return value

    def required_string(self, key: str) -> str:
        value = self.string(key, required=True)
        assert value is not None
        return value

    def integer(self, key: str, required: bool = False) -> int | None:
        return self._get(key, (int,), "an integer", required)

    def boolean(self, key: str) -> bool:
        return self._get(key, (bool,), "true or false", True)

    def strings(self, key: str, required: bool = False) -> tuple[str, ...]:
        value = self._get(key, (list, tuple), "a list of strings", required)
        if value is None:
            return ()
        if not all(isinstance(item, str) and item.strip() for item in value):
            raise self.error(key, "must be a list of non-empty strings")
        return tuple(value)

    def table(self, key: str, required: bool = False) -> _Fields | None:
        value = self._get(key, (Mapping,), "a table", required)
        return None if value is None else _Fields(value, self.where, self.name(key))

    def tables(self, key: str) -> list[_Fields]:
        value = self._get(key, (list, tuple), "a list of tables", False)
        if value is None:
            return []
        return [_Fields(item, self.where, f"{self.name(key)}[{i}]") for i, item in enumerate(value)]

    def date(self, key: str) -> date:
        value = self._get(key, (date, str), "a date (YYYY-MM-DD)", True)
        if isinstance(value, datetime):
            raise self.error(key, "must be a date (YYYY-MM-DD), not a date and time")
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise self.error(key, "must be a date (YYYY-MM-DD)") from None


def _paper(f: _Fields, *, with_note: bool) -> Paper:
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
    return paper


def _source(f: _Fields) -> Source:
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
    if "commit" in values and not GIT_COMMIT.match(values["commit"]):
        raise f.error("commit", "must be a full commit id: 40 lowercase hex characters")
    if type == "github" and not GITHUB_REPO.match(values["repo"]):
        raise f.error("repo", "must be owner/name")
    for key in ("workspace", "exposure", "url"):
        if values.get(key) and not values[key].startswith(("http://", "https://")):
            raise f.error(key, "must be an http:// or https:// URL")
    return Source(type=type, **values)


def _version(f: _Fields) -> Version:
    f.only(VERSION_FIELDS)
    id = f.required_string("id")
    if not VERSION_ID.match(id):
        raise f.error("id", f"{id!r} must match {VERSION_ID.pattern}")
    format = f.required_string("format")
    if format not in FORMATS:
        raise f.error("format", f"must be one of {', '.join(FORMATS)}, not {format!r}")
    sha256 = f.required_string("sha256")
    if not SHA256.match(sha256):
        raise f.error("sha256", "must be 64 lowercase hex characters")
    license = f.required_string("license")
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

    Raises `RegistryError` naming `where` and the field at the first rule that is broken.
    """
    f = _Fields(data, where)
    f.only(MODEL_FIELDS)

    id = f.required_string("id")
    if not MODEL_ID.match(id):
        raise f.error("id", f"{id!r} must match {MODEL_ID.pattern}")
    family = f.string("family")
    if family is not None and not MODEL_ID.match(family):
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
    for i, v in enumerate(versions):
        if ids.index(v.id) != i:
            raise f.error(f"versions[{i}].id", f"version id {v.id!r} is used twice")
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
    return {key: value for key, value in data.items() if value is not None and value != []}


def _paper_to_dict(paper: Paper) -> dict[str, Any]:
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
    required, optional = SOURCE_FIELDS[source.type]
    return _without_empty(
        {"type": source.type, **{key: getattr(source, key) for key in required + optional}}
    )


def _version_to_dict(version: Version) -> dict[str, Any]:
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
    """The JSON form of a model, in the field order of `model.toml`; `parse_model` reads it back"""
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
