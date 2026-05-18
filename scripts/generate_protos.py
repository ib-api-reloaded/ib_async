"""Generate Python protobuf bindings from IBKR's official .proto schemas.

The IBKR TWS API archive is fetched from ``interactivebrokers.github.io``
on first run (version + SHA256 pinned in ``pyproject.toml``
``[tool.ib_async.twsapi]``) and cached under
``~/.cache/ib_async/twsapi-{version}/``. Subsequent runs reuse the
cache. The same script powers local dev, CI, and the release
pipeline so all three fetch identical bytes — no drift between what
gets shipped and what the parity audit checks against.

Override the cached source by setting ``IB_PROTO_SOURCE`` to a
directory of ``.proto`` files — useful when iterating against a
local TWS install's bundled schemas.

Generated bindings live under ``ib_async/_pb/`` (gitignored, bundled
into the wheel via ``[tool.poetry.include]``). End users do not need
``protoc`` or ``grpcio-tools``.

Behaviour:
  1. Resolve the proto source dir (env override / cache / fetch).
  2. Wipe and recreate ``ib_async/_pb/`` so stale bindings cannot
     accidentally survive a schema removal.
  3. Invoke ``grpc_tools.protoc`` against every ``*.proto`` file.
  4. Rewrite cross-file imports into package-relative form so they
     resolve from inside ``ib_async._pb``.
  5. Emit an ``__init__.py`` and a ``py.typed`` marker.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _twsapi_meta import REPO_ROOT, TwsapiMeta  # noqa: E402
from _twsapi_meta import load as load_meta  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "ib_async" / "_pb"


def _ensure_source(meta: TwsapiMeta) -> Path:
    """Return a directory of ``.proto`` files to compile.

    Resolution order:
      1. ``IB_PROTO_SOURCE`` env var — escape hatch for dev against
         an unreleased local schema. No SHA check.
      2. ``meta.proto_dir`` if cache is valid for the pinned version.
      3. Download + SHA-verify + extract archive, then use cache.
    """
    override = os.environ.get("IB_PROTO_SOURCE")
    if override:
        path = Path(override).expanduser()
        if not path.is_dir() or not any(path.glob("*.proto")):
            sys.exit(
                f"IB_PROTO_SOURCE override invalid: {path}\n"
                f"  expected directory of .proto files"
            )
        print(f"using IB_PROTO_SOURCE override: {path}")
        return path

    if _cache_is_valid(meta):
        print(f"twsapi cache hit: {meta.cache_dir}")
        return meta.proto_dir

    _fetch_and_extract(meta)
    if not _cache_is_valid(meta):
        sys.exit(f"extraction did not produce expected layout under {meta.cache_dir}")
    return meta.proto_dir


def _cache_is_valid(meta: TwsapiMeta) -> bool:
    if not meta.proto_dir.is_dir() or not any(meta.proto_dir.glob("*.proto")):
        return False
    if not meta.version_file.is_file():
        return False
    # client_utils.py is the audit script's parity ground truth. A
    # cache missing it would pass the proto-only check yet break
    # ``make audit`` later — re-fetch instead.
    if not meta.client_utils_path.is_file():
        return False
    raw = meta.version_file.read_text().strip()
    return raw == f"API_Version={meta.dotted_version}"


_FETCH_TIMEOUT_SECONDS = 120


def _fetch_and_extract(meta: TwsapiMeta) -> None:
    meta.cache_dir.parent.mkdir(parents=True, exist_ok=True)
    print(f"downloading {meta.archive_url}")
    with urllib.request.urlopen(
        meta.archive_url, timeout=_FETCH_TIMEOUT_SECONDS
    ) as resp:
        data = resp.read()

    actual = hashlib.sha256(data).hexdigest()
    if actual != meta.archive_sha256:
        sys.exit(
            f"SHA256 mismatch for {meta.archive_url}\n"
            f"  expected: {meta.archive_sha256}\n"
            f"  actual:   {actual}\n"
            f"If IBKR republished the same version (rare), update\n"
            f"pyproject.toml [tool.ib_async.twsapi].archive_sha256\n"
            f"after manually verifying the new bytes."
        )

    print(f"verified SHA256, extracting into {meta.cache_dir}")
    if meta.cache_dir.exists():
        shutil.rmtree(meta.cache_dir)
    meta.cache_dir.mkdir(parents=True)

    # Extract only what we use: protos + version marker + the
    # reference client_utils.py the parity audit walks against.
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        keep = [
            m
            for m in zf.namelist()
            if m.startswith("IBJts/source/proto/")
            or m == "IBJts/source/pythonclient/ibapi/client_utils.py"
            or m == "IBJts/API_VersionNum.txt"
        ]
        zf.extractall(meta.cache_dir, keep)


def _reset_output() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)


def _run_protoc(source_dir: Path) -> None:
    from grpc_tools import protoc

    proto_files = sorted(str(p) for p in source_dir.glob("*.proto"))
    args = [
        "protoc",
        f"--proto_path={source_dir}",
        f"--python_out={OUTPUT_DIR}",
        f"--pyi_out={OUTPUT_DIR}",
        *proto_files,
    ]
    rc = protoc.main(args)
    if rc != 0:
        sys.exit(f"protoc failed with status {rc}")


# protoc emits ``import Foo_pb2 as ...`` for cross-file references.
# Those don't resolve once the modules live inside ``ib_async._pb``,
# so rewrite to ``from . import Foo_pb2 as ...``.
_IMPORT_RE = re.compile(r"^import (\w+_pb2)( as \w+)?$", re.MULTILINE)


def _rewrite_imports() -> None:
    for py in OUTPUT_DIR.glob("*_pb2.py"):
        text = py.read_text()
        new_text = _IMPORT_RE.sub(r"from . import \1\2", text)
        if new_text != text:
            py.write_text(new_text)
    for pyi in OUTPUT_DIR.glob("*_pb2.pyi"):
        text = pyi.read_text()
        new_text = _IMPORT_RE.sub(r"from . import \1\2", text)
        if new_text != text:
            pyi.write_text(new_text)


def _write_package_markers() -> None:
    (OUTPUT_DIR / "__init__.py").write_text(
        '"""Generated protobuf bindings — do not edit by hand."""\n'
    )
    (OUTPUT_DIR / "py.typed").write_text("")


def main() -> None:
    meta = load_meta()
    source = _ensure_source(meta)
    _reset_output()
    _run_protoc(source)
    _rewrite_imports()
    _write_package_markers()
    count = len(list(OUTPUT_DIR.glob("*_pb2.py")))
    rel = OUTPUT_DIR.relative_to(REPO_ROOT)
    print(f"generated {count} protobuf modules in {rel} (twsapi {meta.version})")


if __name__ == "__main__":
    main()
