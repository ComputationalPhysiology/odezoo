# AGENTS.md

Instructions for coding agents, and for people, working in this repository. `CLAUDE.md` imports
this file.

## What odezoo is

odezoo is a curated registry of ODE model files, mostly cell models but also others such as
Windkessel models. Models are stored as markup only: CellML (`.cellml`) or gotranx `.ode`. The
package and its `odezoo` command line search the registry and fetch a model's file exactly as it
was recorded, verified by its sha256. Each model is one folder, `models/<id>/`, holding a
`model.toml` and, where the licence allows, copies of the model's files.

## Setup and commands

odezoo supports Python 3.11 and later. The devcontainer in `.devcontainer/` uses Python 3.15 and
runs the setup below by itself.

```
python3 -m pip install -e ".[dev]"            # editable install, with test and dev tools
pre-commit install
python3 -m pytest                             # the suite (network tests are deselected)
python3 -m pytest tests/test_cli.py::test_name -v
pre-commit run --all-files                    # ruff (lint and format), mypy, cspell, hygiene
odezoo --help
odezoo registry check                         # check every model in this checkout
```

The install bundles the models into `src/odezoo/registry.json` (git-ignored), through the
hatchling build hook in `hatch_build.py`. After changing `models/`, use `--registry .` (or
`ODEZOO_REGISTRY=.`) to work with the checkout, or reinstall to refresh the bundled registry.

## Layout

| Path | What it holds |
|---|---|
| `src/odezoo/schema.py` | The dataclasses behind `model.toml` (`Model`, `Version`, `Source`, `Paper`), and `parse_model`, which checks every rule that needs no files |
| `src/odezoo/registry.py` | Reading a checkout or the bundled `registry.json`; `build` writes the latter |
| `src/odezoo/search.py`, `resolve.py` | Search, and choosing which version to fetch |
| `src/odezoo/http.py` | The one HTTP client: requests to a host are spaced out, only 429 and 503 are retried |
| `src/odezoo/cache.py` | The download cache, keyed by sha256 (`--cache-dir`, `ODEZOO_CACHE_DIR`) |
| `src/odezoo/fetch.py` | Getting a file: checkout, then cache, then this repository on GitHub (pinned to the registry's commit), then upstream; every candidate is checked against the sha256 |
| `src/odezoo/api.py` | The Python API (`models`, `model`, `search`, `get`), re-exported by `odezoo/__init__.py` |
| `src/odezoo/cli.py`, `render.py` | The argparse command line, and its rich output |
| `src/odezoo/maintain/` | Maintainer commands: `check.py` (`registry check`), `version.py` (`registry add version`), `toml.py` (writes `model.toml`) |
| `models/<id>/` | One model: `model.toml`, and copies named `<version id>.<ext>` |
| `LICENSES/` | The text of each licence a kept copy is under, as `<SPDX id>.txt` |
| `tests/` | The suite; `conftest.py` and `helpers.py` hold the fixtures and the fake HTTP server |

## Code

- The only runtime dependency is `rich`. Ask the maintainer before adding another: argparse was
  chosen over typer, and pydantic and platformdirs were turned down, to keep the install light.
- `import odezoo` must not import rich (a test checks). Only `cli.py` and `render.py` use rich, and
  the command handlers import `render` when they need it.
- Modules import each other relatively (`from .schema import Model`, `from ..fetch import
  sha256_hex`), never as `odezoo.…` (a test checks).
- Every function and class has a NumPy-style docstring written like the existing ones (ruff's `D`
  rules, numpy convention, check the public ones):
  - `name : type`, or `name : type, optional` with "by default …"
  - a summary line in the imperative, without a final full stop
  - `Returns` and `Raises` sections
  - constructor parameters in the class docstring
  - single backticks, because the documentation is MyST
- Code must run on Python 3.11, so use no syntax or library features from later versions.
- An error the user can cause is an `OdezooError` subclass (`errors.py`) whose message says what
  to do about it. The command line prints it on one line, without a traceback, and exits with 1.
- Write prose and messages in British English (the noun is "licence"). cspell checks `src/`,
  `tests/`, `docs/` and the README; add real words to `cspell.config.yaml`.
- Lines are at most 100 characters. Ruff, mypy and cspell must pass (`pre-commit run --all-files`).

## Tests

- Tests never reach the network. pytest-socket blocks every host but localhost, and downloads
  come from the `http_server` fixture (`FakeServer` in `tests/helpers.py`). PMR, GitHub, Zenodo
  and NCBI must not see requests from test runs, or they may block us.
- A test that needs the real network is marked `@pytest.mark.network`. It is deselected by
  default, and is run by hand only (`pytest -m network`), and rarely.
- Write the failing test first, watch it fail, then write the code.
- CI runs the suite on Linux, macOS and Windows with every supported Python. Mind paths,
  encodings (Windows consoles may be cp1252) and line endings.

## The registry

- A file's identity is its sha256, so a model file is never changed in place: a changed file is a
  new version (`odezoo registry add version ID FILE --derived-from V`).
- Versions are append-only. Once a version is on `main`, its `id`, `format`, `sha256` and `file`
  never change and it is never removed; only its `license` and `notes` may be corrected.
- Version ids: `pmr-<7 hex>`, `github-<7 hex>`, `zenodo-<record>` or `url-<date>` for upstream
  files, and `v1`, `v2`, … for our own.
- A copy is kept in `models/<id>/` only under a licence in `MIRROR_LICENSES` (`schema.py`), with
  the licence text in `LICENSES/`. Otherwise the version has only a `source`.
- `.gitattributes` keeps `models/**` byte for byte (`-text`), and the whitespace hooks skip
  `models/` and `LICENSES/`. Never let a tool rewrite those files.
- `odezoo registry check`, run in the checkout, must pass before committing a change to
  `models/`.

## Git

- Never push, and never open a pull request, without the maintainer's go-ahead. Before a push,
  check where it goes: `git -C <absolute path of this checkout> remote get-url --push origin`.
- Stage files by name, not with `git add -A`: maintainers keep untracked local files here.
- `docs/superpowers/` and `.superpowers/` hold the maintainer's local planning files (specs,
  plans, ledgers, a handoff). They are excluded from git and never committed. If
  `docs/superpowers/HANDOFF.md` exists, read it before starting work.
