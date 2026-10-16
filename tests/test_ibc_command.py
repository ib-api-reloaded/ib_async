"""The IBC start command."""

from __future__ import annotations

import asyncio
import logging
import sys

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


def test_an_option_without_a_windows_switch_is_left_out_there(monkeypatch, caplog):
    """Warned of once, when the IBC is made: a Watchdog starts it again on
    every restart."""
    monkeypatch.setattr(sys, "platform", "win32")
    with caplog.at_level(logging.WARNING, logger="ib_async.IBC"):
        ibc = IBC(1019, twsSettingsPath=r"C:\Jts")
        commands = [ibc._command(), ibc._command()]
    for command in commands:
        assert r"C:\Jts" not in command and "1019" in command
    assert [r.getMessage() for r in caplog.records] == [
        "IBC takes no twsSettingsPath on Windows; left out"
    ]


async def test_an_option_set_after_the_ibc_is_made_is_warned_of_at_start(
    monkeypatch, caplog
):
    """IBC is a plain dataclass, so an option may be set after it is made;
    a start warns of it then, once, however often a Watchdog restarts."""
    monkeypatch.setattr(sys, "platform", "win32")

    async def started(*command, **kwargs):
        return None

    monkeypatch.setattr(asyncio, "create_subprocess_exec", started)
    ibc = IBC(1019)
    ibc.monitorAsync = lambda: asyncio.sleep(0)  # type: ignore[method-assign]
    ibc.twsSettingsPath = r"C:\Jts"
    with caplog.at_level(logging.WARNING, logger="ib_async.IBC"):
        for _ in range(2):
            await ibc.startAsync()
            ibc._proc = None  # as after a restart's termination
    assert [r.getMessage() for r in caplog.records] == [
        "IBC takes no twsSettingsPath on Windows; left out"
    ]
