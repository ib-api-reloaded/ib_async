"""Behavior behind the lint hardening: non-blocking termination, identity
hashing for result lists, and error chaining in util.run."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ib_async as ibi
from ib_async import util
from ib_async.ibcontroller import IBC
from ib_async.objects import BarDataList, RealTimeBarList, ScanDataList
from ib_async.ticker import BarList


@pytest.mark.parametrize("cls", [BarDataList, RealTimeBarList, ScanDataList, BarList])
def test_result_lists_hash_by_identity(cls):
    first, second = cls(), cls()
    assert first != second  # identity equality, even when both are empty
    assert {first: 1, second: 2}[first] == 1
    assert hash(first) == hash(first)


def test_windows_terminate_awaits_taskkill_without_blocking():
    ibc = IBC(twsVersion=1030)
    ibc._isWindows = True
    ibc._proc = MagicMock(pid=4242)
    ibc._proc.wait = AsyncMock(return_value=0)
    killer = MagicMock()
    killer.wait = AsyncMock(return_value=0)
    spawn = AsyncMock(return_value=killer)

    with (
        patch("asyncio.create_subprocess_exec", spawn),
        patch("subprocess.call") as blocking,
    ):
        util.getLoop().run_until_complete(ibc.terminateAsync())

    spawn.assert_awaited_once_with("taskkill", "/F", "/T", "/PID", "4242")
    killer.wait.assert_awaited_once()
    blocking.assert_not_called()


def test_run_chains_the_global_error_to_the_cancellation():
    async def waitForever():
        await asyncio.sleep(3600)

    def raiseGlobal():
        util.globalErrorEvent.emit(RuntimeError("from the wire"))

    util.getLoop().call_soon(raiseGlobal)
    with pytest.raises(RuntimeError, match="from the wire") as caught:
        util.run(waitForever())
    assert isinstance(caught.value.__cause__, asyncio.CancelledError)


def test_run_does_not_report_an_earlier_global_error():
    util.globalErrorEvent.emit(RuntimeError("stale, from another run"))

    async def cancelled():
        raise asyncio.CancelledError("stop")

    with pytest.raises(asyncio.CancelledError, match="stop"):
        ibi.util.run(cancelled())
