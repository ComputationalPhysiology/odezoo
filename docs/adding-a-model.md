# Adding a model

A model is a folder in the repository, `models/<id>/`, holding a `model.toml` and, where the
licence allows, a copy of each of its files. Adding one is a pull request. Work in a checkout,
with odezoo installed from it (`python3 -m pip install -e ".[dev]"`), and pass `--registry .` (or
set `ODEZOO_REGISTRY=.`) so that the commands see your changes.

## From a URL

`odezoo registry add url` downloads a file and adds it, as a new model or as a new version of an
existing one:

```
odezoo --registry . registry add url URL --id ID --license SPDX
```

The URL decides what kind of source the version records:

| URL | Source | Version id |
|---|---|---|
| A GitHub `blob` or `raw` URL, or `raw.githubusercontent.com` | `github`, pinned to the commit; a branch or tag is resolved to its commit | `github-<7 hex>` |
| A Zenodo record file, `https://zenodo.org/records/<n>/files/<name>` | `zenodo` | `zenodo-<record>` |
| A PMR file at a commit, `https://models.physiomeproject.org/workspace/<name>/rawfile/<commit>/<file>` | `pmr` | `pmr-<7 hex>` |
| Any other `http(s)` URL | `url`, kept as given | `url-<date>` |

For PMR, use the file's `rawfile` URL with the full 40-character commit id; an exposure or a page
URL is refused with a message saying which URL to use. The file must end in `.cellml` or `.ode`,
and CellML that uses `<import>` is refused, since odezoo keeps one file per version. `--dry-run`
says what would be added without writing anything.

A new model gets only its id. Open its `model.toml` and fill in at least its `name`, its
`categories` (from PMR's 20, such as `electrophysiology`) and its `[paper]`, with a DOI or a
PubMed id; add `species`, `cell_type`, `keywords`, `family` and `description` where they help
people find it. Species and cell types are plain names (`odezoo values species` lists those in
use); notes belong in the `description`. A model is `reviewed = true` only once someone has run it
and compared it with its paper.

## Licences

Every version records its licence as an SPDX id, or `unknown`. A copy of the file is kept in the
repository only when the licence allows redistribution (`CC-BY-3.0`, `CC-BY-4.0`, `CC0-1.0`,
`MIT`, the BSD and Apache licences, and the GPL and LGPL family); otherwise the version has only
its source, and odezoo fetches it from there.

- The text of each licence a kept copy is under is in `LICENSES/<SPDX id>.txt`; add it if it is
  not there yet.
- MIT and BSD ask for the copyright notice to go with every copy, so a model that keeps a copy
  under them also has upstream's licence file, with its copyright line, as `models/<id>/LICENSE`.

## Our own versions

An edited file, such as a CellML file converted to `.ode`, is a new version of the same model:

```
odezoo --registry . registry add version ID FILE --derived-from V --notes "what changed, and why"
```

It gets the next id `v1`, `v2`, …, records the version it was derived from, and takes that
version's licence unless `--license` says otherwise.

## Versions never change

A file's identity is its sha256, so a recorded file is never changed in place: a changed file is
a new version. Once a version is on `main`, its `id`, `format`, `sha256` and `file` stay as they
are, and it is never removed; only its `license` and `notes` may be corrected. The model's own
fields, such as its name, species or description, can be edited freely.

## Checking, and the pull request

```
odezoo --registry . registry check
```

checks every model: the fields of each `model.toml`, that each kept file has its recorded sha256,
the licence texts, and that CellML files have no `<import>`. It must pass before you commit.

On the pull request, CI runs the same check, checks that no version already on `main` was changed
or removed, and downloads each version the pull request adds from its source to compare its
sha256.
