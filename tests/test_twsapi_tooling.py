"""Offline tests for the TWS API pin tooling under ``scripts/``.

IBKR prunes old archives from its download location without notice
and only publishes unversioned installers on its new download page, so
the build has to detect a vanished archive, explain the way out, and
re-pin safely. Every test here runs without network: archives are
built in memory, HTTP is stubbed, and ``HOME`` / ``pyproject.toml`` are
redirected into ``tmp_path`` so the real cache and pin are never
touched.
"""

from __future__ import annotations

import importlib.util
import io
import lzma
import struct
import sys
import urllib.error
import zipfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

PYPROJECT_SNIPPET = """\
[project]
name = "demo"

[tool.ib_async.twsapi]
# To bump: run make twsapi-bump.
version = "1046.01"
archive_sha256 = "old"

[tool.mypy]
check_untyped_defs = true
"""

# Trimmed from IBKR's installer page: the nav uses bare <span> labels
# too, which the parser must not mistake for channels.
INDEX_HTML = """
<a href="#" class="selected"><span>Download</span></a>
<a href="https://example/contribute"><span>Contribute</span></a>
<div class="download-section-header clearfix">
    <h2><span>Stable</span></h2>
    <span class="section-meta">
        Version: <strong>1050.02</strong>
        &nbsp;&bull;&nbsp; Release Date: <strong>Sep 9 2026</strong>
</div>
<div class="download-section-header clearfix">
    <h2><span>Latest</span></h2>
    <span class="section-meta">
        Version: <strong>1051.01</strong>
</div>
"""


def _load(name: str):
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tooling(tmp_path, monkeypatch):
    """The twsapi CLI with its pin and cache redirected into tmp_path."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    twsapi = _load("twsapi")
    meta_module = sys.modules["_twsapi_meta"]
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT_SNIPPET, encoding="utf-8")
    monkeypatch.setattr(meta_module, "PYPROJECT", pyproject)
    return twsapi, meta_module, pyproject


def _archive(
    dotted: str = "10.51.01",
    *,
    protos: bool = True,
    versionFile: bool = True,
) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if protos:
            zf.writestr("IBJts/source/proto/Order.proto", "message Order {}\n")
        if versionFile:
            zf.writestr("IBJts/API_VersionNum.txt", f"API_Version={dotted}\n")
        zf.writestr("IBJts/samples/Readme.txt", "not needed by the build\n")
    return buf.getvalue()


def _dat(entries: dict[str, bytes]) -> bytes:
    """One of an installer's .dat files: an LZMA-compressed zip."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return lzma.compress(buf.getvalue(), format=lzma.FORMAT_ALONE)


INSTALLER_URL = (
    "https://download2.interactivebrokers.com/installers/tws-api/"
    "latest/tws-api-latest-linux-x64.sh"
)


def _installer(version: str = "1053.01") -> bytes:
    """An install4j shell installer laid out as IBKR's Linux one: a script
    naming the data block's length, then the block: an index of .dat
    files, the files, and the installer's runtime. Its version marker
    has IBKR's installer form, ``1053.01``."""
    dats = {
        "0.dat": _dat({".install4j/launcher.jar": b"jar", "uninstall": b"#!/bin/sh"}),
        "6778.dat": _dat(
            {
                "API_VersionNum.txt": f"API_Version={version}\n".encode(),
                "source/": b"",
                "source/proto/Order.proto": b"message Order {}\n",
                "THIRD_PARTY_LICENSES\\": b"",
            }
        ),
        "6781.dat": _dat(
            {
                ".i4j_external_6781\\source\\": b"",
                ".i4j_external_6781/source/pythonclient/ibapi/client.py": b"# client\n",
            }
        ),
    }
    index = [
        struct.pack(">H", len(name)) + name.encode() + struct.pack(">Q", len(data))
        for name, data in dats.items()
    ]
    block = b"".join(
        [
            struct.pack(">II", 0xE8E413D5, len(dats)),
            *index,
            *dats.values(),
            b"installer runtime, not read",
        ]
    )
    script = (
        "#!/bin/sh\n"
        f'java -Dexe4j.totalDataLength={len(block)} -classpath "$cp" Installer\n'
        "exit $returnCode\n"
    )
    return script.encode() + block


