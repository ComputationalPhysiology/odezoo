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
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
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
