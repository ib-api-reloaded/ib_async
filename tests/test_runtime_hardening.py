"""Behavior behind the lint hardening: non-blocking termination, identity
hashing for result lists, and error chaining in util.run."""

import asyncio

import pytest

import ib_async as ibi
from ib_async import util


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
