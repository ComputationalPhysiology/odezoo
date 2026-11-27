# Contributing to odezoo

Contributions are welcome: new models, corrections to a model's details, bug fixes and
improvements to the code and the documentation. Every change is a pull request against `main`.

The rules for the code and the registry are in [AGENTS.md](AGENTS.md). It is written for coding
agents and for people alike, so read it before your first pull request. This guide covers the
steps: setting up, testing, checking the documentation, and making a release.

## Setting up

odezoo needs Python 3.11 or later. Building the documentation also needs Node; CI uses Node 22.

```
git clone git@github.com:ComputationalPhysiology/odezoo.git
cd odezoo
python3 -m pip install -e ".[dev]"     # editable install, with the test and docs tools
pre-commit install                     # ruff, mypy, cspell and the hygiene hooks, on commit
```

The repository has a devcontainer (`.devcontainer/`) that does all of this by itself.

The install bundles the models into `src/odezoo/registry.json`. After changing `models/`, pass
`--registry .` (or set `ODEZOO_REGISTRY=.`) so that `odezoo` sees the checkout, not the bundle.

## Testing

```
python3 -m pytest                      # the suite; tests never reach the network
pre-commit run --all-files             # lint, format, types and spelling
odezoo --registry . registry check     # every model, if you changed models/
```

Write the failing test first, then the code. CI runs the suite on Linux, macOS and Windows with
every supported Python, so mind paths, encodings and line endings.

## Adding or changing a model

[Adding a model](docs/adding-a-model.md) in the documentation walks through it. In short:

- Add a model or a version with `odezoo --registry . registry add url URL --id ID --license SPDX`,
  then fill in its `model.toml`.
- A model file is never changed in place. A changed file is a new version:
  `odezoo --registry . registry add version ID FILE --derived-from V`.
- `odezoo --registry . registry check` must pass before you commit.

## The documentation

The site is built with [mystmd](https://mystmd.org) from `docs/`. The pages for each model, the
search page, the simulations page and the API reference are generated at build time, so
generate them first:

```
odezoo --registry . registry build -o registry.json
python3 tools/simulate_models.py registry.json models docs/simulations
python3 tools/generate_model_pages.py registry.json docs docs/simulations
python3 tools/generate_api_pages.py docs/api
rm registry.json
```

The generated files are git-ignored. Run the commands again after changing `models/` or the
docstrings of `odezoo.api`, `odezoo.schema` or `odezoo.errors`.

`simulate_models.py` loads every model's default version with gotranx and integrates it for 3 s,
each in its own process with a time limit (`--timeout`, 300 s), and writes a figure per model and
`status.json`. It takes several minutes; `--only ID ...` simulates only some models, and leaving
out the step (and the last argument of `generate_model_pages.py`) gives pages that say the
simulation did not run. A model that fails is reported on its page and on the simulations page,
never as an error. CI runs the tool's tests in the docs job, the one job with gotranx installed:
`python3 -m pytest tests/test_simulate_models.py tests/test_model_pages.py`.

All `myst` commands run in `docs/`, with Node told to prefer IPv4. Otherwise the theme server and
the content server may each take a different `localhost` and fail to find each other ("No site
configuration found").

```
cd docs
export NODE_OPTIONS=--dns-result-order=ipv4first
```

### Preview while writing

```
myst start
```

This serves the site at <http://localhost:3000> and rebuilds a page when you save it.

### Build as CI does

```
myst build --html --strict
python3 -m http.server -d _build/html 8000
```

Open <http://localhost:8000>. `--strict` turns every warning into an error, as in CI. CI also
runs the search page's tests, with `node --test "docs/_static/*.test.mjs"` from the repository
root.

### Check the site CI built for a pull request

The Docs workflow of each pull request uploads the built site as an artifact named
`github-pages`. It is built to be served at `/odezoo/`, where GitHub Pages serves it. Served from
`/`, its stylesheets and links are not found and the pages look broken. Put it in a folder named
`odezoo`:

```
unzip github-pages.zip                 # holds artifact.tar
mkdir -p site/odezoo
tar -xf artifact.tar -C site/odezoo
python3 -m http.server -d site 8000
```

Open <http://localhost:8000/odezoo/>.

## Pull requests

- Work on a branch, and stage files by name: `git add -A` would sweep up untracked local files.
- Before you push, run `python3 -m pytest` and `pre-commit run --all-files`, and the registry
  check if you changed `models/`.
- CI runs the tests (which include the registry check), the linters and a strict build of the
  site.

## Releases

For maintainers:

1. Set the new version in `pyproject.toml` and `CITATION.cff` (a test checks they agree), and
   merge that to `main`.
2. On GitHub, go to Releases, then Draft a new release, with a new tag `v<version>` on `main`.

Publishing the release creates the tag, and `release.yml` then publishes the package to PyPI.
Zenodo archives the release. The site needs no release: `docs.yml` deploys it on every push to
`main`.
