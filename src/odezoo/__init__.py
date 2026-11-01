"""odezoo: a curated registry of ODE models, fetched and verified by sha256"""

from importlib.metadata import PackageNotFoundError, version

__version__: str
try:
    __version__ = version("odezoo")
except PackageNotFoundError:  # running from a source tree that is not installed (the build hook)
    __version__ = "0+unknown"

# Imported after __version__, which odezoo.http reads.
from .api import get, model, models, search  # noqa: E402
from .errors import (  # noqa: E402
    FetchError,
    ModelNotFound,
    OdezooError,
    OutputExistsError,
    RegistryError,
    VersionNotFound,
)
from .schema import Model, Paper, Source, Version  # noqa: E402

__all__ = [
    "FetchError",
    "Model",
    "ModelNotFound",
    "OdezooError",
    "OutputExistsError",
    "Paper",
    "RegistryError",
    "Source",
    "Version",
    "VersionNotFound",
    "__version__",
    "get",
    "model",
    "models",
    "search",
]