# -- installer page -----------------------------------------------------------


def test_published_versions_reads_channels_not_nav_labels(tooling):
    twsapi, _, _ = tooling

    assert twsapi.archive.published_versions(INDEX_HTML) == {
        "Stable": "1050.02",
        "Latest": "1051.01",
    }


# -- archive layout -----------------------------------------------------------


def test_complete_archive_is_pinnable(tooling):
    twsapi, _, _ = tooling

    assert twsapi.archive.layout_problems(_archive(), "10.51.01") == []


def test_archive_with_mismatched_version_marker_is_refused(tooling):
    twsapi, _, _ = tooling

    problems = twsapi.archive.layout_problems(_archive("10.50.02"), "10.51.01")

    assert any("10.50.02" in p for p in problems)


def test_non_zip_is_refused(tooling):
    twsapi, _, _ = tooling

    assert twsapi.archive.layout_problems(b"<html>404</html>", "10.51.01") == [
        "not a zip archive or installer"
    ]


def test_extract_keeps_only_what_the_build_uses(tooling, tmp_path):
    twsapi, _, _ = tooling
    dest = tmp_path / "cache"

    twsapi.archive.extract(_archive(), dest)

    kept = sorted([p.relative_to(dest).as_posix() for p in dest.rglob("*.*")])
    assert kept == [
        "IBJts/API_VersionNum.txt",
        "IBJts/source/proto/Order.proto",
    ]


# -- installers ---------------------------------------------------------------


def test_installer_files_are_where_ibkr_installs_them(tooling):
    twsapi, _, _ = tooling

    assert twsapi.installer.files(_installer()) == {
        "API_VersionNum.txt": b"API_Version=1053.01\n",
        "source/proto/Order.proto": b"message Order {}\n",
        "source/pythonclient/ibapi/client.py": b"# client\n",
    }


def test_installer_is_pinnable(tooling):
    twsapi, _, _ = tooling

    assert twsapi.archive.layout_problems(_installer(), "10.53.01") == []


def test_installer_of_another_version_is_refused(tooling):
    twsapi, _, _ = tooling

    problems = twsapi.archive.layout_problems(_installer("1050.02"), "10.53.01")

    assert any("1050.02" in p for p in problems)


def test_extract_reads_an_installer(tooling, tmp_path):
    twsapi, _, _ = tooling
    dest = tmp_path / "cache"

    twsapi.archive.extract(_installer(), dest)

    kept = sorted([p.relative_to(dest).as_posix() for p in dest.rglob("*.*")])
    assert kept == [
        "IBJts/API_VersionNum.txt",
        "IBJts/source/proto/Order.proto",
    ]


def test_cut_short_installer_is_refused(tooling):
    twsapi, _, _ = tooling

    problems = twsapi.archive.layout_problems(_installer()[:-40], "10.53.01")

    assert len(problems) == 1
    assert problems[0].startswith("unreadable installer:")


# -- reading archives ---------------------------------------------------------


def test_pruned_archive_reads_as_unavailable(tooling, monkeypatch):
    twsapi, _, _ = tooling

    def gone(*_args, **_kwargs):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)

    monkeypatch.setattr(twsapi.archive.urllib.request, "urlopen", gone)

    with pytest.raises(twsapi.archive.ArchiveUnavailable, match="no longer serves"):
        twsapi.archive.read("https://example.invalid/twsapi.zip")


def test_missing_local_archive_reads_as_unavailable(tooling, tmp_path):
    twsapi, _, _ = tooling

    with pytest.raises(twsapi.archive.ArchiveUnavailable, match="no such"):
        twsapi.archive.read(str(tmp_path / "absent.zip"))


# -- pin rewrite --------------------------------------------------------------


def test_save_rewrites_only_the_pin(tooling):
    _, meta_module, pyproject = tooling

    meta_module.save(meta_module.TwsapiMeta(version="1051.01", archive_sha256="new"))

    assert pyproject.read_text(encoding="utf-8") == PYPROJECT_SNIPPET.replace(
        'version = "1046.01"', 'version = "1051.01"'
    ).replace('archive_sha256 = "old"', 'archive_sha256 = "new"')
    assert meta_module.load().version == "1051.01"


