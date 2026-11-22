"""What the source distribution contains: the package, its tests and licences, nothing local"""

import shutil
import subprocess
import sys
import tarfile

from helpers import REPO

IGNORED = (".venv", ".git", ".superpowers", "__pycache__", "*.egg-info", "*_cache", "registry.json")


def test_sdist_holds_only_the_package_files(tmp_path):
    copy = tmp_path / "odezoo"
    shutil.copytree(REPO, copy, ignore=shutil.ignore_patterns(*IGNORED))
    # Local-only planning files, as a maintainer's checkout has them.
    (copy / ".superpowers/sdd/plan").mkdir(parents=True)
    (copy / ".superpowers/sdd/plan/progress.md").write_text("private")
    (copy / "docs/superpowers/specs").mkdir(parents=True, exist_ok=True)
    (copy / "docs/superpowers/specs/design.md").write_text("private")
    dist = tmp_path / "dist"
    subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-t", "sdist", "-d", str(dist)],
        cwd=copy,
        check=True,
        capture_output=True,
    )
    with tarfile.open(next(dist.glob("odezoo-*.tar.gz"))) as sdist:
        names = [name.split("/", 1)[1] for name in sdist.getnames() if "/" in name]
    assert not [n for n in names if n.startswith((".superpowers", "docs", "models", ".github"))]
    assert "src/odezoo/registry.json" in names and "LICENSES/CC-BY-3.0.txt" in names


def test_citation_has_the_package_version():
    # Zenodo takes a release's metadata from CITATION.cff, so it must not lag behind.
    import re
    import tomllib

    version = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    cited = re.search(
        r"^version: (\S+)$", (REPO / "CITATION.cff").read_text(encoding="utf-8"), re.M
    )
    assert cited is not None and cited.group(1) == version["version"]
