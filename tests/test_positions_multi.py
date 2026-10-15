"""IB.reqPositionsMulti: the positions of an account and/or model, once."""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock

import ib_async as ibi
from ib_async import Position, Stock


def _ib() -> ibi.IB:
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.return_value = 7
    ib.client.isConnected.return_value = False
    return ib


def _stock(symbol: str, conId: int) -> Stock:
    s = Stock(symbol, "SMART", "USD")
    s.conId = conId
    return s


async def test_returns_the_rows_with_their_model_then_cancels():
    ib = _ib()
    request = asyncio.ensure_future(ib.reqPositionsMultiAsync("DU1", "Growth"))
    await asyncio.sleep(0)
    ib.client.reqPositionsMulti.assert_called_once_with(7, "DU1", "Growth")

    ib.wrapper.positionMulti(
        7, "DU1", "Growth", _stock("SPY", 1), Decimal(10), Decimal("450.5")
    )
    ib.wrapper.positionMulti(7, "DU1", "Growth", _stock("QQQ", 2), Decimal(0), None)
    ib.wrapper.positionMultiEnd(7)

    rows = await request
    assert rows == [
        Position("DU1", _stock("SPY", 1), Decimal(10), Decimal("450.5"), "Growth")
    ]
    ib.client.cancelPositionsMulti.assert_called_once_with(7)


async def test_model_rows_leave_the_account_positions_alone():
    """A model's share of a position is not the account's position."""
    ib = _ib()
    ib.wrapper.position("DU1", _stock("SPY", 1), Decimal(100), Decimal(440))
    request = asyncio.ensure_future(ib.reqPositionsMultiAsync("DU1", "Growth"))
    await asyncio.sleep(0)
    ib.wrapper.positionMulti(
        7, "DU1", "Growth", _stock("SPY", 1), Decimal(10), Decimal("450.5")
    )
    ib.wrapper.positionMultiEnd(7)
    await request
    [position] = ib.positions()
    assert position.position == Decimal(100)
