"""Fetch, verify, and extract IBKR's TWS API archive.

Shared by ``scripts/generate_protos.py`` (build-time fetch into the
cache) and ``scripts/twsapi.py`` (operator status / pin bump), so both
read the archive through one path with one set of failure messages.

IBKR serves the archive as ``twsapi_macunix.<version>.zip`` but prunes
old versions from that location without notice, and the replacement
installer page only offers unversioned ``latest`` / ``stable``
builds. A pinned build therefore has to notice when its archive has
disappeared and say what to do about it, rather than surfacing a bare
``HTTPError`` from deep inside ``urllib``.
"""

from __future__ import annotations

import hashlib
import io
import re
import shutil
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ARCHIVE_ENV = "IB_TWSAPI_ARCHIVE"
INDEX_URL = "https://download2.interactivebrokers.com/installers/tws-api/index.html"
FETCH_TIMEOUT_SECONDS = 120

PROTO_PREFIX = "IBJts/source/proto/"
VERSION_MEMBER = "IBJts/API_VersionNum.txt"

# The installer page heads each channel with ``<h2><span>Latest</span></h2>``
# and names its version in the same header block. Anchoring on the
# ``<h2>`` matters: the page's nav also uses bare ``<span>`` labels.
_CHANNEL_RE = re.compile(
    r"<h2>\s*<span>(?P<channel>\w+)</span>\s*</h2>"
    r".*?Version:\s*<strong>(?P<version>[\d.]+)</strong>",
    re.DOTALL,
)


class ArchiveUnavailable(Exception):
    """The archive could not be read from the given URL or path."""


def read(source: str) -> bytes:
    """Return the archive bytes from ``source``, a URL or a local path.

    Raises :class:`ArchiveUnavailable` with an operator-facing reason —
    a 404 in particular means IBKR has pruned that version.
    """
    if not source.startswith(("http://", "https://")):
        path = Path(source).expanduser()
        if not path.is_file():
            raise ArchiveUnavailable(f"no such archive file: {path}")
        return path.read_bytes()

    try:
        with urllib.request.urlopen(source, timeout=FETCH_TIMEOUT_SECONDS) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise ArchiveUnavailable(
                f"{source} returned 404 — IBKR no longer serves this version"
            ) from exc
        raise ArchiveUnavailable(f"{source} returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise ArchiveUnavailable(f"{source} unreachable: {exc.reason}") from exc


def probe(url: str) -> int | None:
    """HTTP status of a ``HEAD`` on ``url``, or None if unreachable."""
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_SECONDS) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError:
        return None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def layout_problems(data: bytes, dotted_version: str) -> list[str]:
    """Everything wrong with ``data`` as a pinnable archive, or nothing.

    A pinnable archive carries the schemas we compile and a version
    marker matching the version it was fetched as.
    """
    try:
        names = set(zipfile.ZipFile(io.BytesIO(data)).namelist())
    except zipfile.BadZipFile:
        return ["not a zip archive"]

    problems = []
    if not any(n.startswith(PROTO_PREFIX) and n.endswith(".proto") for n in names):
        problems.append(f"no .proto files under {PROTO_PREFIX}")
    if VERSION_MEMBER not in names:
        problems.append(f"missing {VERSION_MEMBER}")
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            marker = zf.read(VERSION_MEMBER).decode().strip()
        if marker != f"API_Version={dotted_version}":
            problems.append(
                f"{VERSION_MEMBER} says {marker!r}, expected "
                f"'API_Version={dotted_version}'"
            )

    return problems


def extract(data: bytes, dest: Path) -> None:
    """Replace ``dest`` with only the members the build uses: the
    ``.proto`` schemas and the version marker."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        keep = [
            m
            for m in zf.namelist()
            if m.startswith(PROTO_PREFIX) or m == VERSION_MEMBER
        ]
        zf.extractall(dest, keep)


def published_versions(html: str) -> dict[str, str]:
    """Map IBKR's installer channels to versions, e.g. ``{"Latest": "1051.01"}``."""
    return {m["channel"]: m["version"] for m in _CHANNEL_RE.finditer(html)}


def fetch_published_versions() -> dict[str, str]:
    """:func:`published_versions` for the live installer page."""
    with urllib.request.urlopen(INDEX_URL, timeout=FETCH_TIMEOUT_SECONDS) as resp:
        return published_versions(resp.read().decode("utf-8", "replace"))
