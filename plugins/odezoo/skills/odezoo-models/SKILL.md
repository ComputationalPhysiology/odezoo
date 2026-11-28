---
name: odezoo-models
description: Find, compare and fetch published cardiac cell, contraction and circulation models from the odezoo registry (CellML and gotranx .ode files, verified by sha256) — search by species, cell type and category, read a model's paper, licence and review status, pin a version for reproducibility, work offline from a cache, and hand the file to gotranx, fenicsx-beat, sknm or simcardemsx. Use when the user asks which cell model to use, needs a specific published model (ten Tusscher, O'Hara-Rudy, ToR-ORd, Courtemanche, Land, ...), wants a reproducible pinned model file, needs models on an offline cluster, or wants to add a model to the registry.
---

# Finding and fetching published models with odezoo

odezoo is a curated registry of published ODE model files: mostly cardiac cell models
(electrophysiology), plus contraction (myofilament) and circulation models. Each model has a
paper, a licence, a review flag and one or more versions; a version is one file (CellML or gotranx
`.ode`) identified by its sha256, so a fetched file is exactly the file that was recorded. Two
ways to drive it:

- **Command line**: `odezoo list`, `odezoo search`, `odezoo values`, `odezoo info`,
  `odezoo fetch`. Good for exploring and for putting files in a project folder.
- **Python**: `odezoo.search`, `odezoo.model`, `odezoo.get`. Good inside simulation scripts, with
  a pinned version.

odezoo does not simulate anything and does not convert formats: gotranx turns the file into code,
and fenicsx-beat, sknm or simcardemsx use that code.

Your job: find out what the user needs the model for, agree on a model and on how to deliver the
file, fetch it, and check that it loads before they rely on it. Work through the five steps below in
order. Ask **one question at a time** (use your agent's question tool if it has one, otherwise ask
in plain text).

Reference files (read when a step needs them):

- [install.md](install.md) — installing odezoo, and what is needed to use the files
- [choosing.md](choosing.md) — searching, filters, reading `info`, which models cover what
- [fetching.md](fetching.md) — command line or Python, pinning, the cache, offline clusters,
  handing the file to gotranx
- [adding.md](adding.md) — adding a model or a version to the registry (maintainers and
  contributors)
- [gotchas.md](gotchas.md) — things that go wrong, and settings that work better

## Step 1: Check the environment

```bash
python -c "import odezoo; print(odezoo.__version__)"
odezoo values category
```

- **Version.** This skill describes odezoo 0.2 or later (`odezoo values` and the `--no-pager`,
  `--ids` and `--json` options). If `odezoo values category` fails, recommend upgrading
  (`python -m pip install -U odezoo`).
- **The registry is part of the install.** A pip install carries the registry as it was at that
  release. If the user needs a model added since, they need a newer release, a git install, or a
  checkout passed with `--registry` ([install.md](install.md)).
- **Network.** Fetching a file not yet in the cache needs GitHub or the upstream host. Ask whether
  the machine where the simulation runs is online; compute nodes often are not
  ([fetching.md](fetching.md)).
- Later, check what the next step needs: gotranx to load or convert the file (CellML conversion
  also needs myokit, which gotranx installs).
- **Never install anything without asking.** Show the command and let the user run or approve it.

Always pass `--no-pager`, `--ids` or `--json` to `odezoo list` and `odezoo search`: on a terminal a
long table opens a pager and waits for a key press. `info` and `values` do not page (and have no
`--no-pager`).

## Step 2: Interview the user

Ask one question at a time, multiple choice with an "other" option, and say why it matters when that
is not obvious. Skip a topic the user already answered (confirm instead). If they name an exact model
("fetch Courtemanche"), confirm the id with `odezoo search` and go straight to topic 3. Topics, in
order:

1. **Goal** — choose a model for a study; get a model they already know; pin a model so a study
   can be reproduced; add a model to the registry (then follow [adding.md](adding.md) instead of
   the steps below).
2. **Constraints** — species (human, rabbit, guinea pig, ...); region and cell type (ventricle,
   atrium, sinoatrial node, Purkinje; endocardial, midmyocardial, epicardial); category
   (electrophysiology, myofilament mechanics, circulation); whether only reviewed models will do;
   how much cost they can afford (number of states, stiffness) for tissue runs. See
   [choosing.md](choosing.md).
3. **Downstream use** — which package consumes it (gotranx on its own, fenicsx-beat, sknm,
   simcardemsx), whether it will be coupled to another model (an electrophysiology model to a
   contraction model), and whether the file will be committed to a repository or shared (licences
   differ, [gotchas.md](gotchas.md)).
4. **Environment** — internet access where the simulation runs, and where downloads should be
   kept (the cache folder, or the project folder).

## Step 3: Propose alternatives

Present **2–3 candidate models with trade-offs and a recommendation**: species and cell type,
number of states (cost in tissue; [choosing.md](choosing.md) lists them for common models, otherwise
load the file), reviewed or not, format (CellML needs conversion, `.ode` loads directly), licence,
and whether cell types are separate ids or a parameter in one file (this matters for a tissue with
several cell types, [choosing.md](choosing.md)). Get the facts from `odezoo info <id> --json`
rather than memory: only the JSON has the model's description. If the user named the model, skip
the candidates: confirm the id, show its versions and licence, and go on to the delivery. Then the
**delivery**:

