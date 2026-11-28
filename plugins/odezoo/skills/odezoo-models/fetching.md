# Fetching a model and handing it on

## Command line

```bash
odezoo fetch tentusscher_2006_epi -o models/
odezoo fetch tentusscher_2006_epi --version pmr-5dc4239 -o models/
odezoo fetch tentusscher_2006_endo tentusscher_2006_epi tentusscher_2006_m -o models/
odezoo fetch land_2017 --format ode -o models/
```

Each file is written as `<id>.cellml` or `<id>.ode` in the `-o` folder (created if missing; the
current folder by default).

- Without options, `fetch` takes the model's default version, else its newest. `--version` names
  one, and works with one model id only (pin several models with one `fetch` each); `--format`
  takes the newest version in that format.
- An identical file already there is left alone; a different one is refused unless `--force`
  ([gotchas.md](gotchas.md)).
- Every file is checked against the registry's sha256. odezoo tries a registry checkout given with
  `--registry`, then the cache, then this repository's copy on GitHub (pinned to a commit), then the
  upstream source. If none gives the right bytes, the error lists each place and why.

## Python

```python
from pathlib import Path

import odezoo

path = odezoo.get("land_2017", version="github-6e5a5aa")  # the file in the cache
Path("models").mkdir(exist_ok=True)
path = odezoo.get("land_2017", version="github-6e5a5aa", dest="models")  # models/land_2017.ode
```

`get` returns the path. `dest` that is an existing folder gets `<id>.<ext>` in it; anything else is
taken as the file name. `cache=False` needs `dest`. `force=True` overwrites a different file.
Errors a user can cause are `odezoo.OdezooError` subclasses: `odezoo.ModelNotFound` (with
suggestions), `odezoo.VersionNotFound`, `odezoo.FetchError` (lists every place tried),
`odezoo.OutputExistsError`.

## Pinning

The version id (`pmr-5dc4239`, `github-6e5a5aa`, `v1`, ...) and the sha256 identify the file. A
registry update can add a version and change which one is fetched by default, so in a script that
will be rerun, always pass `version=` (or `--version`). Record id, version id and sha256 in the
study's notes:

```bash
odezoo info tentusscher_2006_epi --json
```

Versions are append-only: a version id, once released, always means the same bytes.

## The cache

Downloads are kept by sha256 in the cache folder (`odezoo cache dir` prints it; by default
`~/.cache/odezoo` on Linux, `~/Library/Caches/odezoo` on macOS, `%LOCALAPPDATA%\odezoo\Cache` on
Windows). Change it with `--cache-dir PATH` or `ODEZOO_CACHE_DIR`; a flag beats the
environment variable. `odezoo cache clear` empties it; `odezoo fetch --no-cache` neither reads nor
writes it.

## Offline compute nodes

A cached file is served without any network access. For a cluster whose compute nodes are offline:

```bash
# on a login node (online), into a folder the compute nodes can read
ODEZOO_CACHE_DIR=/shared/project/odezoo-cache odezoo fetch tentusscher_2006_epi --version pmr-5dc4239 -o models/
```

Then either use the file in `models/` directly (simplest), or call
`odezoo.get(..., cache_dir="/shared/project/odezoo-cache")` (or set `ODEZOO_CACHE_DIR`) in the job.
With a different or empty cache, the job fails with `odezoo.FetchError` listing the URLs it could
not reach.

## Handing the file to gotranx

A `.ode` version loads directly:

```python
import gotranx
import odezoo

ode = gotranx.load_ode(odezoo.get("land_2017", version="github-6e5a5aa"))
```

A CellML version is converted first (through myokit):

```bash
gotranx cellml2ode models/tentusscher_2006_epi.cellml -o models/tentusscher_2006_epi.ode
```

Then read the `.ode` file before generating code:

- **Time unit**: most CellML electrophysiology models are in ms; the contraction and circulation
  `.ode` files are in s (the header says so, e.g. Land: `# Units: s, uM, um, Pa`). Convert before
  coupling (the gotranx-odes skill's composition guide).
- **Membrane potential name**: `grep -n "_dt = " models/<id>.ode` lists the derivatives (`V`, `v`,
  `membrane_V`, ...). Downstream solvers ask for it.
- **The model's own stimulus**: `grep -in stim models/<id>.ode`. Amplitude, start, duration,
  period, and sometimes an end time (Courtemanche: `stim_end = 50000` ms, so pacing stops after
  50 s). For a tissue simulation where the solver stimulates, set the amplitude to zero.
- **Cell type**: the `celltype` or `epi` parameter, where the model has one
  ([choosing.md](choosing.md)).
- **Inputs of a contraction or circulation model**: its description and the comments at the top
  of the file say which parameters are the inputs and which component to remove to couple it
  (`land_2017`: `Ca`, `SL`, `dSL` in the `inputs` component; `regazzoni_2022`: `beat_phase` is
  computed in the `timing` component, and becomes a missing variable to supply once that component
  is removed).

Loading with gotranx's default singularity guards can take much longer than without for some models;
see [gotchas.md](gotchas.md).

## Handing the file to a tissue solver

None of them reads CellML: convert to `.ode` first. Then it depends on the solver and how it is
driven (use its skill, or its documentation):

- **fenicsx-beat, command line**: takes the `.ode` file itself (`cell.ode_file`) and generates the
  code. Set `cell.v_name` to the model's membrane potential if it is not `v` (Courtemanche and
  ten Tusscher use `V`), and set the model's own stimulus amplitude to zero in `cell.parameters`
  when beat stimulates. Per-region parameters (`cell.regions.<region>.parameters`) can set a
  cell-type parameter such as `celltype`, so one file covers endo, mid and epi.
- **fenicsx-beat, Python; sknm; simcardemsx**: take code generated by gotranx. Generate it once
  (gotranx-odes skill), keep the module next to the simulation script, and record the odezoo
  version it came from.

Read the time and current units against the solver's (beat works in ms; Courtemanche's currents are
in pA, not pA/pF).
