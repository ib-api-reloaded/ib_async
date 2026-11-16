"""Hatch build hook: generate ``ib_async/_pb/`` when a build has none.

The protobuf bindings are generated, not committed. Release builds run
``make protos`` first, so their sdist and wheel carry them. A build
straight from a git checkout (``pip install git+https://...``,
``uv add git+https://...``) has no ``_pb``, and without this hook the
package it installs fails on import with
``ModuleNotFoundError: ib_async._pb``.

When ``_pb`` is missing, the hook asks the build frontend for the
``protos`` dependency group (``grpcio-tools``) and runs
``scripts/generate_protos.py``, which fetches the pinned TWS API archive
and checks its SHA256, as ``make protos`` does. When ``_pb`` is present
(a release sdist, or a checkout after ``make protos``), the hook does
nothing and needs nothing. Editable installs (``uv sync``) are left
alone, so local development keeps running ``make protos`` itself.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class ProtosBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def _root(self) -> Path:
        return Path(self.root)

    def _needed(self) -> bool:
        return not (self._root() / "ib_async" / "_pb" / "__init__.py").exists()

    def dependencies(self) -> list[str]:
        # Asked before the build says whether it is editable, so an
        # editable build without _pb also gets grpcio-tools in its build
        # environment, though initialize() then generates nothing.
        if not self._needed():
            return []
        pyproject = tomllib.loads(
            (self._root() / "pyproject.toml").read_text(encoding="utf-8")
        )
        return list(pyproject["dependency-groups"]["protos"])

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if version == "editable" or not self._needed():
            return
        script = self._root() / "scripts" / "generate_protos.py"
        if not script.exists():
            raise RuntimeError(
                "ib_async/_pb/ is missing and scripts/generate_protos.py is "
                "not here to generate it; build from a git checkout or a "
                "release sdist"
            )
        subprocess.run([sys.executable, str(script)], check=True, cwd=self._root())
