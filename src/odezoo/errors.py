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

    Parameters
    ----------
    message : str
        What is wrong
    where : str, optional
        The file the error is in, such as `models/<id>/model.toml`
    field : str, optional
        The field the error is about, such as `versions[1].sha256`
    """

    def __init__(self, message: str, *, where: str | None = None, field: str | None = None):
        self.message = message
        self.where = where
        self.field = field
        super().__init__(": ".join(part for part in (where, field, message) if part))


class ModelNotFound(OdezooError):
    """No model in the registry has the id asked for

    Parameters
    ----------
    id : str
        The id that was asked for
    suggestions : Sequence[str], optional
        Ids of models with similar names, offered in the message as "did you mean …?"
    """

    def __init__(self, id: str, suggestions: Sequence[str] = ()):
        self.id = id
        self.suggestions = list(suggestions)
        text = f"no model {id!r} in the registry"
        if self.suggestions:
            text += f"; did you mean {', '.join(self.suggestions)}?"
        super().__init__(text)


class VersionNotFound(OdezooError):
    """A model has no version with the id or the format asked for"""


@dataclass(frozen=True)
class Attempt:
    """One place a file was looked for, and why it did not give the right bytes

    Attributes
    ----------
    source : str
        The path or URL that was tried
    reason : str
        Why it failed, such as `sha256 mismatch` or `HTTP 404`
    """

    source: str
    reason: str


class FetchError(OdezooError):
    """No place gave a version's file with the recorded sha256

    Parameters
    ----------
    model_id : str
        The model whose file was fetched
    version_id : str
        The version whose file was fetched
    attempts : Sequence[Attempt]
        Every place that was tried, in order, and why it failed
    """

    def __init__(self, model_id: str, version_id: str, attempts: Sequence[Attempt]):
        self.model_id = model_id
        self.version_id = version_id
        self.attempts = list(attempts)
        tried = "; ".join(f"{a.source}: {a.reason}" for a in self.attempts) or "no source to try"
        super().__init__(f"could not fetch {model_id} {version_id} ({tried})")


class OutputExistsError(OdezooError):
    """The file to write exists and holds different bytes

    Parameters
    ----------
    path : Path
        The file that would have been overwritten
    """

    def __init__(self, path: Path):
        self.path = path
        super().__init__(f"{path} exists with different content; pass --force to overwrite it")
