# Adding a model to the registry

For contributors and maintainers. Adding a model is a pull request to
https://github.com/ComputationalPhysiology/odezoo; the repository's own guide is
[docs/adding-a-model.md](https://github.com/ComputationalPhysiology/odezoo/blob/main/docs/adding-a-model.md),
and its `AGENTS.md` has the rules for agents working in a checkout. Read both before starting.

## Interview (instead of Step 2 of the skill)

1. **Where the file is** — a GitHub file, a Zenodo record, a Physiome Model Repository (PMR) file at
   a commit, or another URL; or an edited file of an existing model (for example CellML converted
   to `.ode`).
2. **Its licence** (an SPDX id such as `CC-BY-4.0`, `MIT`, `GPL-3.0-only`, or `unknown`). It decides
   whether a copy is kept in the repository.
3. **The paper** (DOI or PubMed id), species, cell type, category, keywords, and whether it is one
   of several cell-type variants (a family).
4. **Has it been run and compared with the paper?** Only then is it `reviewed = true`.

## Work in a checkout

```bash
git clone https://github.com/ComputationalPhysiology/odezoo
cd odezoo
python -m pip install -e ".[dev]"
```

Pass `--registry .` to every command (or set `ODEZOO_REGISTRY=.`) so that it sees the checkout and
not the installed registry. Never push or open a pull request without the maintainer's go-ahead, and
stage files by name.

## From a URL

```bash
odezoo --registry . registry add url URL --id ID --license SPDX --dry-run
odezoo --registry . registry add url URL --id ID --license SPDX
```

| URL | Version id |
|---|---|
| GitHub `blob` or `raw` URL (a branch or tag is resolved to its commit) | `github-<7 hex>` |
| `https://zenodo.org/records/<n>/files/<name>` | `zenodo-<record>` |
| PMR `https://models.physiomeproject.org/workspace/<name>/rawfile/<40-hex commit>/<file>` | `pmr-<7 hex>` |
| any other `http(s)` URL | `url-<date>` |

- The file must end in `.cellml` or `.ode`. CellML with `<import>` is refused: odezoo keeps one file
  per version.
- For PMR use the `rawfile` URL with the full commit id; an exposure or page URL is refused with a
  message saying which URL to use.
- A new model gets only its id. Then edit `models/<id>/model.toml`: at least `name`, `categories`
  (PMR's categories, e.g. `electrophysiology`) and `[paper]` with a DOI or PubMed id; add `species`,
  `cell_type`, `keywords`, `family` and `description` where they help people find it. Plain names
  for species and cell types (`odezoo values species` lists those in use). Put notes, such as which
  parameter selects the cell type, in the `description`.

## Our own version of a model

An edited file is a new version of the same model, never a change to an existing one:

```bash
odezoo --registry . registry add version ID FILE --derived-from V --notes "what changed, and why"
```

It gets the next id (`v1`, `v2`, ...) and takes the licence of `--derived-from` unless `--license`
is given.

## Licences

A copy of the file is kept in `models/<id>/` only under a licence that allows redistribution
(CC-BY, CC0, MIT, BSD, Apache, the GPL and LGPL family); otherwise the version records only its
source and odezoo fetches it from there. Each licence a kept copy is under needs its text in
`LICENSES/<SPDX id>.txt`; MIT and BSD copies also need upstream's licence file with its copyright
line as `models/<id>/LICENSE`.

## Check before committing

```bash
odezoo --registry . registry check
python -m pytest
pre-commit run --all-files
```

`registry check` checks every `model.toml`, the sha256 of each kept file, the licence texts, and that
CellML files have no `<import>`. On the pull request, CI also checks that no version already on
`main` changed or was removed, and downloads each new version from its source to compare the
sha256.

## Rules that are easy to break

- A recorded file is never changed in place, and a version on `main` is never removed: its `id`,
  `format`, `sha256` and `file` are fixed (only `license` and `notes` may be corrected).
- Files under `models/` and `LICENSES/` are kept byte for byte. Do not let an editor or a formatter
  touch them (no trailing-whitespace or line-ending fixes).
- Tests never reach the network; a new test uses the fake HTTP server in `tests/helpers.py`.
- Prose and messages are in British English ("licence").
