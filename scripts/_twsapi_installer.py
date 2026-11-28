"""Read IBKR's TWS API Linux installer without running it.

Since 10.53 IBKR publishes the TWS API only as installers
(``tws-api-<channel>-linux-x64.sh`` and macOS / Windows builds) on its
installer page; the per-version zip stops at 10.51. The Linux installer
is an install4j shell script followed by a data block whose length the
script names (``-Dexe4j.totalDataLength=N``). The block starts with an
index of ``.dat`` files, each an LZMA stream of a zip, and ends with the
installer's own runtime (a JRE), which is not read.

Inside the zips, the root files and ``source/proto`` sit at the top
level and the client sources under ``.i4j_external_<n>/``, which the
installer strips. Directory entries, some written with Windows
separators, and the installer's own files (``.install4j/``,
``uninstall``) are skipped.
"""

from __future__ import annotations

import io
import lzma
import re
import struct
import zipfile

INSTALLER_URL = (
    "https://download2.interactivebrokers.com/installers/tws-api/"
    "{channel}/tws-api-{channel}-linux-x64.sh"
)

_SCRIPT_SCAN_BYTES = 1 << 16
_DATA_LENGTH = re.compile(rb"-Dexe4j\.totalDataLength=(\d+)")
_MAGIC = 0xE8E413D5
_EXTERNAL = re.compile(r"^\.i4j_external_\d+/")


class UnreadableInstaller(ValueError):
    """The bytes look like an installer but its data block does not parse."""


def is_installer(data: bytes) -> bool:
    """Whether ``data`` is an install4j shell installer."""
    return data.startswith(b"#!/bin/sh") and (
        _DATA_LENGTH.search(data[:_SCRIPT_SCAN_BYTES]) is not None
    )


def installer_url(channel: str) -> str:
    """The Linux installer IBKR serves for a channel, e.g. ``Latest``."""
    return INSTALLER_URL.format(channel=channel.lower())


def files(data: bytes) -> dict[str, bytes]:
    """Every file the installer installs, by its path in the install
    directory (``API_VersionNum.txt``, ``source/proto/Order.proto``, ...)."""
    match = _DATA_LENGTH.search(data[:_SCRIPT_SCAN_BYTES])
    if match is None:
        raise UnreadableInstaller("no exe4j.totalDataLength in the script")
    total = int(match[1])
    if total > len(data):
        raise UnreadableInstaller(
            f"data block of {total} bytes is longer than the file ({len(data)})"
        )
    block = data[len(data) - total :]
    try:
        installed: dict[str, bytes] = {}
        for payload in _dat_files(block):
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                for info in zf.infolist():
                    path = _installed_path(info.filename)
                    if path is not None:
                        installed[path] = zf.read(info)
    except (struct.error, lzma.LZMAError, zipfile.BadZipFile) as exc:
        raise UnreadableInstaller(f"data block does not parse: {exc}") from exc
    return installed


def to_zip(data: bytes) -> bytes:
    """The installer's files as IBKR's zip archive lays them out, under
    ``IBJts/``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in sorted(files(data).items()):
            zf.writestr(f"IBJts/{path}", content)
    return buf.getvalue()


def _dat_files(block: bytes) -> list[bytes]:
    """The decompressed ``.dat`` files of the data block, in index order."""
    magic, count = struct.unpack_from(">II", block, 0)
    if magic != _MAGIC:
        raise UnreadableInstaller(f"data block starts with {magic:#x}, not {_MAGIC:#x}")
    pos = 8
    sizes = []
    for _ in range(count):
        (name_length,) = struct.unpack_from(">H", block, pos)
        (size,) = struct.unpack_from(">Q", block, pos + 2 + name_length)
        sizes.append(size)
        pos += 10 + name_length
    payloads = []
    for size in sizes:
        stream = block[pos : pos + size]
        if len(stream) != size:
            raise UnreadableInstaller("data block ends inside a .dat file")
        decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        payloads.append(decompressor.decompress(stream))
        if not decompressor.eof:
            raise UnreadableInstaller("a .dat file's LZMA stream is cut short")
        pos += size
    return payloads


def _installed_path(name: str) -> str | None:
    """Where the installer puts a zip entry, or None for an entry it
    does not install as a file."""
    if name.endswith("/") or "\\" in name:
        return None
    if name.startswith(".install4j/") or name == "uninstall":
        return None
    return _EXTERNAL.sub("", name)
