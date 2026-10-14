"""Inspect and move the TWS API pin.

``status`` reports the pinned version, whether IBKR still serves its
archive, whether the local cache holds it, and which versions IBKR
currently publishes as Latest / Stable. ``--check`` turns an
unavailable pinned archive into a non-zero exit so a scheduled job
notices IBKR pruning it before a cold-cache build does.

``bump VERSION`` fetches that version's archive, refuses it unless it
carries everything the build and parity audit need, records its
SHA256 in ``pyproject.toml``, and primes the cache so the next
``make protos`` builds from it without fetching again.

Usage::

    uv run python scripts/twsapi.py status [--check]
    uv run python scripts/twsapi.py bump 1051.01 [--from PATH_OR_URL]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _twsapi_archive as archive
from _twsapi_meta import TwsapiMeta
from _twsapi_meta import load as load_meta
from _twsapi_meta import save as save_meta


def _availability(status: int | None) -> str:
    if status == 200:
        return "available"
    if status == 404:
        return "GONE (404 — IBKR pruned it)"
    if status is None:
        return "unreachable"
    return f"HTTP {status}"


def status(check: bool) -> int:
    meta = load_meta()
    pinned = archive.probe(meta.archive_url)

    print(f"pinned:   {meta.version}  sha256 {meta.archive_sha256[:16]}...")
    print(f"archive:  {meta.archive_url}")
    print(f"          {_availability(pinned)}")
    cached = meta.client_utils_path.is_file() and meta.proto_dir.is_dir()
    print(f"cache:    {meta.cache_dir} ({'present' if cached else 'absent'})")

    try:
        channels = archive.fetch_published_versions()
    except OSError as exc:
        print(f"IBKR:     installer page unreadable ({exc})")
        channels = {}

    for channel, version in sorted(channels.items()):
        url = TwsapiMeta(version=version, archive_sha256="").archive_url
        marker = "  <- pinned" if version == meta.version else ""
        print(
            f"IBKR:     {channel:<7} {version}  archive "
            f"{_availability(archive.probe(url))}{marker}"
        )

    if pinned != 200:
        print(
            f"\nThe pinned archive is not downloadable. Builds with a warm "
            f"cache still work; a cold one fails.\n"
            f"Re-pin with `make twsapi-bump V=<version>`, or set "
            f"{archive.ARCHIVE_ENV} to a copy of the pinned archive."
        )
        return 1 if check else 0

    return 0


def bump(version: str, source: str | None) -> int:
    probe_meta = TwsapiMeta(version=version, archive_sha256="")
    source = source or probe_meta.archive_url
    print(f"fetching {source}")
    try:
        data = archive.read(source)
    except archive.ArchiveUnavailable as exc:
        print(f"cannot bump to {version}: {exc}", file=sys.stderr)
        return 1

    problems = archive.layout_problems(data, probe_meta.dotted_version)
    if problems:
        print(f"refusing {version}: archive is not pinnable", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    meta = TwsapiMeta(version=version, archive_sha256=archive.sha256(data))
    archive.extract(data, meta.cache_dir)
    save_meta(meta)

    print(f"pinned {meta.version}  sha256 {meta.archive_sha256}")
    print(f"cache primed at {meta.cache_dir}")
    print("next: make protos && make audit && make test")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="report pin vs what IBKR serves")
    p_status.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when the pinned archive is no longer downloadable",
    )

    p_bump = sub.add_parser("bump", help="re-pin to VERSION (e.g. 1051.01)")
    p_bump.add_argument("version")
    p_bump.add_argument(
        "--from",
        dest="source",
        help="read the archive from this path or URL instead of IBKR",
    )

    args = parser.parse_args(argv)
    if args.command == "status":
        return status(args.check)
    return bump(args.version, args.source)


if __name__ == "__main__":
    sys.exit(main())
