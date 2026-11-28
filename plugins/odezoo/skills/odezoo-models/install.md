# Installing odezoo

odezoo needs Python 3.11 or later; its only dependency is rich.

```bash
python -m pip install odezoo
```

Check:

```bash
python -c "import odezoo; print(odezoo.__version__)"
odezoo values category
```

## Which registry you get

Each release carries the registry as it was when the release was made. The documentation site
(https://computationalphysiology.github.io/odezoo) follows the repository's `main` branch, so it can
list models that the installed release does not have. To get those:

- install from GitHub: `python -m pip install git+https://github.com/ComputationalPhysiology/odezoo`;
- or use a checkout of the repository for one command or call: `odezoo --registry <checkout> ...`,
  `odezoo.get(..., registry="<checkout>")`, or `ODEZOO_REGISTRY=<checkout>` in the environment.

`odezoo search <words> --ids` shows whether the installed registry has a model.

## What the next step needs

odezoo only fetches files. To use them:

| Next step | Needs |
|---|---|
| Load a `.ode` file or convert CellML to `.ode` | gotranx (`python -m pip install gotranx`), which brings myokit |
| Run the model in tissue | fenicsx-beat, sknm or simcardemsx, each with its own install |
| Add a model to the registry | a checkout with `python -m pip install -e ".[dev]"` ([adding.md](adding.md)) |

## Install gotchas

- An editable install from a checkout bundles the registry at install time. After changing
  `models/` in the checkout, pass `--registry .` or reinstall.
- Fetching needs network the first time a file is fetched on a machine (or with a new cache
  folder). See [fetching.md](fetching.md) for offline compute nodes.

Never install anything without asking the user first.
