"""odezoo: a curated registry of ODE models, fetched and verified by sha256"""

from ._version import __version__
from .api import get, model, models, search
from .errors import (
    FetchError,
    ModelNotFound,
    OdezooError,
    OutputExistsError,
    RegistryError,
    VersionNotFound,
)
from .schema import Model, Paper, Source, Version

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
