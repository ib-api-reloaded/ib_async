"""TWS API version pin — single source of truth in pyproject.toml.

Reads ``[tool.ib_async.twsapi]`` so ``scripts/generate_protos.py``,
``scripts/release.py``, ``scripts/audit_proto_parity.py``, and CI
all consume one version + SHA256 pin. No duplication, no drift.

The IBKR TWS API archive ships BOTH:
  * ``IBJts/source/proto/*.proto`` — schemas we compile
  * ``IBJts/source/pythonclient/ibapi/client_utils.py`` — reference
    encoder the parity audit walks against

A single version pin keeps generated bindings and parity ground
truth locked together.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"


@dataclass(frozen=True, slots=True)
class TwsapiMeta:
    version: str
    archive_sha256: str

    @property
    def archive_url(self) -> str:
        return (
            "https://interactivebrokers.github.io/downloads/"
            f"twsapi_macunix.{self.version}.zip"
        )

    @property
    def cache_dir(self) -> Path:
        return Path.home() / ".cache" / "ib_async" / f"twsapi-{self.version}"

    @property
    def proto_dir(self) -> Path:
        return self.cache_dir / "IBJts" / "source" / "proto"

    @property
    def client_utils_path(self) -> Path:
        return (
            self.cache_dir
            / "IBJts"
            / "source"
            / "pythonclient"
            / "ibapi"
            / "client_utils.py"
        )

    @property
    def version_file(self) -> Path:
        return self.cache_dir / "IBJts" / "API_VersionNum.txt"

    @property
    def dotted_version(self) -> str:
        # "1046.01" → "10.46.01" (the form inside API_VersionNum.txt).
        # IBKR's URL convention drops exactly that one dot.
        if "." not in self.version:
            return self.version
        head, tail = self.version.split(".", 1)
        if len(head) >= 4:
            return f"{head[:-2]}.{head[-2:]}.{tail}"
        return self.version


def load() -> TwsapiMeta:
    with PYPROJECT.open("rb") as f:
        cfg = tomllib.load(f)
    t = cfg["tool"]["ib_async"]["twsapi"]
    return TwsapiMeta(version=t["version"], archive_sha256=t["archive_sha256"])


_SECTION = "[tool.ib_async.twsapi]"


def save(meta: TwsapiMeta, pyproject: Path | None = None) -> None:
    """Rewrite the pin in place, leaving every other byte of the file alone.

    Only the ``version`` and ``archive_sha256`` keys inside
    ``[tool.ib_async.twsapi]`` change, so the section's comments and the
    rest of ``pyproject.toml`` survive a bump untouched.
    """
    pyproject = pyproject or PYPROJECT
    text = pyproject.read_text()
    start = text.index(_SECTION)
    end = text.find("\n[", start + len(_SECTION))
    end = len(text) if end == -1 else end

    section = text[start:end]
    for key, value in (
        ("version", meta.version),
        ("archive_sha256", meta.archive_sha256),
    ):
        section, count = re.subn(
            rf'^{key} = "[^"]*"$', f'{key} = "{value}"', section, flags=re.MULTILINE
        )
        if count != 1:
            raise ValueError(f"expected one {key!r} key in {_SECTION}, found {count}")

    pyproject.write_text(text[:start] + section + text[end:])
