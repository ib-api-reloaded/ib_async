"""A Ticker shows only live streams.

The streams on one contract (market data, tick-by-tick, market depth)
share one Ticker. It lives while a stream feeds it:

- When one stream ends and others go on, the fields it filled that no
  remaining stream fills are cleared: market data fills every quote and
  generic field, tick-by-tick Last and AllLast the last trade, BidAsk the
  quote, depth the book.
- When the last stream ends (a cancel, an error that ends it, a
  disconnect), the Ticker leaves the pool and its updateEvent is done. It
  keeps its last values for whoever holds it, and the next stream for the
  contract starts a new, empty Ticker.
"""

from __future__ import annotations

import pytest

from ib_async import Stock, Ticker
from ib_async.util import getLoop
from tests._sim import CONTRACT, Ask, SimulatedTws, TestEmpty

AnyTicker = Ticker[None] | Ticker[TestEmpty]


def started() -> SimulatedTws:
    return SimulatedTws(getLoop())


def ask(tws: SimulatedTws, kind: str) -> Ask:
    [found] = tws.openAsks(kind)
    return found


def bookOf(ticker: AnyTicker) -> list[float]:
    return [level.price for level in (*ticker.domBids, *ticker.domAsks)]


def test_a_ticker_ends_with_its_last_stream_and_keeps_its_values() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    tws.quote(ask(tws, "reqMktData"), 99.5, 100.5)

    assert tws.ib.cancelMktData(CONTRACT)

    assert ticker.updateEvent.done()
    assert (ticker.bid, ticker.ask) == (99.5, 100.5)
    assert tws.ib.ticker(CONTRACT) is None
    assert tws.ib.tickers() == []


def test_the_next_stream_after_the_end_starts_an_empty_ticker() -> None:
    tws = started()
    ended = tws.ib.reqMktData(CONTRACT)
    tws.run()
    tws.quote(ask(tws, "reqMktData"), 99.5, 100.5)
    tws.ib.cancelMktData(CONTRACT)

    ticker = tws.ib.reqMktData(CONTRACT)

    assert ticker is not ended and not ticker.updateEvent.done()
    assert ticker.isUnset(ticker.bid) and ticker.isUnset(ticker.ask)
    assert tws.ib.ticker(CONTRACT) is ticker


def test_market_data_ending_clears_its_fields_while_depth_goes_on() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT, "456")
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()
    tws.quote(ask(tws, "reqMktData"), 99.5, 100.5)
    tws.depth(ask(tws, "reqMktDepth"), 0, 0, 1, 99.4)

    tws.ib.cancelMktData(CONTRACT)

    assert not ticker.updateEvent.done()
    assert ticker.isUnset(ticker.bid) and ticker.isUnset(ticker.ask)
    assert ticker.contract is CONTRACT
    assert bookOf(ticker) == [99.4]
    assert tws.ib.ticker(CONTRACT) is ticker
    tws.depth(ask(tws, "reqMktDepth"), 0, 1, 1, 99.3)
    assert bookOf(ticker) == [99.3]


def test_depth_ending_clears_the_book_while_market_data_goes_on() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()
    tws.quote(ask(tws, "reqMktData"), 99.5, 100.5)
    tws.depth(ask(tws, "reqMktDepth"), 0, 0, 1, 99.4)

    tws.ib.cancelMktDepth(CONTRACT)

    assert not ticker.updateEvent.done()
    assert bookOf(ticker) == []
    assert (ticker.bid, ticker.ask) == (99.5, 100.5)


def test_a_field_another_stream_fills_stays_when_one_ends() -> None:
    """Market data and tick-by-tick BidAsk both fill the quote: market
    data ending clears its other fields and keeps the quote, which BidAsk
    goes on filling."""
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqTickByTickData(CONTRACT, "BidAsk")
    tws.run()
    tws.lastTick(ask(tws, "reqMktData"), 100.0)
    tws.tickByTick(ask(tws, "reqTickByTickData"), "BidAsk", 99.5)

    tws.ib.cancelMktData(CONTRACT)

    assert (ticker.bid, ticker.ask) == (99.5, 100.5)
    assert ticker.isUnset(ticker.last)
    assert not ticker.updateEvent.done()


