# odezoo

odezoo is a curated registry of ODE model files, mostly cell models but also others such as
Windkessel models, stored as markup: CellML or [gotranx](https://github.com/finsberg/gotranx)
`.ode`. It is a Python package with a command line interface that searches the registry and
downloads a model's file exactly as it was recorded, verified by its sha256. The registry holds
only the models chosen for it, and each model has one `model.toml` that says where its files come
from, which paper it belongs to, and how to find it.

## Install

odezoo needs Python 3.11 or later. Until the first release is on PyPI, install it from GitHub:

```
python3 -m pip install git+https://github.com/ComputationalPhysiology/odezoo
```

## Quick start

```
odezoo list                                    # every model; takes the same filters as search
odezoo search --category electrophysiology     # find models; also by text, --keyword, --species
odezoo info beeler_reuter_1977                 # paper, DOI, versions, licences, sources
odezoo fetch beeler_reuter_1977 -o models/     # writes models/beeler_reuter_1977.cellml
```

`odezoo fetch` takes several ids, so `odezoo fetch $(odezoo search --format cellml --ids)`
fetches every CellML model. `--format` picks the newest version in a format, `--version` a given
version, and `--force` overwrites a different file that is already there. A table of models
taller than the terminal opens in your pager (`$PAGER`, else `less`); `--no-pager` turns that off.

Every file is checked against the sha256 in the registry. It is taken from the cache if it is
there, otherwise from this repository's copy on GitHub, otherwise from where its authors keep it
(the Physiome Model Repository, GitHub or Zenodo). Whichever it comes from, it is the same bytes.

## From Python

```python
import odezoo

odezoo.search("ten tusscher", category="electrophysiology", format="cellml")
model = odezoo.model("beeler_reuter_1977")  # paper, keywords, versions, ...
path = odezoo.get("beeler_reuter_1977")  # the file in the cache
path = odezoo.get("beeler_reuter_1977", dest=".")  # copied to ./beeler_reuter_1977.cellml
```

With gotranx, a model's `.ode` version loads directly:

```python
import gotranx

ode = gotranx.load_ode(odezoo.get("tworld", format="ode"))
```

## Settings

| Option | Environment variable | What it does |
|---|---|---|
| `--cache-dir PATH` | `ODEZOO_CACHE_DIR` | Where downloads are kept. `odezoo cache dir` shows it, `odezoo cache clear` empties it, and `fetch --no-cache` skips it. |
| `--registry PATH` | `ODEZOO_REGISTRY` | Use a checkout of this repository instead of the registry bundled with odezoo, e.g. to try models not yet released. |

A flag beats its environment variable.

## Adding models

Each model is a folder under `models/` with a `model.toml` and the files it keeps a copy of.
`odezoo registry check` checks a checkout, and `odezoo registry add version ID FILE
--derived-from V` adds an edited file as a new version. The full guide to adding models will be
in the documentation.

## Licence

The code is MIT licensed. Each model file keeps its own licence, recorded in its `model.toml`; the
texts are in `LICENSES/`.
