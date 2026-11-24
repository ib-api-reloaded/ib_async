"""Ticker.marketDataType is the market data type IBKR reported for the
market data stream: live, frozen, delayed or delayed frozen, or None
until IBKR reports one.

IBKR sends it per request in its MarketDataType message, separately from
the prices: prices can arrive before the type, and asking for live data
does not mean IBKR serves it. A new market data stream starts unknown,
also on a Ticker that a depth stream kept live.
"""

from __future__ import annotations

import logging

import pytest

from ib_async import MarketDataType
from ib_async.util import getLoop
from tests._sim import CONTRACT, Ask, SimulatedTws


def started() -> SimulatedTws:
    return SimulatedTws(getLoop())


def ask(tws: SimulatedTws, kind: str) -> Ask:
    [found] = tws.openAsks(kind)
    return found


def reqIdOf(tws: SimulatedTws, kind: str) -> int:
    reqId = ask(tws, kind).reqId
    assert reqId is not None
    return reqId


def test_the_type_is_unknown_until_ibkr_reports_it() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    assert ticker.marketDataType is None

    tws.quote(ask(tws, "reqMktData"), 100.0, 101.0)
    assert ticker.marketDataType is None

    tws.wrapper.marketDataType(reqIdOf(tws, "reqMktData"), 1)
    assert ticker.marketDataType is MarketDataType.LIVE


def test_each_reported_type_is_kept_until_the_next() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    reqId = reqIdOf(tws, "reqMktData")

    for value, kind in [
        (2, MarketDataType.FROZEN),
        (3, MarketDataType.DELAYED),
        (4, MarketDataType.DELAYED_FROZEN),
        (1, MarketDataType.LIVE),
    ]:
        tws.wrapper.marketDataType(reqId, value)
        assert ticker.marketDataType is kind


def test_a_reported_type_fires_the_update_event() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    seen: list[MarketDataType | None] = []
    ticker.updateEvent += lambda t: seen.append(t.marketDataType)

    tws.wrapper.marketDataType(reqIdOf(tws, "reqMktData"), 3)
    tws.wrapper.tcpDataProcessed()

    assert seen == [MarketDataType.DELAYED]


def test_a_new_stream_starts_unknown_on_a_ticker_depth_kept_live() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()
    tws.wrapper.marketDataType(reqIdOf(tws, "reqMktData"), 1)

    tws.ib.cancelMktData(CONTRACT)
    assert ticker.marketDataType is None
    again = tws.ib.reqMktData(CONTRACT)

    assert again is ticker and again.marketDataType is None


def test_a_snapshot_gets_its_own_type() -> None:
    tws = started()
    snapshot = tws.ib.reqMktData(CONTRACT, snapshot=True)
    tws.run()

    tws.wrapper.marketDataType(reqIdOf(tws, "reqMktData"), 4)

    assert snapshot.marketDataType is MarketDataType.DELAYED_FROZEN


def test_a_type_outside_ibkrs_four_is_logged_and_ignored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    reqId = reqIdOf(tws, "reqMktData")

    with caplog.at_level(logging.WARNING):
        tws.wrapper.marketDataType(reqId, 9)

    assert ticker.marketDataType is None
    assert f"unknown market data type 9 for reqId {reqId}" in caplog.text
