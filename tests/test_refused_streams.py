"""A stream that IBKR refuses with an error ends; one it keeps serving
does not.

Streams are deduplicated by contract (or account and conId for PnL). A
refused stream left registered hands the next request for it the dead
subscription's Ticker and sends nothing, so the Ticker never updates.
IBKR documents which errors end a request
(https://interactivebrokers.github.io/tws-api/message_codes.html): for
those the subscription is closed without a cancel, the Ticker keeps its
data, and the next request is sent. Errors after which the stream goes
on leave it registered.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import pytest

import ib_async as ibi
from ib_async.runtime import CodeCount
from ib_async.wrapper import STREAM_ENDING_CODES
from tests._session import Session, errorFrame, ready

STOCK = ibi.Stock("AAPL", "SMART", "USD", conId=265598)
SCAN = ibi.ScannerSubscription(
    instrument="STK", locationCode="STK.US", scanCode="TOP_PERC_GAIN"
)

Live = ibi.Ticker | ibi.RealTimeBarList | ibi.PnLSingle | ibi.ScanDataList

STREAMS: dict[str, Callable[[ibi.IB], Live]] = {
    "reqMktData": lambda ib: ib.reqMktData(STOCK),
    "reqTickByTickData": lambda ib: ib.reqTickByTickData(STOCK, "Last"),
    "reqMktDepth": lambda ib: ib.reqMktDepth(STOCK),
    "reqRealTimeBars": lambda ib: ib.reqRealTimeBars(STOCK, 5, "TRADES", True),
    "reqPnLSingle": lambda ib: ib.reqPnLSingle("DU1", "", 265598),
    "reqScannerSubscription": lambda ib: ib.reqScannerSubscription(SCAN),
}

# Each stream with "no security definition", market data with every code
# that ends it, and depth with its own.
ENDED = sorted(
    {(name, 200) for name in STREAMS}
    | {("reqMktData", code) for code in STREAM_ENDING_CODES}
    | {("reqMktDepth", 309), ("reqMktDepth", 316)}
)
# Errors after which IBKR keeps serving the stream, or that do not say it
# ended.
CONTINUED = [10090, 10091, 10167, 10197, 322, 2104]
# Notices that IBKR serves only part of the requested data.
PARTLY_SERVED = [10090, 10091]


def framesSent(session: Session) -> int:
    session.run()
    return len(session.conn.sent)


def started(name: str, proto: bool) -> tuple[Session, Live, int]:
    session = Session()
    ready(session)
    live = STREAMS[name](session.ib)
    if isinstance(live, ibi.Ticker):
        # Data the error must not clear.
        live.last = 101.5
    return session, live, framesSent(session)


def reqIdOf(session: Session) -> int:
    (sub,) = session.ib.wrapper.subscriptions
    return sub.reqId


@pytest.mark.parametrize("proto", [False, True])
@pytest.mark.parametrize(("name", "code"), ENDED)
def test_a_stream_ibkr_refuses_ends_and_can_be_requested_again(
    name: str, code: int, proto: bool
) -> None:
    session, live, sent = started(name, proto)
    session.receive(errorFrame(reqIdOf(session), code, "refused", proto))

    assert len(session.ib.wrapper.subscriptions) == 0
    # No cancel for a stream IBKR never served.
    assert framesSent(session) == sent
    again = STREAMS[name](session.ib)
    assert framesSent(session) == sent + 1
    if isinstance(live, ibi.Ticker):
        # The same pooled Ticker, with its data: a caller holding it gets
        # the new stream's ticks.
        assert again is live and live.last == 101.5


@pytest.mark.parametrize("proto", [False, True])
@pytest.mark.parametrize("code", PARTLY_SERVED)
def test_a_snapshot_ibkr_serves_in_part_still_completes(code: int, proto: bool) -> None:
    """IBKR sends what the account may see and says the rest is not
    subscribed. That is a notice: the snapshot goes on and ends with
    tickSnapshotEnd, as a full one does."""
    session = Session()
    ready(session)
    tickers = asyncio.ensure_future(
        session.ib.reqTickersAsync(STOCK), loop=session.loop
    )
    session.run()
    reqId = reqIdOf(session)

    session.receive(
        errorFrame(reqId, code, "part of the data is not subscribed", proto)
    )
    assert not tickers.done()
    assert len(session.ib.wrapper.subscriptions) == 1

    session.ib.wrapper.tickSnapshotEnd(reqId)
    session.run()
    (ticker,) = tickers.result()
    assert ticker.contract is STOCK
    counters = session.ib.runtimeState().counters
    assert counters.warnings == (CodeCount(code, 1),) and counters.errors == ()


@pytest.mark.parametrize("proto", [False, True])
@pytest.mark.parametrize("code", CONTINUED)
def test_a_stream_ibkr_goes_on_serving_stays(code: int, proto: bool) -> None:
    session, live, sent = started("reqMktData", proto)
    session.receive(errorFrame(reqIdOf(session), code, "notice", proto))

    assert len(session.ib.wrapper.subscriptions) == 1
    assert STREAMS["reqMktData"](session.ib) is live
    # Still deduplicated: nothing sent.
    assert framesSent(session) == sent