def test_a_trade_stream_ending_clears_the_last_trade_while_depth_goes_on() -> None:
    tws = started()
    ticker = tws.ib.reqTickByTickData(CONTRACT, "Last")
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()
    tws.tickByTick(ask(tws, "reqTickByTickData"), "Last", 100.0)
    assert ticker.last == 100.0

    tws.ib.cancelTickByTickData(CONTRACT, "Last")

    assert ticker.isUnset(ticker.last) and ticker.isUnset(ticker.lastSize)
    assert not ticker.updateEvent.done()


def test_the_quote_stays_when_bid_ask_ends_while_market_data_goes_on() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqTickByTickData(CONTRACT, "BidAsk")
    tws.run()
    tws.tickByTick(ask(tws, "reqTickByTickData"), "BidAsk", 99.5)

    tws.ib.cancelTickByTickData(CONTRACT, "BidAsk")

    assert (ticker.bid, ticker.ask) == (99.5, 100.5)


def test_the_last_of_several_streams_ends_the_ticker() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqTickByTickData(CONTRACT, "BidAsk")
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()
    tws.depth(ask(tws, "reqMktDepth"), 0, 0, 1, 99.4)

    tws.ib.cancelMktData(CONTRACT)
    tws.ib.cancelTickByTickData(CONTRACT, "BidAsk")
    assert not ticker.updateEvent.done()
    tws.ib.cancelMktDepth(CONTRACT)

    assert ticker.updateEvent.done()
    assert bookOf(ticker) == [99.4]
    assert tws.ib.ticker(CONTRACT) is None


def test_an_error_that_ends_the_last_stream_ends_the_ticker() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()

    tws.refuseStream(ask(tws, "reqMktData"))

    assert ticker.updateEvent.done()
    assert tws.ib.ticker(CONTRACT) is None


def test_a_disconnect_ends_every_streamed_ticker() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()

    tws.disconnect()

    assert ticker.updateEvent.done()
    assert tws.ib.tickers() == []


def test_iterating_a_ticker_ends_with_its_stream() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    seen: list[float | None] = []

    async def follow() -> None:
        async for updated in ticker.updateEvent:
            seen.append(updated.bid)

    task = tws.start(follow())
    tws.quote(ask(tws, "reqMktData"), 99.5, 100.5)
    tws.wrapper.tcpDataProcessed()
    tws.run()
    tws.ib.cancelMktData(CONTRACT)
    tws.run()

    assert task.done() and seen == [99.5]


def test_awaiting_an_ended_ticker_fails_at_once() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    tws.ib.cancelMktData(CONTRACT)

    async def awaitUpdate() -> AnyTicker:
        return await ticker.updateEvent

    task = tws.start(awaitUpdate())

    assert isinstance(task.exception(), ValueError)


def test_streaming_contract_after_contract_keeps_no_ended_tickers() -> None:
    tws = started()
    for conId in range(2, 12):
        contract = Stock("SIM", "SMART", "USD", conId=conId)
        tws.ib.reqMktData(contract)
        tws.run()
        tws.ib.cancelMktData(contract)

    assert tws.ib.tickers() == []
    assert tws.wrapper.subscriptions.state().pooledTickers == 0


def test_a_request_that_fails_to_send_leaves_no_ticker() -> None:
    tws = started()
    tws.client.reqMktData.side_effect = ValueError("refused by the encoder")
    with pytest.raises(ValueError, match="refused by the encoder"):
        tws.ib.reqMktData(CONTRACT)
    assert tws.ib.ticker(CONTRACT) is None
    assert tws.ib.tickers() == []


def test_a_snapshot_still_has_its_own_ticker_done_at_its_end() -> None:
    tws = started()
    streamed = tws.ib.reqMktData(CONTRACT)
    tws.run()
    tws.ib.cancelMktData(CONTRACT)
    snapshot = tws.ib.reqMktData(CONTRACT, snapshot=True)
    tws.run()

    tws.snapshotEnd(ask(tws, "reqMktData"))

    assert snapshot is not streamed and snapshot.updateEvent.done()
    assert tws.ib.ticker(CONTRACT) is None