# -- bump ---------------------------------------------------------------------


def test_bump_pins_and_primes_the_cache(tooling, tmp_path):
    twsapi, meta_module, _ = tooling
    data = _archive()
    source = tmp_path / "twsapi_macunix.1051.01.zip"
    source.write_bytes(data)

    assert twsapi.main(["bump", "1051.01", "--from", str(source)]) == 0

    meta = meta_module.load()
    assert meta.version == "1051.01"
    assert meta.archive_sha256 == twsapi.archive.sha256(data)
    assert meta.version_file.is_file()
    assert meta.proto_dir.is_dir()


def test_bump_refuses_an_unpinnable_archive_and_keeps_the_old_pin(tooling, tmp_path):
    twsapi, meta_module, pyproject = tooling
    source = tmp_path / "no-protos.zip"
    source.write_bytes(_archive(protos=False))

    assert twsapi.main(["bump", "1051.01", "--from", str(source)]) == 1

    assert pyproject.read_text(encoding="utf-8") == PYPROJECT_SNIPPET
    assert meta_module.load().version == "1046.01"


def test_bump_from_an_installer_url_pins_the_url(tooling, monkeypatch):
    twsapi, meta_module, pyproject = tooling
    data = _installer()
    monkeypatch.setattr(
        twsapi.archive, "read", lambda source: data if source == INSTALLER_URL else b""
    )

    assert twsapi.main(["bump", "1053.01", "--from", INSTALLER_URL]) == 0

    meta = meta_module.load()
    assert meta.archive_url == INSTALLER_URL
    assert meta.archive_sha256 == twsapi.archive.sha256(data)
    assert meta.proto_dir.is_dir()
    sha = twsapi.archive.sha256(data)
    assert f'archive_sha256 = "{sha}"\narchive_url = "{INSTALLER_URL}"\n' in (
        pyproject.read_text(encoding="utf-8")
    )


def test_bump_from_a_local_installer_pins_the_given_url(tooling, tmp_path):
    twsapi, meta_module, _ = tooling
    source = tmp_path / "tws-api-latest-linux-x64.sh"
    source.write_bytes(_installer())

    argv = ["bump", "1053.01", "--from", str(source), "--url", INSTALLER_URL]
    assert twsapi.main(argv) == 0

    assert meta_module.load().archive_url == INSTALLER_URL


def test_bump_to_a_zip_drops_the_pinned_url(tooling, tmp_path):
    twsapi, meta_module, pyproject = tooling
    installer = tmp_path / "installer.sh"
    installer.write_bytes(_installer("1051.01"))
    zipped = tmp_path / "twsapi_macunix.1051.01.zip"
    data = _archive()
    zipped.write_bytes(data)
    twsapi.main(["bump", "1051.01", "--from", str(installer), "--url", INSTALLER_URL])

    assert twsapi.main(["bump", "1051.01", "--from", str(zipped)]) == 0

    assert meta_module.load().url == ""
    assert pyproject.read_text(encoding="utf-8") == PYPROJECT_SNIPPET.replace(
        'version = "1046.01"', 'version = "1051.01"'
    ).replace(
        'archive_sha256 = "old"', f'archive_sha256 = "{twsapi.archive.sha256(data)}"'
    )


# -- unpack -------------------------------------------------------------------


def test_unpack_writes_the_installed_tree(tooling, tmp_path):
    twsapi, _, _ = tooling
    source = tmp_path / "installer.sh"
    source.write_bytes(_installer())
    dest = tmp_path / "ib6"

    assert twsapi.main(["unpack", str(source), str(dest)]) == 0

    written = sorted([p.relative_to(dest).as_posix() for p in dest.rglob("*.*")])
    assert written == [
        "API_VersionNum.txt",
        "source/proto/Order.proto",
        "source/pythonclient/ibapi/client.py",
    ]


def test_unpack_reads_a_zip_without_its_top_directory(tooling, tmp_path):
    twsapi, _, _ = tooling
    source = tmp_path / "twsapi.zip"
    source.write_bytes(_archive())
    dest = tmp_path / "ib5"

    assert twsapi.main(["unpack", str(source), str(dest)]) == 0

    assert (dest / "source" / "proto" / "Order.proto").is_file()


