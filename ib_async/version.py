"""Version info."""

from __future__ import annotations

import re
from importlib.metadata import version

# The release segment at the start of a PEP 440 version: 3.0.0 in 3.0.0rc1,
# 3.0.0.post1 or 3.0.0+local.1.
_RELEASE = re.compile(r"\d+(?:\.\d+)*")


def _versionInfo(version: str) -> tuple[int, ...]:
    """The release segment of ``version`` as integers.

    ``__version_info__`` has always been a tuple of integers, as in
    ib_insync, so a pre-release, post-release, dev or local label is left
    out of it; ``__version__`` keeps the whole version."""
    match = _RELEASE.match(version)
    if match is None:
        raise ValueError(f"not a version: {version!r}")
    return tuple(int(part) for part in match.group().split("."))


__version__ = version("ib_async")
__version_info__ = _versionInfo(__version__)
