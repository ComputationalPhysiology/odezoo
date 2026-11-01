"""odezoo: a curated registry of ODE models, fetched and verified by sha256"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("odezoo")
except PackageNotFoundError:  # running from a source tree that is not installed (the build hook)
    __version__ = "0+unknown"
