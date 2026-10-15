"""The IBC start command."""

from __future__ import annotations

import pytest

from ib_async.ibcontroller import IBC


def test_macos_tws_version_keeps_its_period():
    """macOS IBC takes the major version as installed, "10.19"; Windows
    and Linux take 1019. A float would turn 10.30 into "10.3"."""
    ibc = IBC(twsVersion="10.30", gateway=True, tradingMode="paper")
    command = ibc._command()
    assert "10.30" in command
    assert "--gateway" in command
    assert "--mode=paper" in command


def test_integer_tws_version():
    assert "1030" in IBC(twsVersion=1030)._command()


def test_the_tws_version_is_required():
    with pytest.raises(TypeError, match="twsVersion"):
        IBC(gateway=True)  # type: ignore[call-arg]
    for empty in (0, ""):
        with pytest.raises(ValueError, match="twsVersion"):
            IBC(twsVersion=empty)
