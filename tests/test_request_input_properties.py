"""A request made with any Contract or Order a user may pass sends exactly
one frame, or is refused before it sends anything.

The client connects to a recording connection at the newest server
version, so the protobuf converters encode every request. For each request
method and each generated Contract and Order, the test checks that the
method sends one frame, or raises ValueError or TypeError and sends
nothing. If a frame went out before the exception, the server would hold a
request that the caller believes was refused. A refused request also
leaves no request and no subscription registered: a request left behind
waits for an answer that never comes, and a stream left behind would hand
the corrected call a Ticker that never updates.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async.order import Order
from tests._property import examples
from tests._session import Session, ready
from tests._strategies import orders, userContracts

# The types an awaitable request resolves to.
Answer = (
    ibi.BarDataList
    | datetime
    | list[ibi.HistogramData]
    | list[ibi.HistoricalTick]
    | list[ibi.ContractDetails]
    | list[ibi.Contract | list[ibi.Contract | None] | None]
    | ibi.OptionComputation
    | ibi.HistoricalSchedule
    | ibi.OrderState
    | list[ibi.ContractDescription]
    | list[ibi.DepthMktDataDescription]
    | str
    | int
    | list[ibi.Position]
    | list[ibi.Fill]
    | list[ibi.Trade]
    | list[ibi.PriceIncrement]
    | list[ibi.OptionChain]
    | list[ibi.NewsProvider]
    | ibi.NewsArticle
    | list[ibi.HistoricalNews]
    | list[ibi.SoftDollarTier]
    | list[ibi.FamilyCode]
    | None
)
# The types a request method returns when called. It returns a live
# object, a flag, or an awaitable for the answer.
Started = (
    ibi.Ticker
    | ibi.Trade
    | ibi.RealTimeBarList
    | ibi.ScanDataList
    | ibi.PnL
    | ibi.PnLSingle
    | bool
    | None
    | Awaitable[Answer]
)
Request = Callable[[ibi.IB, ibi.Contract, Order], Started]

REQUESTS: dict[str, Request] = {
    "reqMktData": lambda ib, c, o: ib.reqMktData(c),
    "reqMktDepth": lambda ib, c, o: ib.reqMktDepth(c),
    "reqTickByTickData": lambda ib, c, o: ib.reqTickByTickData(c, "Last"),
    "reqRealTimeBars": lambda ib, c, o: ib.reqRealTimeBars(c, 5, "TRADES", True),
    "reqHistoricalData": lambda ib, c, o: ib.reqHistoricalDataAsync(
        c, "", "1 D", "1 min", "TRADES", True
    ),
    "reqHeadTimeStamp": lambda ib, c, o: ib.reqHeadTimeStampAsync(c, "TRADES", True, 1),
    "reqHistogramData": lambda ib, c, o: ib.reqHistogramDataAsync(c, True, "1 day"),
    "reqHistoricalTicks": lambda ib, c, o: ib.reqHistoricalTicksAsync(
        c, "", "20261016 12:00:00", 100, "TRADES", True
    ),
    "reqContractDetails": lambda ib, c, o: ib.reqContractDetailsAsync(c),
    "qualifyContracts": lambda ib, c, o: ib.qualifyContractsAsync(c),
    "calculateImpliedVolatility": lambda ib, c, o: ib.calculateImpliedVolatilityAsync(
        c, 1.0, 100.0
    ),
    "calculateOptionPrice": lambda ib, c, o: ib.calculateOptionPriceAsync(
        c, 0.2, 100.0
    ),
    "reqHistoricalSchedule": lambda ib, c, o: ib.reqHistoricalScheduleAsync(c, 5),
    "placeOrder": lambda ib, c, o: ib.placeOrder(c, o),
    "whatIfOrder": lambda ib, c, o: ib.whatIfOrderAsync(c, o),
}

# Requests that take no contract or order. Each sends exactly one frame.
SCAN = ibi.ScannerSubscription(
    instrument="STK", locationCode="STK.US", scanCode="TOP_PERC_GAIN"
)
FIXED_REQUESTS: dict[str, Callable[[ibi.IB], Started]] = {
    "reqMatchingSymbols": lambda ib: ib.reqMatchingSymbolsAsync("AAPL"),
    "reqSmartComponents": lambda ib: ib.reqSmartComponentsAsync("a6"),
    "reqMktDepthExchanges": lambda ib: ib.reqMktDepthExchangesAsync(),
    "reqScannerSubscription": lambda ib: ib.reqScannerSubscription(SCAN),
    "reqScannerParameters": lambda ib: ib.reqScannerParametersAsync(),
    "reqPnL": lambda ib: ib.reqPnL("DU1"),
    "reqPnLSingle": lambda ib: ib.reqPnLSingle("DU1", "", 10),
    "reqPositions": lambda ib: ib.reqPositionsAsync(),
    "reqPositionsMulti": lambda ib: ib.reqPositionsMultiAsync("DU1", "M1"),
    "reqAccountUpdates": lambda ib: ib.reqAccountUpdatesAsync("DU1"),
    "reqAccountUpdatesMulti": lambda ib: ib.reqAccountUpdatesMultiAsync("DU1", "M1"),
    "reqAccountSummary": lambda ib: ib.reqAccountSummaryAsync(),
    "reqExecutions": lambda ib: ib.reqExecutionsAsync(),
    "reqExecutionsFiltered": lambda ib: ib.reqExecutionsAsync(
        ibi.ExecutionFilter(acctCode="DU1", symbol="AAPL", secType="STK")
    ),
    "reqOpenOrders": lambda ib: ib.reqOpenOrdersAsync(),
    "reqAllOpenOrders": lambda ib: ib.reqAllOpenOrdersAsync(),
    "reqCompletedOrders": lambda ib: ib.reqCompletedOrdersAsync(True),
    "reqAutoOpenOrders": lambda ib: ib.reqAutoOpenOrders(True),
    "reqGlobalCancel": lambda ib: ib.reqGlobalCancel(),
    "reqCurrentTime": lambda ib: ib.reqCurrentTimeAsync(),
    "reqCurrentTimeInMillis": lambda ib: ib.reqCurrentTimeInMillisAsync(),
    "reqMarketDataType": lambda ib: ib.reqMarketDataType(3),
    "reqMarketRule": lambda ib: ib.reqMarketRuleAsync(26),
    "reqSecDefOptParams": lambda ib: ib.reqSecDefOptParamsAsync(
        "AAPL", "", "STK", 265598
    ),
    "reqNewsProviders": lambda ib: ib.reqNewsProvidersAsync(),
    "reqNewsArticle": lambda ib: ib.reqNewsArticleAsync("BRFG", "BRFG$1"),
    "reqHistoricalNews": lambda ib: ib.reqHistoricalNewsAsync(
        265598, "BRFG", "", "", 10
    ),
    "reqNewsBulletins": lambda ib: ib.reqNewsBulletins(True),
    "reqUserInfo": lambda ib: ib.reqUserInfoAsync(),
    "reqWshMetaData": lambda ib: ib.reqWshMetaData(),
    "reqWshEventData": lambda ib: ib.reqWshEventData(ibi.WshEventData(conId=265598)),
    "reqSoftDollarTiers": lambda ib: ib.reqSoftDollarTiersAsync(),
    "reqFamilyCodes": lambda ib: ib.reqFamilyCodesAsync(),
    "requestFA": lambda ib: ib.requestFA(1),
    "reqConfig": lambda ib: ib.reqConfigAsync(),
}

# Requests followed by their cancels. Each function makes the request and
# counts the frames sent so far. It then sends the cancel and returns the
# count.
STOCK = ibi.Stock("AAPL", "SMART", "USD", conId=265598)


def framesSent(session: Session) -> int:
    session.run()
    return len(session.conn.sent)


def cancelMktData(s: Session) -> int:
    s.ib.reqMktData(STOCK)
    before = framesSent(s)
    s.ib.cancelMktData(STOCK)
    return before


def cancelMktDepth(s: Session) -> int:
    s.ib.reqMktDepth(STOCK)
    before = framesSent(s)
    s.ib.cancelMktDepth(STOCK)
    return before


def cancelTickByTickData(s: Session) -> int:
    s.ib.reqTickByTickData(STOCK, "Last")
    before = framesSent(s)
    s.ib.cancelTickByTickData(STOCK, "Last")
    return before


def cancelRealTimeBars(s: Session) -> int:
    bars = s.ib.reqRealTimeBars(STOCK, 5, "TRADES", True)
    before = framesSent(s)
    s.ib.cancelRealTimeBars(bars)
    return before


def cancelPnL(s: Session) -> int:
    s.ib.reqPnL("DU1")
    before = framesSent(s)
    s.ib.cancelPnL("DU1")
    return before


def cancelPnLSingle(s: Session) -> int:
    s.ib.reqPnLSingle("DU1", "", 10)
    before = framesSent(s)
    s.ib.cancelPnLSingle("DU1", "", 10)
    return before


def cancelScannerSubscription(s: Session) -> int:
    scan = s.ib.reqScannerSubscription(SCAN)
    before = framesSent(s)
    s.ib.cancelScannerSubscription(scan)
    return before


def cancelNewsBulletins(s: Session) -> int:
    s.ib.reqNewsBulletins(True)
    before = framesSent(s)
    s.ib.cancelNewsBulletins()
    return before


def cancelWshMetaData(s: Session) -> int:
    s.ib.reqWshMetaData()
    before = framesSent(s)
    s.ib.cancelWshMetaData()
    return before


def cancelWshEventData(s: Session) -> int:
    s.ib.reqWshEventData(ibi.WshEventData(conId=265598))
    before = framesSent(s)
    s.ib.cancelWshEventData()
    return before


def cancelOrder(s: Session) -> int:
    trade = s.ib.placeOrder(STOCK, ibi.MarketOrder("BUY", 1))
    before = framesSent(s)
    s.ib.cancelOrder(trade.order)
    return before


CANCELS: dict[str, Callable[[Session], int]] = {
    f.__name__: f
    for f in (
        cancelMktData,
        cancelMktDepth,
        cancelTickByTickData,
        cancelRealTimeBars,
        cancelPnL,
        cancelPnLSingle,
        cancelScannerSubscription,
        cancelNewsBulletins,
        cancelWshMetaData,
        cancelWshEventData,
        cancelOrder,
    )
}

Refusal = ValueError | TypeError


def attempt(
    session: Session, start: Callable[[], Started]
) -> tuple[Refusal | None, int]:
    """Make the request. Return the refusal and the number of frames sent.
    The refusal is the exception the request raised, or None if the
    request was sent. An awaitable result is started as a task. The test
    counts its frames and then cancels the task. The cancel may send its
    own frame, which is not counted."""
    before = len(session.conn.sent)
    try:
        result = start()
    except (ValueError, TypeError) as exc:
        return exc, len(session.conn.sent) - before
    refusal: Refusal | None = None
    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
        task = asyncio.ensure_future(result, loop=session.loop)
        session.run()
        if task.done() and not task.cancelled() and task.exception() is not None:
            raised = task.exception()
            assert isinstance(raised, ValueError | TypeError), raised
            refusal = raised
        sent = len(session.conn.sent) - before
        task.cancel()
        session.run()
        return refusal, sent
    return None, len(session.conn.sent) - before


@given(
    name=st.sampled_from(sorted(REQUESTS)),
    contract=userContracts,
    order=st.one_of(orders(), st.builds(ibi.MarketOrder, st.just("BUY"), st.just(100))),
)
@examples()
def test_request_sends_one_frame_or_refuses_before_sending(
    name: str, contract: ibi.Contract, order: Order
) -> None:
    session = Session()
    ready(session)
    refusal, sent = attempt(
        session, lambda: REQUESTS[name](session.ib, contract, order)
    )
    if refusal is None:
        assert sent == 1, (name, sent)
    else:
        assert sent == 0, (name, refusal)
        # Nothing was sent, so nothing waits for an answer.
        assert len(session.ib.wrapper.requests) == 0, (name, refusal)
        assert len(session.ib.wrapper.subscriptions) == 0, (name, refusal)


@dataclass(frozen=True, slots=True)
class Retry:
    """A call with an argument the encoder rejects, and the same call
    corrected."""

    rejected: Callable[[ibi.IB], Started]
    corrected: Callable[[ibi.IB], Started]


OPTION_STR_STRIKE = ibi.Option("AAPL", "20261218", "150", "C", "SMART")  # type: ignore[arg-type]
OPTION = ibi.Option("AAPL", "20261218", 150, "C", "SMART")
SCAN_STR_ROWS = ibi.ScannerSubscription(
    instrument="STK",
    locationCode="STK.US",
    scanCode="TOP_PERC_GAIN",
    numberOfRows="10",  # type: ignore[arg-type]
)

STREAM_RETRIES: dict[str, Retry] = {
    "reqMktData": Retry(
        lambda ib: ib.reqMktData(STOCK, 233),  # type: ignore[arg-type]
        lambda ib: ib.reqMktData(STOCK, "233"),
    ),
    "reqMktData snapshot": Retry(
        lambda ib: ib.reqMktData(OPTION_STR_STRIKE, snapshot=True),
        lambda ib: ib.reqMktData(OPTION, snapshot=True),
    ),
    "reqTickByTickData": Retry(
        lambda ib: ib.reqTickByTickData(STOCK, "Last", "0"),  # type: ignore[arg-type]
        lambda ib: ib.reqTickByTickData(STOCK, "Last", 0),
    ),
    "reqMktDepth": Retry(
        lambda ib: ib.reqMktDepth(STOCK, "5"),  # type: ignore[arg-type]
        lambda ib: ib.reqMktDepth(STOCK, 5),
    ),
    "reqRealTimeBars": Retry(
        lambda ib: ib.reqRealTimeBars(OPTION_STR_STRIKE, 5, "TRADES", True),
        lambda ib: ib.reqRealTimeBars(OPTION, 5, "TRADES", True),
    ),
    "reqPnL": Retry(
        lambda ib: ib.reqPnL("DU1", 7),  # type: ignore[arg-type]
        lambda ib: ib.reqPnL("DU1", "7"),
    ),
    "reqPnLSingle": Retry(
        lambda ib: ib.reqPnLSingle("DU1", "", "10"),  # type: ignore[arg-type]
        lambda ib: ib.reqPnLSingle("DU1", "", 10),
    ),
    "reqScannerSubscription": Retry(
        lambda ib: ib.reqScannerSubscription(SCAN_STR_ROWS),
        lambda ib: ib.reqScannerSubscription(SCAN),
    ),
}


@pytest.mark.parametrize("name", sorted(STREAM_RETRIES))
def test_a_stream_the_encoder_rejects_leaves_no_subscription(name: str) -> None:
    """The rejected call registers nothing, so the corrected call sends its
    request. Streams are deduplicated by contract: a subscription left by
    the rejected call would hand the corrected call a Ticker that never
    updates, and send nothing."""
    session = Session()
    ready(session)
    retry = STREAM_RETRIES[name]

    refusal, sent = attempt(session, lambda: retry.rejected(session.ib))
    assert refusal is not None and sent == 0, (name, refusal, sent)
    assert len(session.ib.wrapper.subscriptions) == 0, name

    refusal, sent = attempt(session, lambda: retry.corrected(session.ib))
    assert refusal is None and sent == 1, (name, refusal, sent)
    assert len(session.ib.wrapper.subscriptions) == 1, name


LIMIT = ibi.LimitOrder("BUY", 1, 150.0)

# Requests with an argument the encoder rejects. Generated contracts do not
# reach most of these arguments.
REJECTED_REQUESTS: dict[str, Callable[[ibi.IB], Started]] = {
    "reqContractDetails": lambda ib: ib.reqContractDetailsAsync(OPTION_STR_STRIKE),
    "reqHistoricalData endDateTime": lambda ib: ib.reqHistoricalDataAsync(
        STOCK,
        20261016,  # type: ignore[arg-type]
        "1 D",
        "1 min",
        "TRADES",
        True,
    ),
    "reqHistoricalData keepUpToDate": lambda ib: ib.reqHistoricalDataAsync(
        OPTION_STR_STRIKE, "", "1 D", "1 min", "TRADES", True, keepUpToDate=True
    ),
    "reqHistoricalSchedule": lambda ib: ib.reqHistoricalScheduleAsync(
        OPTION_STR_STRIKE, 5
    ),
    "reqHistoricalTicks startDateTime": lambda ib: ib.reqHistoricalTicksAsync(
        STOCK,
        20261016,  # type: ignore[arg-type]
        "",
        100,
        "TRADES",
        True,
    ),
    "reqHeadTimeStamp": lambda ib: ib.reqHeadTimeStampAsync(
        OPTION_STR_STRIKE, "TRADES", True, 1
    ),
    "reqHistogramData": lambda ib: ib.reqHistogramDataAsync(
        OPTION_STR_STRIKE, True, "1 day"
    ),
    "calculateImpliedVolatility": lambda ib: ib.calculateImpliedVolatilityAsync(
        OPTION_STR_STRIKE, 1.0, 100.0
    ),
    "calculateOptionPrice": lambda ib: ib.calculateOptionPriceAsync(
        OPTION_STR_STRIKE, 0.2, 100.0
    ),
    "whatIfOrder": lambda ib: ib.whatIfOrderAsync(OPTION_STR_STRIKE, LIMIT),
    "reqExecutions": lambda ib: ib.reqExecutionsAsync(
        ibi.ExecutionFilter(clientId="7")  # type: ignore[arg-type]
    ),
    "reqSecDefOptParams": lambda ib: ib.reqSecDefOptParamsAsync(
        "AAPL",
        "",
        "STK",
        "265598",  # type: ignore[arg-type]
    ),
    "reqHistoricalNews": lambda ib: ib.reqHistoricalNewsAsync(
        "265598",  # type: ignore[arg-type]
        "BRFG",
        "",
        "",
        10,
    ),
    "reqPositionsMulti": lambda ib: ib.reqPositionsMultiAsync("DU1", 7),  # type: ignore[arg-type]
    "reqAccountUpdatesMulti": lambda ib: ib.reqAccountUpdatesMultiAsync(
        "DU1",
        7,  # type: ignore[arg-type]
    ),
}


@pytest.mark.parametrize("name", sorted(REJECTED_REQUESTS))
def test_a_request_the_encoder_rejects_leaves_nothing_registered(name: str) -> None:
    """Nothing was sent, so no answer comes. A request left registered
    would wait for it until the next disconnect."""
    session = Session()
    ready(session)
    refusal, sent = attempt(session, lambda: REJECTED_REQUESTS[name](session.ib))
    assert refusal is not None and sent == 0, (name, refusal, sent)
    assert len(session.ib.wrapper.requests) == 0, name
    assert len(session.ib.wrapper.subscriptions) == 0, name


def test_tickers_with_a_rejected_contract_end_like_a_failed_snapshot() -> None:
    """The first snapshot is sent and the second is refused. The call
    raises and leaves no subscription; the snapshot already sent ends when
    IBKR answers it, as it does after any failed reqTickers."""
    session = Session()
    ready(session)
    refusal, sent = attempt(
        session, lambda: session.ib.reqTickersAsync(STOCK, OPTION_STR_STRIKE)
    )
    assert refusal is not None and sent == 1, (refusal, sent)
    assert len(session.ib.wrapper.subscriptions) == 0
    (answering,) = session.ib.wrapper.requests
    session.ib.wrapper.tickSnapshotEnd(answering.reqId)
    assert len(session.ib.wrapper.requests) == 0


@pytest.mark.parametrize("name", sorted(FIXED_REQUESTS))
def test_fixed_request_sends_one_frame(name: str) -> None:
    session = Session()
    ready(session)
    refusal, sent = attempt(session, lambda: FIXED_REQUESTS[name](session.ib))
    assert refusal is None and sent == 1, (name, refusal, sent)


@pytest.mark.parametrize("name", sorted(CANCELS))
def test_cancel_sends_one_frame(name: str) -> None:
    session = Session()
    ready(session)
    before = CANCELS[name](session)
    session.run()
    assert len(session.conn.sent) - before == 1, name
