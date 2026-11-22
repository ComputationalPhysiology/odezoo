# From Python

`import odezoo` gives the same registry as the command line, without rich or any other
dependency being imported.

```python
import odezoo

odezoo.models()  # every model, sorted by id
odezoo.search("ten tusscher", species="human", format="cellml")
odezoo.values("species")  # {"human": 14, "guinea pig": 8, ...}
model = odezoo.model("beeler_reuter_1977")  # paper, keywords, versions, ...
model.paper.doi  # "10.1113/jphysiol.1977.sp011853"
```

`search` takes the filters of the command line as keyword arguments, each a value or a list of
alternatives: `category`, `keyword`, `species`, `family`, `format` and `reviewed`. `values` takes
a field name and the same filters.

`get` fetches a file, verified by its sha256, and returns its path:

```python
path = odezoo.get("beeler_reuter_1977")  # the file in the cache
path = odezoo.get("beeler_reuter_1977", dest=".")  # copied to ./beeler_reuter_1977.cellml
path = odezoo.get("beeler_reuter_1977", version="pmr-cb090c9")
```

A model's `.ode` version, where it has one, loads directly in gotranx:

```python
import gotranx

ode = gotranx.load_ode(odezoo.get(model_id, format="ode"))
```

Every function takes `registry=` to use a checkout of the repository instead of the bundled
registry. Errors a user can cause are subclasses of `odezoo.OdezooError`, whose messages say what
to do: `ModelNotFound` (with suggestions), `VersionNotFound`, `FetchError` (listing every place
tried) and `OutputExistsError`.

The reference below is written from the source.
