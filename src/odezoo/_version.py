"""The installed version of odezoo"""

from importlib.metadata import PackageNotFoundError, version

__version__: str
try:
    __version__ = version("odezoo")
except PackageNotFoundError:  # running from a source tree that is not installed (the build hook)
    __version__ = "0+unknown"
