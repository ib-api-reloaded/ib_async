"""Generate Python protobuf bindings from IBKR's official .proto schemas.

Reads .proto files from the IBKR reference repo (configurable via the
IB_PROTO_SOURCE environment variable, defaulting to
``<IBKR-TWSAPI>/IBJts/source/proto``) and writes generated
``*_pb2.py`` / ``*_pb2.pyi`` modules into ``ib_async/_pb/``, which is
gitignored.

Run via ``make protos`` or ``uv run python scripts/generate_protos.py``.

The generated bindings are deterministic outputs of ``protoc`` and are
not committed to the repository — every build environment regenerates
them from the schemas that match the TWS API version we target.

Behaviour:
  1. Wipe and recreate ``ib_async/_pb/`` so stale bindings cannot
     accidentally survive a schema removal.
  2. Invoke ``grpc_tools.protoc`` against every ``*.proto`` file under
     the source directory.
  3. Post-process the generated modules to rewrite cross-file imports
     into package-relative form (``from .Foo_pb2 import …``) so they
     resolve from inside ``ib_async._pb``.
  4. Emit an ``__init__.py`` and a ``py.typed`` marker so consumers and
     type-checkers can import from ``ib_async._pb`` cleanly.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path("<IBKR-TWSAPI>/IBJts/source/proto").expanduser()
SOURCE_DIR = Path(os.environ.get("IB_PROTO_SOURCE", str(DEFAULT_SOURCE)))
OUTPUT_DIR = REPO_ROOT / "ib_async" / "_pb"


def _check_source() -> None:
    if not SOURCE_DIR.is_dir():
        sys.exit(
            f"protoc source directory not found: {SOURCE_DIR}\n"
            f"Set IB_PROTO_SOURCE to the path of IBJts/source/proto."
        )
    if not any(SOURCE_DIR.glob("*.proto")):
        sys.exit(f"no .proto files found under {SOURCE_DIR}")


def _reset_output() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)


def _run_protoc() -> None:
    # Imported lazily so a missing grpc_tools install fails with a useful
    # message rather than a top-level ImportError.
    from grpc_tools import protoc

    proto_files = sorted(str(p) for p in SOURCE_DIR.glob("*.proto"))
    args = [
        "protoc",
        f"--proto_path={SOURCE_DIR}",
        f"--python_out={OUTPUT_DIR}",
        f"--pyi_out={OUTPUT_DIR}",
        *proto_files,
    ]
    rc = protoc.main(args)
    if rc != 0:
        sys.exit(f"protoc failed with status {rc}")


# protoc emits ``import Foo_pb2 as ...`` for cross-file references. Those
# don't resolve once the modules live inside the ``ib_async._pb`` package,
# so rewrite to ``from . import Foo_pb2 as ...``. This mirrors the helper
# the gnzsnz/protobuf PR ships as ``scripts/fix_proto_imports.py``.
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
    _check_source()
    _reset_output()
    _run_protoc()
    _rewrite_imports()
    _write_package_markers()
    count = len(list(OUTPUT_DIR.glob("*_pb2.py")))
    print(f"generated {count} protobuf modules in {OUTPUT_DIR.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
