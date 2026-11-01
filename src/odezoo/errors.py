"""The errors odezoo raises on purpose; the command line prints them without a traceback"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


class OdezooError(Exception):
    """Base class of every error odezoo raises on purpose"""


class RegistryError(OdezooError):
    """A registry entry, or the registry itself, is not valid

    The message names the file (`where`) and the field it is about, when they are known.
    """

    def __init__(self, message: str, *, where: str | None = None, field: str | None = None):
        self.message = message
        self.where = where
        self.field = field
        super().__init__(": ".join(part for part in (where, field, message) if part))


class ModelNotFound(OdezooError):
    def __init__(self, id: str, suggestions: Sequence[str] = ()):
        self.id = id
        self.suggestions = list(suggestions)
        text = f"no model {id!r} in the registry"
        if self.suggestions:
            text += f"; did you mean {', '.join(self.suggestions)}?"
        super().__init__(text)


class VersionNotFound(OdezooError):
    pass


@dataclass(frozen=True)
class Attempt:
    """One place a file was looked for, and why it did not give the right bytes"""

    source: str
    reason: str


class FetchError(OdezooError):
    def __init__(self, model_id: str, version_id: str, attempts: Sequence[Attempt]):
        self.model_id = model_id
        self.version_id = version_id
        self.attempts = list(attempts)
        tried = "; ".join(f"{a.source}: {a.reason}" for a in self.attempts) or "no source to try"
        super().__init__(f"could not fetch {model_id} {version_id} ({tried})")


class OutputExistsError(OdezooError):
    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"{path} exists with different content; pass --force to overwrite it")
