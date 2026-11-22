# The command line

`odezoo --help` lists the commands, and `odezoo COMMAND --help` describes one.

## Finding models

`odezoo list` shows every model as a table. `odezoo search` does the same for the models whose
details contain every word you give it, in any case: the id, name, family, paper title and
authors, keywords, cell type and species.

```
odezoo list
odezoo search ten tusscher
```

Both take the same filters. Repeating a filter gives alternatives; different filters must all
hold.

| Filter | Keeps the models that |
|---|---|
| `--category C` | have category `C` (one of PMR's 20 categories, such as `electrophysiology`) |
| `--keyword K` | have keyword `K` |
| `--species S` | are of species `S`, such as `human` or `guinea pig` |
| `--family F` | belong to family `F`, the cell-type variants of one model |
| `--format F` | have a version in format `cellml` or `ode` |
| `--reviewed`, `--unreviewed` | have, or have not, been run and compared with their paper |

```
odezoo list --species human --species rabbit --category electrophysiology
```

`--ids` prints only the ids, one per line, and `--json` prints the models as JSON. A table taller
than the terminal opens in your pager (`$PAGER`, else `less`), as git does; `--no-pager` prints it
instead.

## What is there

`odezoo values FIELD` counts the models with each value of a field, the most common first. The
field is `category`, `keyword`, `species`, `family`, `format` or `cell_type`, and the command
takes the filters above, so you can see what there is before you search.

```
odezoo values species
odezoo values family --species human
odezoo values cell_type --json
```

## One model

`odezoo info ID` shows a model's paper with its DOI and PubMed links, the other models in its
family, and a table of its versions: format, date added, licence, and where each comes from.
`--json` prints the model as JSON.

```
odezoo info tentusscher_2006_epi
```

## Fetching files

`odezoo fetch` writes each model's file, as `<id>.cellml` or `<id>.ode`, into the folder given
with `-o` (by default the current folder).

```
odezoo fetch beeler_reuter_1977 luo_rudy_1991 -o models/
odezoo fetch $(odezoo search --format cellml --ids) -o models/
```

Without options it fetches the model's default version, else its newest. `--version V` fetches a
given version (with one model id only), and `--format F` the newest version in a format.
`--force` overwrites a different file that is already there; an identical one is left alone.

Every file is checked against the sha256 in the registry. odezoo tries, in order: a registry
checkout given with `--registry`, the cache, this repository's copy on GitHub, and the upstream
source. The first that gives the right bytes wins; if none does, the error lists each place and
why it failed.

## The cache and other settings

| Option | Environment variable | What it does |
|---|---|---|
| `--cache-dir PATH` | `ODEZOO_CACHE_DIR` | Where downloads are kept |
| `--registry PATH` | `ODEZOO_REGISTRY` | Use a checkout of the repository instead of the bundled registry |

A flag beats its environment variable. `odezoo cache dir` prints the cache folder, `odezoo cache
clear` empties it, and `odezoo fetch --no-cache` neither reads nor writes it.

The commands under `odezoo registry` are for maintainers; [Adding a model](adding-a-model.md)
describes them.
