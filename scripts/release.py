"""Release pipeline: fetch → generate → validate → build → smoke → publish.

One command takes a freshly-cloned repo to a publishable wheel +
sdist. Steps, in order:

  1. Fetch + extract the IBKR TWS API archive (version pinned in
     pyproject.toml [tool.ib_async.twsapi]) into
     ~/.cache/ib_async/twsapi-{version}/. Skipped on cache hit.
  2. Generate protobuf bindings into ib_async/_pb/.
  3. Run static checks (ruff + mypy).
  4. Run the proto-parity audit against the version-locked
     client_utils.py from the same archive.
  5. Run the owned test suite (no live wire — no TWS/gateway).
  6. Build wheel + sdist via uv build.
  7. Smoke-install the wheel into a clean venv and import it.
  8. Print READY. Publishing is gated behind ``--publish`` so the
     operator decides when to upload.

Any red step aborts the pipeline before publish can happen.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from _twsapi_meta import REPO_ROOT  # noqa: E402
from _twsapi_meta import load as load_meta  # noqa: E402

DIST_DIR = REPO_ROOT / "dist"


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    print(f"\n--- {' '.join(cmd)}")
    rc = subprocess.call(cmd, cwd=cwd or REPO_ROOT)
    if rc != 0:
        sys.exit(f"step failed (rc={rc}): {' '.join(cmd)}")


def _fetch_and_generate() -> None:
    _run([sys.executable, str(SCRIPTS_DIR / "generate_protos.py")])


def _lint() -> None:
    _run(["uv", "run", "python", "-m", "ruff", "check", "ib_async/", "tests/"])
    _run(["uv", "run", "python", "-m", "mypy", "ib_async/"])


def _audit_parity() -> None:
    _run([sys.executable, str(SCRIPTS_DIR / "audit_proto_parity.py")])


def _test() -> None:
    _run(["uv", "run", "pytest", "-q"])


def _build() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    _run(["uv", "build"])


def _smoke_install_wheel() -> None:
    wheels = sorted(DIST_DIR.glob("*.whl"))
    if not wheels:
        sys.exit("no wheel produced by uv build")
    wheel = wheels[-1]
    with tempfile.TemporaryDirectory() as td:
        env_dir = Path(td) / "venv"
        venv.create(env_dir, with_pip=True)
        bin_dir = env_dir / ("Scripts" if sys.platform == "win32" else "bin")
        pip = bin_dir / "pip"
        py = bin_dir / "python"
        _run([str(pip), "install", "--upgrade", "pip"])
        _run([str(pip), "install", str(wheel)])
        _run([str(py), "-c", "import ib_async; ib_async.IB(); print('smoke ok')"])


def _publish() -> None:
    _run(["uv", "publish"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Run ``uv publish`` after all checks pass. Default: stop at READY.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip pytest. Use only when iterating on packaging itself.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip the clean-venv wheel install smoke test.",
    )
    args = parser.parse_args()

    meta = load_meta()
    print("=== ib_async release pipeline ===")
    print(f"TWS API: version={meta.version} sha256={meta.archive_sha256[:16]}...")
    print(f"cache:   {meta.cache_dir}")

    _fetch_and_generate()
    _lint()
    _audit_parity()
    if not args.skip_tests:
        _test()
    _build()
    if not args.skip_smoke:
        _smoke_install_wheel()

    print("\n=== READY ===")
    print(f"  artifacts: {DIST_DIR}")
    if args.publish:
        _publish()
    else:
        print("  to publish: scripts/release.py --publish  (or: uv publish)")


if __name__ == "__main__":
    main()
