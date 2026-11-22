# Install and quick start

odezoo needs Python 3.11 or later, and its only dependency is
[rich](https://github.com/Textualize/rich).

```
python3 -m pip install odezoo
```

Each release bundles the registry as it was when the release was made. For models added since
the last release, install from GitHub:

```
python3 -m pip install git+https://github.com/ComputationalPhysiology/odezoo
```

## Quick start

```
odezoo list                                    # every model
odezoo values species                          # each species and its number of models
odezoo search --species human ten tusscher     # find models by text and filters
odezoo info beeler_reuter_1977                 # paper, DOI, versions, licences, sources
odezoo fetch beeler_reuter_1977 -o models/     # writes models/beeler_reuter_1977.cellml
```

From Python:

```python
import odezoo

path = odezoo.get("beeler_reuter_1977")  # the file, verified, in the cache
```
