"""reqHeadTimeStamp cancels its request however it ends.

IBKR holds a head timestamp request open, against its limit of 50 open
historical requests, until it is cancelled. A request that failed or was
abandoned, and so never cancelled, kept its slot: after enough of them
new requests stopped being answered.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from unittest.mock import MagicMock

import pytest

import ib_async as ibi

REQ_ID = 5


def connected(isConnected: bool = True) -> ibi.IB:
    """An IB whose client records requests instead of sending them."""
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.isConnected.return_value = isConnected
    ib.client.getReqId.return_value = REQ_ID
    return ib


async def request(ib: ibi.IB) -> asyncio.Task[dt.datetime]:
    """A head timestamp request, started and waiting for its answer."""
    contract = ibi.Stock("AAPL", "SMART", "USD")
    task = asyncio.ensure_future(ib.reqHeadTimeStampAsync(contract, "TRADES", True, 2))
    await asyncio.sleep(0)
    return task


async def test_an_answered_request_is_cancelled():
    ib = connected()
    task = await request(ib)
    ib.wrapper.headTimestamp(REQ_ID, "1609459200")
    assert await task == dt.datetime(2021, 1, 1, tzinfo=dt.UTC)
    ib.client.cancelHeadTimeStamp.assert_called_once_with(REQ_ID)


async def test_a_request_whose_answer_fails_to_parse_is_cancelled():
    ib = connected()
    task = await request(ib)
    ib.wrapper.headTimestamp(REQ_ID, "not a time")
    with pytest.raises(ValueError):
        await task
    ib.client.cancelHeadTimeStamp.assert_called_once_with(REQ_ID)


async def test_a_request_abandoned_by_a_timeout_is_cancelled():
    ib = connected()
    task = await request(ib)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(task, 0.01)
    ib.client.cancelHeadTimeStamp.assert_called_once_with(REQ_ID)


async def test_nothing_is_sent_once_disconnected():
    ib = connected(isConnected=False)
    task = await request(ib)
    ib.wrapper.headTimestamp(REQ_ID, "1609459200")
    await task
    ib.client.cancelHeadTimeStamp.assert_not_called()


async def test_many_abandoned_requests_each_free_their_slot():
    """More than IBKR's 50 open requests, each given up on: every one is
    cancelled, so none stays open."""
    ib = connected()
    for _ in range(60):
        task = await request(ib)
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(task, 0.001)
    assert ib.client.cancelHeadTimeStamp.call_count == 60


async def test_an_abandoned_request_is_not_left_registered():
    ib = connected()
    task = await request(ib)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(task, 0.01)
    assert len(ib.wrapper.requests) == 0


async def test_a_refused_request_answers_none_and_is_cancelled():
    ib = connected()
    task = await request(ib)
    ib.wrapper.error(REQ_ID, 162, "Historical Market Data Service error", "")
    assert await task is None
    ib.client.cancelHeadTimeStamp.assert_called_once_with(REQ_ID)


async def test_a_request_cancelled_by_hand_is_cancelled_with_ibkr_once():
    ib = connected()
    task = await request(ib)
    ib.cancelHeadTimeStamp(REQ_ID)
    with pytest.raises(asyncio.CancelledError):
        await task
    ib.client.cancelHeadTimeStamp.assert_called_once_with(REQ_ID)
