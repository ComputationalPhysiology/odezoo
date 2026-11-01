"""Bundle the registry into the package: write src/odezoo/registry.json when building

The wheel carries the registry as one JSON document, stamped with the commit it was built from
so that mirror URLs can be pinned to it. The model files themselves are not in the wheel.
"""

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    """Hatchling build hook that bundles the registry into the package"""

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        """Write `src/odezoo/registry.json` from the checkout's `models/` before a build

        A build without `models/`, such as a wheel built from an sdist, uses the
        `registry.json` the sdist carries.

        Parameters
        ----------
        version : str
            The version of the build target, such as `standard` or `editable`
        build_data : dict[str, Any]
            The build data hatchling passes; left as it is

        Raises
        ------
        RuntimeError
            If there is neither a `models/` folder nor a `registry.json` to bundle
        """
        root = Path(self.root)
        target = root / "src" / "odezoo" / "registry.json"
        if (root / "models").is_dir():
            sys.path.insert(0, str(root / "src"))
            try:
                from odezoo.registry import build, resolve_commit
            finally:
                sys.path.pop(0)
            commit = os.environ.get("ODEZOO_REGISTRY_COMMIT") or resolve_commit(root)
            data = build(root, commit=commit, built=date.today())
            text = json.dumps(data, indent=1, ensure_ascii=False) + "\n"
            target.write_text(text, encoding="utf-8")
        elif not target.is_file():
            # A wheel built from an sdist: the sdist has no models/ but carries registry.json.
            raise RuntimeError("no models/ folder, and no src/odezoo/registry.json to bundle")
