"""``__version_info__`` is the release segment of any installed version."""

from __future__ import annotations

import pytest

import ib_async
from ib_async.version import _versionInfo


@pytest.mark.parametrize(
    ("version", "info"),
    [
        ("3.0.0", (3, 0, 0)),
        ("10.20.30", (10, 20, 30)),
        ("3.0", (3, 0)),
        ("3.0.0rc1", (3, 0, 0)),
        ("3.0.0a2", (3, 0, 0)),
        ("3.0.0.post1", (3, 0, 0)),
        ("3.0.0.dev4", (3, 0, 0)),
        ("3.0.0+local.1", (3, 0, 0)),
        ("3.0.0rc1.post2.dev3+g1234abc", (3, 0, 0)),
    ],
)
def test_version_info_is_the_release_segment(version: str, info: tuple[int, ...]):
    assert _versionInfo(version) == info


def test_version_that_is_not_a_version_raises():
    with pytest.raises(ValueError, match="not a version"):
        _versionInfo("unknown")


def test_package_exports_the_installed_version_info():
    assert ib_async.__version_info__ == _versionInfo(ib_async.__version__)
