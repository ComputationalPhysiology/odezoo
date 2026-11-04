"""`odezoo registry check`: everything `parse_model` cannot see, because it needs the files

Each model is checked on its own, so one broken model does not hide problems in the others.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from xml.etree import ElementTree

from ..errors import RegistryError
from ..fetch import sha256_hex
from ..registry import read_model
from ..schema import Model

CELLML_NAMESPACES = (
    "http://www.cellml.org/cellml/1.0#",
    "http://www.cellml.org/cellml/1.1#",
    "http://www.cellml.org/cellml/2.0#",
)
CELLML_IMPORTS = {f"{{{ns}}}import" for ns in CELLML_NAMESPACES}
# Licences whose one condition is that the copyright notice goes with every copy. The generic
# text in LICENSES/ has no notice, so a model keeping such a copy has upstream's licence file,
# with its copyright line, as models/<id>/LICENSE.
NOTICE_LICENSES = frozenset({"MIT", "BSD-2-Clause", "BSD-3-Clause"})
LICENSE_FILE = "LICENSE"


@dataclass
class Report:
    """What `odezoo registry check` found

    Attributes
    ----------
    errors : list[str]
        Problems that make the registry wrong, each starting with the file it is in
    warnings : list[str]
        Things worth a look that do not make it wrong
    checked : int
        The number of models checked
    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0

    @property
    def ok(self) -> bool:
        """Whether the check found no errors; warnings are allowed"""
        return not self.errors


def cellml_problem(data: bytes) -> str | None:
    """Find why `data` is not a self-contained CellML model

    Parameters
    ----------
    data : bytes
        A file's bytes

    Returns
    -------
    str | None
        The problem (not well-formed XML, no CellML model at the root, or an `<import>`), or
        None if there is none
    """
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        return f"not well-formed XML ({e})"
    namespace = root.tag[1:].partition("}")[0] if root.tag.startswith("{") else ""
    if namespace not in CELLML_NAMESPACES or root.tag != f"{{{namespace}}}model":
        return f"the root element is {root.tag}, not a model in a CellML namespace"
    if any(element.tag in CELLML_IMPORTS for element in root.iter()):
        return "uses <import>; files here must be self-contained, so flatten it first"
    return None


class _Checker:
    """Check models one by one, collecting what is wrong in `report`

    Parameters
    ----------
    root : Path
        The registry checkout
    """

    def __init__(self, root: Path):
        self.root = root
        self.report = Report()
        self._gotranx: ModuleType | None = None
        self._gotranx_tried = False

    def gotranx(self) -> ModuleType | None:
        """Import gotranx when the first .ode file is seen, warning once if it is not installed

        Returns
        -------
        ModuleType | None
            gotranx, or None if it is not installed
        """
        if not self._gotranx_tried:
            self._gotranx_tried = True
            try:
                import gotranx

                self._gotranx = gotranx
            except ImportError:
                self.report.warnings.append("gotranx not installed, so .ode files were not loaded")
        return self._gotranx

    def model(self, folder: Path) -> None:
        """Check one model's folder: its `model.toml`, then its files

        Parameters
        ----------
        folder : Path
            The model's folder, `models/<id>`
        """
        self.report.checked += 1
        if not (folder / "model.toml").is_file():
            self.report.errors.append(f"models/{folder.name}: has no model.toml")
            return
        try:
            model = read_model(folder)
        except RegistryError as e:
            self.report.errors.append(str(e))
            return
        self.files(folder, model)

    def files(self, folder: Path, model: Model) -> None:
        """Check the files of a model whose `model.toml` is valid

        Each copy must be there, have the recorded sha256, have its licence text in `LICENSES/`,
        and load: CellML as a self-contained model, `.ode` with gotranx if it is installed. A
        copy under a licence in `NOTICE_LICENSES` also needs the model's `LICENSE` file. A file
        no version refers to, other than `LICENSE`, is an error; a version whose licence is not
        its parent's is a warning.

        Parameters
        ----------
        folder : Path
            The model's folder, `models/<id>`
        model : Model
            The model read from it
        """
        errors, warnings = self.report.errors, self.report.warnings
        prefix = f"models/{folder.name}"
        versions = {v.id: v for v in model.versions}
        for v in model.versions:
            parent = versions.get(v.derived_from) if v.derived_from else None
            if parent is not None and parent.license != v.license:
                warnings.append(
                    f"{prefix}/model.toml: version {v.id} is {v.license} but derives from "
                    f"{parent.id}, which is {parent.license}"
                )
            if v.file is None:
                continue
            label, path = f"{prefix}/{v.file}", folder / v.file
            if not path.is_file():
                errors.append(f"{label}: missing")
                continue
            data = path.read_bytes()
            if sha256_hex(data) != v.sha256:
                errors.append(f"{label}: sha256 is {sha256_hex(data)}, model.toml says {v.sha256}")
            if not (self.root / "LICENSES" / f"{v.license}.txt").is_file():
                errors.append(f"{label}: LICENSES/{v.license}.txt is missing; copies need it")
            if v.format == "cellml":
                problem = cellml_problem(data)
                if problem:
                    errors.append(f"{label}: {problem}")
            elif v.format == "ode" and (gotranx := self.gotranx()) is not None:
                try:
                    gotranx.load_ode(path)
                except Exception as e:  # any failure to load is the finding
                    errors.append(f"{label}: gotranx cannot load it ({type(e).__name__}: {e})")
        notices = sorted(
            {v.license for v in model.versions if v.file and v.license in NOTICE_LICENSES}
        )
        if notices and not (folder / LICENSE_FILE).is_file():
            errors.append(
                f"{prefix}/{LICENSE_FILE}: missing; a copy under {', '.join(notices)} must carry "
                "its copyright notice, so put upstream's licence file here"
            )
        referenced = {"model.toml", LICENSE_FILE, *(v.file for v in model.versions if v.file)}
        for path in sorted(folder.iterdir()):
            if path.name not in referenced and not path.name.startswith("."):
                errors.append(f"{prefix}/{path.name}: not referenced by any version")


def check(root: Path, ids: Sequence[str] | None = None) -> Report:
    """Check the models in the checkout at `root` (all of them, or the ones named in `ids`)

    Parameters
    ----------
    root : Path
        The registry checkout
    ids : Sequence[str], optional
        The models to check, by default all of them; an id with no folder is an error

    Returns
    -------
    Report
        The errors and warnings found, and the number of models checked

    Raises
    ------
    RegistryError
        If `root` has no `models/` folder
    """
    root = Path(root)
    if not (root / "models").is_dir():
        raise RegistryError(f"{root} has no models/ folder, so it is not a registry checkout")
    checker = _Checker(root)
    folders = sorted(p for p in (root / "models").iterdir() if p.is_dir())
    if ids:
        names = {f.name for f in folders}
        for id in ids:
            if id not in names:
                checker.report.errors.append(f"models/{id}: no such model")
        folders = [f for f in folders if f.name in ids]
    for folder in folders:
        checker.model(folder)
    return checker.report
