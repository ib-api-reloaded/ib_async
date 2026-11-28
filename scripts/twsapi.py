"""Inspect and move the TWS API pin.

``status`` reports the pinned version, whether IBKR still serves its
archive, whether the local cache holds it, and which versions IBKR
currently publishes as Latest / Stable. ``--check`` turns an
unavailable pinned archive into a non-zero exit so a scheduled job
notices IBKR pruning it before a cold-cache build does.

``bump VERSION`` fetches that version's archive, refuses it unless it
carries the ``.proto`` schemas and version marker the build needs, records its
SHA256 in ``pyproject.toml``, and primes the cache so the next
``make protos`` builds from it without fetching again. The archive is
IBKR's per-version zip (up to 10.51) or its Linux installer (from
10.53, when IBKR stopped publishing the zip). Bumping from an installer
URL pins that URL; ``--url`` names it when the installer was read from
a local copy.

``unpack SOURCE DEST`` writes every file of an archive or installer to
DEST, the TWS API as IBKR installs it, for reading IBKR's client sources.

Usage::

    uv run python scripts/twsapi.py status [--check]
    uv run python scripts/twsapi.py bump 1053.01 [--from PATH_OR_URL] [--url URL]
    uv run python scripts/twsapi.py unpack PATH_OR_URL DEST
"""

from __future__ import annotations

import argparse
import io
import sys
import zipfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _twsapi_archive as archive
import _twsapi_installer as installer
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
    cached = meta.version_file.is_file() and meta.proto_dir.is_dir()
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
            f"IBKR:     {channel:<7} {version}  zip "
            f"{_availability(archive.probe(url))}{marker}"
        )
        print(f"          installer {installer.installer_url(channel)}")

    if pinned != 200:
        print(
            f"\nThe pinned archive is not downloadable. Builds with a warm "
            f"cache still work; a cold one fails.\n"
            f"Re-pin with `make twsapi-bump V=<version> FROM=<zip or "
            f"installer URL>`, or set {archive.ARCHIVE_ENV} to a copy of the "
            f"pinned archive."
        )
        return 1 if check else 0

    return 0


def bump(version: str, source: str | None, url: str | None) -> int:
    probe_meta = TwsapiMeta(version=version, archive_sha256="")
    source = source or probe_meta.archive_url
    if url is None and source.startswith(("http://", "https://")):
        url = source
    # The per-version zip URL is the default; the pin records any other.
    url = "" if url in {None, probe_meta.archive_url} else url
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

    meta = TwsapiMeta(version=version, archive_sha256=archive.sha256(data), url=url)
    archive.extract(data, meta.cache_dir)
    save_meta(meta)

    print(f"pinned {meta.version}  sha256 {meta.archive_sha256}")
    print(f"from   {meta.archive_url}")
    print(f"cache primed at {meta.cache_dir}")
    print("next: make protos && make test")
    return 0


def unpack(source: str, dest: Path) -> int:
    if dest.exists() and any(dest.iterdir()):
        print(f"refusing to unpack into {dest}: it is not empty", file=sys.stderr)
        return 1
    print(f"reading {source}")
    try:
        data = archive.read(source)
        if installer.is_installer(data):
            installed = installer.files(data)
        else:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                installed = {
                    name.removeprefix("IBJts/"): zf.read(name)
                    for name in zf.namelist()
                    if not name.endswith("/")
                }
    except (archive.ArchiveUnavailable, installer.UnreadableInstaller) as exc:
        print(f"cannot unpack {source}: {exc}", file=sys.stderr)
        return 1
    except zipfile.BadZipFile:
        print(f"cannot unpack {source}: not a zip or installer", file=sys.stderr)
        return 1

    for path, content in installed.items():
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    version = installed.get("API_VersionNum.txt", b"no API_VersionNum.txt").decode()
    print(f"unpacked {len(installed)} files into {dest} ({version.strip()})")
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

    p_bump = sub.add_parser("bump", help="re-pin to VERSION (e.g. 1053.01)")
    p_bump.add_argument("version")
    p_bump.add_argument(
        "--from",
        dest="source",
        help="read the zip or installer from this path or URL instead of "
        "IBKR's per-version zip",
    )
    p_bump.add_argument(
        "--url",
        help="the URL to pin, when --from is a local copy of it",
    )

    p_unpack = sub.add_parser(
        "unpack", help="write every file of a zip or installer to DEST"
    )
    p_unpack.add_argument("source")
    p_unpack.add_argument("dest", type=Path)

    args = parser.parse_args(argv)
    if args.command == "status":
        return status(args.check)
    if args.command == "unpack":
        return unpack(args.source, args.dest)
    return bump(args.version, args.source, args.url)


if __name__ == "__main__":
    sys.exit(main())
