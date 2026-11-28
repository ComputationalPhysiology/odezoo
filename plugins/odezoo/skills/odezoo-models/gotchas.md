# Gotchas

Things that go wrong with odezoo and the files it delivers, and what to do instead.

## A command hangs with no output

**What happens:** `odezoo list` or `odezoo search` waits forever when an agent runs it.
**Why:** on a terminal, a table taller than the screen opens in a pager (`$PAGER`, else `less`),
which waits for a key press.
**Do instead:** always pass `--no-pager`, `--ids` or `--json` to `list` and `search`.
<!-- verified: docs/cli.md, cli.py -->

## A model on the website is "not in the registry"

**What happens:** `odezoo info <id>` says there is no such model, though the documentation site
lists it.
**Why:** a release carries the registry as it was when it was made; the site follows `main`.
**Do instead:** install from GitHub
(`python -m pip install git+https://github.com/ComputationalPhysiology/odezoo`), or pass
`--registry <checkout>` / `registry=` to use a checkout.
<!-- verified: docs/install.md, hatch_build.py -->

## The model changes after a registry update

**What happens:** a script that calls `odezoo.get("<id>")` without a version fetches a different
file after odezoo is upgraded.
**Why:** without `version=`, odezoo takes the model's default version, else its newest; an update can
add a version.
**Do instead:** pin `version=` (or `--version`) in anything that will be rerun, and record the
sha256 (`odezoo info <id> --json`).
<!-- verified: resolve.py, docs/cli.md -->

## Only the endocardial cell is simulated

**What happens:** the user fetches `ohara_rudy_2011` or `torord_dyn_cl` for "an epicardial cell"
and gets an endocardial one.
**Why:** some models keep all cell types in one file and select one with a parameter (`celltype`:
0 endo, 1 epi, 2 mid, in `ohara_rudy_2011`, `torord_dyn_cl`, `tworld`; `epi` in `grandi_2010`);
the id and cell type in the registry name only the default. Others (`tentusscher_2006_*`,
`tentusscher_2004_*`, `sakmann_2000_*`) are separate ids with separate files.
**Do instead:** read the description in `odezoo info <id>`, and set the parameter in the generated
code or the `.ode` file.
<!-- verified: model.toml descriptions; 1 = epi, 2 = mid read from the conditionals in the converted
ohara_rudy_2011 and torord_dyn_cl files; not checked for tworld -->

## A fetch refuses to write the file

**What happens:** `odezoo fetch` prints "exists with different content; pass --force to overwrite
it" and exits with 1 (`odezoo.OutputExistsError` in Python).
**Why:** the target file exists and differs, for example because the user edited it (set the
stimulus to zero, changed the cell type).
**Do instead:** keep edits in a converted or renamed copy, not in the fetched file. Use `--force`
(`force=True`) only to throw the edits away. An identical file is left alone without `--force`.
<!-- verified: ran it -->

## `odezoo.get(..., dest="models")` writes a file called `models`

**What happens:** the model ends up in a file named `models`, not in a folder.
**Why:** `dest` that is an existing folder gets `<id>.<ext>` in it; anything else is the path of the
file. `odezoo fetch -o models/` creates the folder, `get` does not.
**Do instead:** create the folder first (`Path("models").mkdir(exist_ok=True)`), or pass the full
file name (`dest="models/land_2017.ode"`).
<!-- verified: ran it -->

## The job fails on a compute node

**What happens:** `odezoo.FetchError` listing GitHub and upstream URLs that could not be reached.
**Why:** the file is not in the cache the job uses, and the node has no network.
**Do instead:** fetch on an online node into the project folder (and use that file), or into a cache
folder the job also uses (`ODEZOO_CACHE_DIR` or `cache_dir=`). A cached file needs no network.
<!-- verified: ran get() with sockets blocked: served from cache; with an empty cache_dir: FetchError -->

## Committing or sharing a GPL or unknown-licence file

**What happens:** a model file ends up in a repository or a supplementary archive under terms the
user did not intend.
**Why:** each version has its own licence: most are CC-BY-3.0 (attribution), the `.ode` contraction
and circulation files MIT, `torord_dyn_cl` and `tworld` GPL-3.0-only. A version under a licence that
does not allow redistribution has no copy in the repository and is fetched from its source.
**Do instead:** tell the user the licence (`odezoo info <id>`) before they commit or share the file;
otherwise commit the fetch command, not the file.
<!-- verified: registry contents -->

## Coupling a contraction model to an electrophysiology model in the wrong units

**What happens:** tension rises a thousand times too fast or too slow, or the model blows up.
**Why:** most CellML electrophysiology models are in milliseconds and mM; the registry's contraction
and circulation `.ode` files are in seconds, and Land uses µM for calcium.
**Do instead:** read the header of each file and convert in the coupling (gotranx `compose`
rescales time; concentrations need converting by hand). See the gotranx-odes skill.
<!-- verified: land_2017.ode header; tools/simulate_models.py reads the time unit per model -->

## The model's own stimulus fires, or stops

**What happens:** in a tissue simulation the tissue is stimulated twice; in a long pacing run the
cell stops being paced.
**Why:** CellML cell models carry their own periodic stimulus, with their own start, period and
sometimes an end (Courtemanche: `stim_end = 50000` ms).
**Do instead:** `grep -in stim` the converted `.ode` file; set the amplitude to zero when the
tissue solver stimulates, and check the end time for long protocols. An adaptive solver needs
`max_step` at most half the stimulus duration, or it can step over the pulse.
<!-- verified: courtemanche_1998 converted .ode; max_step rule as in tools/simulate_models.py -->

## Not every registry file converts with gotranx

**What happens:** `gotranx cellml2ode` fails, or converts but the `.ode` file does not load.
**Why:** odezoo stores files exactly as published. With gotranx 2.11 and myokit 1.39 (checked on
2026-11-28; newer versions may fix these):
`tworld` is refused by myokit's CellML importer ("Each connection in a model must connect a unique
pair of components", PKA and contraction); `nygren_1998` converts but the `.ode` file fails to parse
(a variable named `dot`).
**Do instead:** before proposing a model for gotranx, look at its page on the documentation site,
which shows whether gotranx could load and simulate it; convert it early and offer an alternative if
it fails. Report conversion failures upstream (gotranx or myokit), not by editing the registry file.
<!-- verified: ran cellml2ode on both, 2026-11-28 -->

## Loading a converted model takes many minutes

**What happens:** `gotranx.load_ode` (and so `ode2py`) seems to hang on some converted CellML models.
**Why:** gotranx's singularity guards (on by default since 2.9) analyse every expression; for
`courtemanche_1998` this took more than 10 minutes here, against 0.5 s with
`remove_singularities=False`.
**Do instead:** tell the user it may take a while and offer to run it in the background; for a quick
look (number of states, names), load with `gotranx.load_ode(path, remove_singularities=False)`. Keep
the guards for the code that will be simulated unless the user decides otherwise.
<!-- verified: timed on 2026-11-28 with gotranx 2.11 -->

## Adding a model: the file changes on its way in

**What happens:** `odezoo registry check` reports a sha256 mismatch for a kept copy.
**Why:** an editor, formatter or git setting rewrote whitespace or line endings in `models/`.
**Do instead:** never edit files under `models/` or `LICENSES/` by hand; add an edited file as a new
version (`odezoo --registry . registry add version ...`). See [adding.md](adding.md).
<!-- verified: AGENTS.md, .gitattributes, pre-commit config -->
