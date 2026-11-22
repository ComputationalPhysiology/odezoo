# odezoo

odezoo is a curated registry of ODE model files, mostly cell models but also others such as
Windkessel models, stored as markup: [CellML](https://www.cellml.org) or
[gotranx](https://github.com/finsberg/gotranx) `.ode`. It is a Python package with a command line
that searches the registry and downloads a model's file exactly as it was recorded.

Every file is identified by its sha256. Whether it comes from your cache, from this repository's
copy on GitHub, or from where its authors keep it (the Physiome Model Repository, GitHub or
Zenodo), odezoo checks the hash before handing it over, so a given release of odezoo always gives
the same bytes for a model, also after the original source has gone.

Each model has one `model.toml` that says which paper it belongs to, how to find it (categories,
keywords, species, cell type), and where each version of its file comes from, with that file's
licence.

- [Install and quick start](install.md)
- [Search the models](search.md) in your browser, or browse them in the sidebar
- [The command line](cli.md)
- [From Python](python.md)
- [Adding a model](adding-a-model.md)
