# mypy: disallow-any-generics
"""Static pins for the type of the empty values (``IBDefaults``).

``make typecheck`` runs mypy on this file; nothing here runs. It pins that
an IB's ``EmptyT`` comes from the ``IBDefaults`` it is built with and
reaches its tickers, tick records and quote helpers, and that the bare
names (``IB``, ``Ticker``) mean the default, None, under
``disallow-any-generics``.
"""

from __future__ import annotations

from enum import Enum
from typing import assert_type

import ib_async as ibi
from ib_async.objects import TickByTickAllLast, TickData


class Missing(Enum):
    PRICE = "no price"
    SIZE = "no size"


def defaultIB() -> None:
    ib = ibi.IB()
    assert_type(ib, ibi.IB[None])
    ticker = ib.reqMktData(ibi.Stock("A", "SMART", "USD"))
    assert_type(ticker, ibi.Ticker[None])
    assert_type(ticker.bid, float | None)
    assert_type(ticker.ticks, list[TickData[None]])


def noneIB() -> None:
    ib = ibi.IB(ibi.IBDefaults(emptyPrice=None, emptySize=None, unset=None))
    assert_type(ib, ibi.IB[None])


def enumIB() -> None:
    ib = ibi.IB(ibi.IBDefaults(emptyPrice=Missing.PRICE, emptySize=Missing.SIZE))
    assert_type(ib, ibi.IB[Missing])
    ticker = ib.reqMktData(ibi.Stock("A", "SMART", "USD"))
    assert_type(ticker.bid, float | Missing | None)
    assert_type(ticker.ticks[0].size, float | Missing)
    tick = ticker.tickByTicks[0]
    if isinstance(tick, TickByTickAllLast):
        assert_type(tick.price, float | Missing)
    # The quote helpers read numbers only: their results never hold an
    # empty value.
    assert_type(ticker.midpoint(), float | None)
    assert_type(ticker.marketPrice(), float | None)
    bid = ticker.bid
    if ticker.defaults.isPrice(bid):
        assert_type(bid, float)


def bareNames(ib: ibi.IB, ticker: ibi.Ticker) -> None:
    # A bare name is the default, as in code written before EmptyT.
    assert_type(ib, ibi.IB[None])
    assert_type(ticker.bid, float | None)
