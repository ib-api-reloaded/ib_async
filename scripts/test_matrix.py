#!/usr/bin/env python3
"""Run the test suite on several Python versions, each isolated and time-boxed.

Every version runs in its own uv environment (``.venvs/py<version>``), so
versions never share installed packages. Each run has a hard wall-clock
limit: on expiry the whole process tree is killed and the version is
reported as TIMEOUT instead of stalling the matrix. Full output goes to
``.venvs/logs/py<version>.log``; the console gets one summary line per
version and the exit status is non-zero if any version did not pass.

Usage::

    scripts/test_matrix.py [--versions 3.11 3.12 ...] [--timeout SECONDS]
                           -- <test command and arguments>

Example::

    scripts/test_matrix.py --timeout 300 -- pytest -q -W error::DeprecationWarning

Standard library only, so it runs before any environment exists.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

DEFAULT_VERSIONS = ("3.11", "3.12", "3.13", "3.14")
ROOT = Path(__file__).resolve().parent.parent
VENVS = ROOT / ".venvs"
LOGS = VENVS / "logs"


@dataclass(frozen=True, slots=True)
class Outcome:
    version: str
    status: str  # PASS, FAIL or TIMEOUT
    seconds: float
    summary: str
    log: Path


def _summary_line(output: str) -> str:
    """The test runner's own result line (pytest's ``N passed``, unittest's
    ``OK`` / ``FAILED``), or the last non-empty line."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith(("=", "OK", "FAILED")) or " passed" in line:
            return line.strip("= ")
    return lines[-1] if lines else "(no output)"


def run_version(
    version: str, command: list[str], timeout: float, extra_uv_args: list[str]
) -> Outcome:
    LOGS.mkdir(parents=True, exist_ok=True)
    log = LOGS / f"py{version}.log"
    env = dict(os.environ, UV_PROJECT_ENVIRONMENT=str(VENVS / f"py{version}"))
    argv = ["uv", "run", "--python", version, *extra_uv_args, *command]
    start = time.monotonic()
    with log.open("w") as out:
        out.write(f"$ {' '.join(argv)}\n\n")
        out.flush()
        # A new session makes the run its own process group, so a timeout
        # can stop uv, the interpreter and anything they started.
        proc = subprocess.Popen(
            argv,
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            code = None
    seconds = time.monotonic() - start
    if code is None:
        return Outcome(version, "TIMEOUT", seconds, f"killed after {timeout:.0f}s", log)
    summary = _summary_line(log.read_text())
    return Outcome(version, "PASS" if code == 0 else "FAIL", seconds, summary, log)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--versions", nargs="+", default=list(DEFAULT_VERSIONS))
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="wall-clock limit per version, in seconds (default 300)",
    )
    parser.add_argument(
        "--uv-arg",
        action="append",
        default=[],
        dest="uv_args",
        help="extra argument for `uv run` (repeatable), e.g. --uv-arg=--all-extras",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("give the test command after --")

    outcomes = []
    for version in args.versions:
        print(f"py{version}: running (limit {args.timeout:.0f}s) ...", flush=True)
        outcome = run_version(version, command, args.timeout, args.uv_args)
        outcomes.append(outcome)
        print(
            f"py{version}: {outcome.status:<7} {outcome.seconds:6.1f}s  "
            f"{outcome.summary}",
            flush=True,
        )

    failed = [o for o in outcomes if o.status != "PASS"]
    for outcome in failed:
        print(f"  see {outcome.log.relative_to(ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