def test_unpack_refuses_a_directory_with_files(tooling, tmp_path):
    twsapi, _, _ = tooling
    source = tmp_path / "installer.sh"
    source.write_bytes(_installer())
    dest = tmp_path / "ib6"
    dest.mkdir()
    (dest / "kept.txt").write_text("mine", encoding="utf-8")

    assert twsapi.main(["unpack", str(source), str(dest)]) == 1

    assert [p.name for p in dest.iterdir()] == ["kept.txt"]


# -- status -------------------------------------------------------------------


def test_status_check_fails_when_the_pinned_archive_is_gone(
    tooling, monkeypatch, capsys
):
    twsapi, _, _ = tooling
    monkeypatch.setattr(
        twsapi.archive,
        "probe",
        lambda url: 404 if "1046.01" in url else 200,
    )
    monkeypatch.setattr(
        twsapi.archive,
        "fetch_published_versions",
        lambda: {"Latest": "1051.01", "Stable": "1050.02"},
    )

    assert twsapi.main(["status", "--check"]) == 1
    out = capsys.readouterr().out
    assert "GONE" in out
    assert "Latest  1051.01" in out


def test_status_without_check_only_reports(tooling, monkeypatch):
    twsapi, _, _ = tooling
    monkeypatch.setattr(twsapi.archive, "probe", lambda url: 404)
    monkeypatch.setattr(twsapi.archive, "fetch_published_versions", dict)

    assert twsapi.main(["status"]) == 0


# -- build-time fetch ---------------------------------------------------------


def test_generate_protos_fetch_honours_the_archive_override(
    tooling, tmp_path, monkeypatch
):
    """A mirrored copy of the pinned archive builds when IBKR has pruned
    the original — and is still held to the pinned SHA256."""
    twsapi, meta_module, _ = tooling
    generate = _load("generate_protos")
    data = _archive("10.46.01")
    mirror = tmp_path / "mirror.zip"
    mirror.write_bytes(data)
    monkeypatch.setenv(twsapi.archive.ARCHIVE_ENV, str(mirror))
    meta = meta_module.TwsapiMeta(
        version="1046.01", archive_sha256=twsapi.archive.sha256(data)
    )

    generate._fetch_and_extract(meta)

    assert generate._cache_is_valid(meta)


def test_generate_protos_fetch_rejects_an_override_with_other_bytes(
    tooling, tmp_path, monkeypatch
):
    twsapi, meta_module, _ = tooling
    generate = _load("generate_protos")
    mirror = tmp_path / "mirror.zip"
    mirror.write_bytes(_archive("10.46.01"))
    monkeypatch.setenv(twsapi.archive.ARCHIVE_ENV, str(mirror))
    meta = meta_module.TwsapiMeta(version="1046.01", archive_sha256="0" * 64)

    with pytest.raises(SystemExit, match="SHA256 mismatch"):
        generate._fetch_and_extract(meta)


def test_generate_protos_fetches_the_pinned_installer(tooling, monkeypatch):
    twsapi, meta_module, _ = tooling
    generate = _load("generate_protos")
    data = _installer()
    monkeypatch.setattr(
        generate.archive,
        "read",
        lambda source: data if source == INSTALLER_URL else b"",
    )
    meta = meta_module.TwsapiMeta(
        version="1053.01", archive_sha256=twsapi.archive.sha256(data), url=INSTALLER_URL
    )

    generate._fetch_and_extract(meta)

    assert generate._cache_is_valid(meta)


def test_generate_protos_fetch_explains_a_pruned_archive(tooling, monkeypatch):
    twsapi, meta_module, _ = tooling
    generate = _load("generate_protos")

    def gone(_source):
        raise twsapi.archive.ArchiveUnavailable("404 — IBKR no longer serves it")

    monkeypatch.setattr(generate.archive, "read", gone)
    meta = meta_module.TwsapiMeta(version="1046.01", archive_sha256="x")

    with pytest.raises(SystemExit, match="make twsapi-bump"):
        generate._fetch_and_extract(meta)
