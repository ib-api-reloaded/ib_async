"""What the generators share: formatting generated code as the project's
formatter keeps it, and writing the generated files or checking they are
current.

A generator builds each output file's text from its catalog and calls
:func:`main` with them; ``--check`` writes nothing and exits 1 when a file
is out of date (``make ruff`` runs every generator so).
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def formatted(source: str, path: Path) -> str:
    """``source`` as ``ruff format`` writes it for ``path``, so a
    generated module is exactly what the project's formatter keeps."""
    result = subprocess.run(
        ["ruff", "format", "--stdin-filename", str(path), "-"],
        input=source,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise SystemExit(f"ruff cannot format the generated {path}:\n{result.stderr}")
    return result.stdout


def main(
    description: str,
    script: str,
    outputs: Callable[[], Mapping[Path, str]],
    argv: list[str] | None = None,
) -> int:
    """Write each output that changed, or with ``--check`` list those out of
    date and exit 1."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if a file is out of date"
    )
    args = parser.parse_args(argv)
    stale = []
    for path, text in outputs().items():
        current = path.read_text() if path.exists() else None
        if current == text:
            continue
        stale.append(path.relative_to(ROOT))
        if not args.check:
            path.write_text(text)
    if args.check and stale:
        print("out of date: " + ", ".join(map(str, stale)))
        print(f"run: uv run python scripts/{script}")
        return 1
    for path in stale:
        print(f"wrote {path}")
    return 0
