# Choosing a model

## Searching

Look at what there is before searching:

```bash
odezoo values species
odezoo values cell_type --species human
odezoo values category
```

Then filter. Repeating a filter gives alternatives; different filters must all hold. Text words must
all occur somewhere in the model's details (id, name, family, paper title and authors, keywords,
cell type, species).

```bash
odezoo search --species human --category electrophysiology --no-pager
odezoo search ten tusscher --ids
odezoo list --category myofilament_mechanics --json
```

| Filter | Keeps the models that |
|---|---|
| `--category C` | have category `C`, e.g. `electrophysiology`, `myofilament_mechanics`, `cardiovascular_circulation` |
| `--keyword K` | have keyword `K` |
| `--species S` | are of species `S` (`human`, `rabbit`, `guinea pig`, `canine`, `rat`, `mouse`, ...) |
| `--family F` | belong to family `F`: the cell-type variants of one model, e.g. `tentusscher_2006` |
| `--format F` | have a version in format `cellml` or `ode` |
| `--reviewed`, `--unreviewed` | have, or have not, been run and compared with their paper |

Always add `--no-pager`, `--ids` or `--json`: a long table on a terminal opens a pager.

From Python, the same filters are keyword arguments:

```python
import odezoo

for m in odezoo.search(species="human", category="electrophysiology"):
    print(m.id, m.cell_type, m.reviewed, [(v.id, v.format, v.license) for v in m.versions])
```

## Reading one model

```bash
odezoo info ohara_rudy_2011
```

shows the paper (DOI, PubMed), species, cell type, review status, the other models of its family,
and each version's format, date, licence and source. `odezoo info <id> --json` adds each version's
sha256 and the model's **description**, which the table does not show: read it, it says things such
as which parameter selects the cell type, or which inputs a contraction model expects. The number of
states is not in the registry; see the table below or load the file.

The documentation site has a page per model (https://computationalphysiology.github.io/odezoo,
search box or the model list) with a 3 s simulation run with gotranx, or the stage at which that
run failed. Check it before proposing a model the user will convert with gotranx: not every
registry file converts ([gotchas.md](gotchas.md)).

## What "reviewed" means

`reviewed = true` means someone has run the model and compared it with its paper. It does not mean
the model suits the user's purpose, and it says nothing about stability at large time steps. An
unreviewed model has not been checked; say so when proposing one.

## Cell types: separate ids or a parameter

- **Separate ids, one file each**: `tentusscher_2006_endo`, `tentusscher_2006_epi`,
  `tentusscher_2006_m` (likewise `tentusscher_2004_*` and `sakmann_2000_*`). `--family` lists them.
- **One file with a parameter**: `ohara_rudy_2011`, `torord_dyn_cl` and `tworld` have a
  `celltype` parameter (0 = endocardial, the default; 1 = epicardial; 2 = midmyocardial);
  `grandi_2010` has `epi` (1 = epicardial, the default). The id names the default cell type only.
  Set the parameter in the generated code (or in the `.ode` file) for the other types.

For a tissue with several cell types (transmural heterogeneity), this matters: a model with a
cell-type parameter needs one file, with the parameter set per region (fenicsx-beat's command line
does this with `cell.regions`). Separate files, as for ten Tusscher, differ in their equations, not
only in parameters, so they need one cell model per region, which in fenicsx-beat means its Python
API. Mention the midmyocardial variant when the user asks for endo and epi.

## Starting points (confirm with `odezoo info` and the user)

Numbers of states are those gotranx reports after conversion.

| Purpose | Candidates |
|---|---|
| Teaching, fast qualitative tissue runs | `fitzhugh_nagumo_1961` (2 states), `beeler_reuter_1977` (8, canine) |
| Human ventricle, tissue scale | `tentusscher_2006_*` (19 states, separate endo/mid/epi files) |
| Human ventricle, detailed | `ohara_rudy_2011` (41), `torord_dyn_cl` (45, ToR-ORd with dynamic chloride, GPL), `grandi_2010` (39), `tworld` (2025, GPL; check that it converts) |
| Human atrium | `courtemanche_1998` (21), `maleckar_2008` (30), `nygren_1998` (check that it converts) |
| Human Purkinje | `stewart_2009` (20) |
| Sinoatrial node (rabbit) | `zhang_2000`, `dokos_1996`, `demir_1999` |
| Animal ventricle | guinea pig `luo_rudy_1991`, `faber_rudy_2000`; canine `fox_2002`, `hund_rudy_2004`; rabbit `puglisi_bers_2001` (unreviewed); rat `pandit_2001`; mouse `bondarenko_2004`, `wang_sobie_2008` |
| Contraction (myofilament) | `land_2017` (human, 7 states, used with O'Hara-Rudy/ToR-ORd), `lewalle_2024`, `rice_2008` (rat), `tran_2010`, `tewari_2016`, `marzban_2020`, `rdq20_mf`, `musgrave_2025` (atrial) |
| Circulation | `regazzoni_2022` (closed loop, four chambers, 12 states) |

The contraction and circulation models are gotranx `.ode` files in seconds; most electrophysiology
models are CellML in milliseconds ([gotchas.md](gotchas.md)). The crossbridge-models skill (or
https://computationalphysiology.github.io/crossbridge) covers the contraction models in depth.

Not in the registry: say so, and offer the closest model that is, or a CellML file from the Physiome
Model Repository (https://models.physiomeproject.org), which gotranx converts in the same way.
