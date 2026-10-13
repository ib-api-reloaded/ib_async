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
    pyproject.write_text(PYPROJECT_SNIPPET)
    monkeypatch.setattr(meta_module, "PYPROJECT", pyproject)
    return twsapi, meta_module, pyproject


def _archive(
    dotted: str = "10.51.01",
    *,
    protos: bool = True,
    clientUtils: bool = True,
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
        "not a zip archive"
    ]


def test_extract_keeps_only_what_the_build_uses(tooling, tmp_path):
    twsapi, _, _ = tooling
    dest = tmp_path / "cache"

    twsapi.archive.extract(_archive(), dest)

    kept = sorted(p.relative_to(dest).as_posix() for p in dest.rglob("*.*"))
    assert kept == [
        "IBJts/API_VersionNum.txt",
        "IBJts/source/proto/Order.proto",
    ]


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

    assert pyproject.read_text() == PYPROJECT_SNIPPET.replace(
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
    source = tmp_path / "stable.zip"
    source.write_bytes(_archive(clientUtils=False))

    assert twsapi.main(["bump", "1051.01", "--from", str(source)]) == 1

    assert pyproject.read_text() == PYPROJECT_SNIPPET
    assert meta_module.load().version == "1046.01"


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
    monkeypatch.setattr(twsapi.archive, "fetch_published_versions", lambda: {})

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


def test_generate_protos_fetch_explains_a_pruned_archive(tooling, monkeypatch):
    twsapi, meta_module, _ = tooling
    generate = _load("generate_protos")

    def gone(_source):
        raise twsapi.archive.ArchiveUnavailable("404 — IBKR no longer serves it")

    monkeypatch.setattr(generate.archive, "read", gone)
    meta = meta_module.TwsapiMeta(version="1046.01", archive_sha256="x")

    with pytest.raises(SystemExit, match="make twsapi-bump"):
        generate._fetch_and_extract(meta)