- **Files in the project folder** (`odezoo fetch <id> -o models/`): the file sits next to the
  code, works offline afterwards, and can be committed if its licence allows it. Recommended for
  a study that will be published.
- **Fetched at run time and pinned** (`odezoo.get("<id>", version="<version id>")`, one call per
  model): nothing to
  commit, the cache serves it after the first time; needs network on first use on each machine.
- **A registry checkout or git install**: only for a model newer than the installed release.

Then **summarise the choice** in a few lines (model id, version id, format, where the file goes,
how it will be converted, cell-type selection, stimulus handling) and get an explicit yes before
fetching.

## Step 4: Fetch

```bash
odezoo info tentusscher_2006_epi
odezoo fetch tentusscher_2006_epi --version pmr-5dc4239 -o models/
```

`--version` works with one model id only: to pin several models, run one `fetch` per model.

or in Python

```python
from pathlib import Path

import odezoo

Path("models").mkdir(exist_ok=True)  # dest must be an existing folder, or it is a file name
path = odezoo.get("tentusscher_2006_epi", version="pmr-5dc4239", dest="models")
```

Before using an odezoo function, read its signature in the installed version
(`python -c "import odezoo, inspect; print(inspect.signature(odezoo.get))"`, `odezoo fetch --help`).
The sha256 is checked on every fetch; there is nothing extra to verify. Details, the cache and
offline machines: [fetching.md](fetching.md).

## Step 5: Check, then hand over

1. **The file loads.** A `.ode` file: `gotranx.load_ode(path)`. A CellML file:
   `gotranx cellml2ode models/<id>.cellml -o models/<id>.ode`, then load the `.ode` file. Print
   `ode.num_states` and `ode.num_parameters` and compare with the paper (or the table in
   [choosing.md](choosing.md)). For a first look, `gotranx.load_ode(path, remove_singularities=False)`
   is fast; with gotranx's default guards some models take minutes and print "Dropping a guard"
   warnings, which are expected ([gotchas.md](gotchas.md)).
2. **Read the converted model** before anyone uses it ([fetching.md](fetching.md)): its time unit
   (most CellML electrophysiology models are in ms, the contraction `.ode` files in s), the name of
   the membrane potential, the model's own stimulus (amplitude, start, period, end), and the
   parameter that selects the cell type, if any.
3. If the gotranx-odes skill is available, continue with its Step 5 (one beat against a
   reference). Otherwise generate Python code (`gotranx ode2py models/<id>.ode -o <id>.py`), and run
   one beat with the model's own stimulus using the generated `rhs` and
   `scipy.integrate.solve_ivp(method="BDF", max_step=<half the stimulus duration>)`: the membrane
   potential should make an upstroke and return to rest. For a tissue solver, see
   [fetching.md](fetching.md) for what it needs from the file.
4. **Hand over**: the model id, the version id, the sha256 (`odezoo info <id> --json`), the
   licence, where the file is, and the exact fetch command or `odezoo.get` call, so the study can
   be reproduced.

## Related skills

- **gotranx-odes** — converting the file and generating code (schemes, backends, composing an
  electrophysiology model with a contraction model); otherwise see
  https://finsberg.github.io/gotranx.
- **crossbridge-models** — the contraction models (Land, Rice, ...) and how to couple them;
  otherwise see https://computationalphysiology.github.io/crossbridge.
- **circulation-simulation** — closed-loop circulation models; otherwise see
  https://computationalphysiology.github.io/circulation.
- **beat-simulation**, **sknm-simulation**, **simcardemsx-simulation** — using the model in a
  tissue, cell-network or electromechanics simulation; otherwise see
  https://finsberg.github.io/fenicsx-beat, https://github.com/ComputationalPhysiology/sknm and
  https://computationalphysiology.github.io/simcardemsx.

Use a related skill if it is available; if not, follow the link.

## Ground rules

- **Do not invent model ids, version ids or options.** Check `odezoo search`, `odezoo info` and
  `--help`. If a model is not in the registry, say so and offer the closest that is (or a CellML
  file from the Physiome Model Repository, outside odezoo).
- **Pin the version** in anything that will be rerun: the default version can change when the
  registry is updated.
- **Respect licences**: each version has its own (most are CC-BY-3.0, the ToR-ORd and T-World
  files are GPL-3.0-only, the `.ode` contraction and circulation files MIT). Tell the user before
  they commit or redistribute a file.
- **Units and stimulus**: check the time unit and the model's own stimulus before coupling or
  simulating ([gotchas.md](gotchas.md)).
- Top pitfalls (all in [gotchas.md](gotchas.md)): a pager hanging the agent; the bundled registry
  being the release snapshot; cell type as a parameter in one file versus separate ids; an unpinned
  default version changing; a fetch refusing to overwrite a different file.
