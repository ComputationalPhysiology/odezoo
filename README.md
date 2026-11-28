# odezoo

odezoo is a curated registry of ODE model files, mostly cell models but also others such as
Windkessel models, stored as markup: CellML or [gotranx](https://github.com/finsberg/gotranx)
`.ode`. It is a Python package with a command line interface that searches the registry and
downloads a model's file exactly as it was recorded, verified by its sha256. The registry holds
only the models chosen for it, and each model has one `model.toml` that says where its files come
from, which paper it belongs to, and how to find it.

## Install

odezoo needs Python 3.11 or later.

```
python3 -m pip install odezoo
```

Each release bundles the registry as it was then. For models added since the last release,
install from GitHub:

```
python3 -m pip install git+https://github.com/ComputationalPhysiology/odezoo
```

The documentation, with a page for every model and a search, is at
<https://computationalphysiology.github.io/odezoo>.

### AI agent skill

odezoo ships an [agent skill](https://agentskills.io) that helps you find the right published
model: it checks your environment, asks what the model is for (species, cell type, downstream use),
proposes candidates and how to deliver the file, fetches a pinned version and checks that it loads
in gotranx.

- **Claude Code:** `/plugin marketplace add ComputationalPhysiology/odezoo` then
  `/plugin install odezoo@odezoo`
- **Other agents** (Codex, Gemini CLI, GitHub Copilot, Cursor, OpenCode, ...):
  `npx skills add ComputationalPhysiology/odezoo --skill odezoo-models`
- **Manually:** copy [`plugins/odezoo/skills/odezoo-models`](https://github.com/ComputationalPhysiology/odezoo/tree/main/plugins/odezoo/skills/odezoo-models)
  into your agent's skills directory (e.g. `~/.claude/skills/`).

See [Using odezoo with an AI agent](#using-odezoo-with-an-ai-agent) below.

## Quick start

```
odezoo list                                    # every model; takes the same filters as search
odezoo search --category electrophysiology     # find models; also by text, --keyword, --species
odezoo values species                          # each species and its number of models
odezoo info beeler_reuter_1977                 # paper, DOI, versions, licences, sources
odezoo fetch beeler_reuter_1977 -o models/     # writes models/beeler_reuter_1977.cellml
```

`odezoo fetch` takes several ids, so `odezoo fetch $(odezoo search --format cellml --ids)`
fetches every CellML model. `--format` picks the newest version in a format, `--version` a given
version, and `--force` overwrites a different file that is already there. A table of models
taller than the terminal opens in your pager (`$PAGER`, else `less`); `--no-pager` turns that off.
`odezoo values` also counts categories, keywords, families, formats and cell types, and takes the
same filters, so `odezoo values family --species human` lists the families of human models.

Every file is checked against the sha256 in the registry. It is taken from the cache if it is
there, otherwise from this repository's copy on GitHub, otherwise from where its authors keep it
(the Physiome Model Repository, GitHub or Zenodo). Whichever it comes from, it is the same bytes.

## From Python

```python
import odezoo

odezoo.search("ten tusscher", category="electrophysiology", format="cellml")
odezoo.values("species")  # {"human": 14, "guinea pig": 8, ...}
model = odezoo.model("beeler_reuter_1977")  # paper, keywords, versions, ...
path = odezoo.get("beeler_reuter_1977")  # the file in the cache
path = odezoo.get("beeler_reuter_1977", dest=".")  # copied to ./beeler_reuter_1977.cellml
```

With gotranx, a model's `.ode` version, where it has one, loads directly:

```python
import gotranx

ode = gotranx.load_ode(odezoo.get(model_id, format="ode"))
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
--derived-from V` adds an edited file as a new version.

`odezoo registry add url URL --id ID [--license SPDX]` downloads a file and adds it, as a new model
or a new version of one. GitHub and PMR URLs are pinned to a commit (for PMR, use the file's
`rawfile` URL with the full commit id). A new model gets only its id; fill in its name, paper and
categories, then run `odezoo registry check`. The documentation has the full guide to adding
models, and [CONTRIBUTING.md](CONTRIBUTING.md) the steps for a pull request, including building
the documentation.

## Using odezoo with an AI agent

The `odezoo-models` skill (installed as above) turns a coding agent into a guide for choosing and
fetching published models. It

- checks that odezoo is installed, whether the installed registry has the model you need, and
  whether the machine that will run the simulation has network access;
- asks you, one question at a time, about your goal, species and cell type, the package that will
  use the model, and whether the file will be committed or shared;
- proposes two or three candidate models with their trade-offs (number of states, review status,
  format, licence, cell types as separate models or as a parameter) and ways to deliver the file
  (in the project folder, or fetched at run time with a pinned version), and recommends one;
- fetches the file, converts it with gotranx where needed, and reports what to check in it (time
  unit, membrane potential, the model's own stimulus, the cell-type parameter);
- knows the common pitfalls (a pager waiting for a key press, unpinned versions changing after an
  update, offline compute nodes, licences);
- covers adding a model to the registry, for contributors;
- never installs anything without asking.

Describe what you want, for example

> I need a human ventricular cell model with endo and epi variants for a tissue simulation in
> fenicsx-beat

and the agent loads the skill on its own; or invoke it explicitly (`/odezoo:odezoo-models` in
Claude Code, `/odezoo-models` if you copied the folder). Update it with
`/plugin marketplace update odezoo` or `npx skills update`.

## Licence

The code is MIT licensed. Each model file keeps its own licence, recorded in its `model.toml`; the
texts are in `LICENSES/`.
