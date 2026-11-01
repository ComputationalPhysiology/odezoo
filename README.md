# odezoo

odezoo is a curated registry of ODE model files, mostly cell models but also others such as
Windkessel models, stored as markup: CellML or [gotranx](https://github.com/finsberg/gotranx)
`.ode`. It is a Python package with a command line interface that searches the registry and
downloads a model's file exactly as it was recorded, verified by its sha256. The registry holds
only the models chosen for it, and each model has one `model.toml` that says where its files come
from, which paper it belongs to, and how to find it.
