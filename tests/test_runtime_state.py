"""IB.runtimeState: the connection, transport, requests, subscriptions and
counters, read in one step, on a session with the real client."""

from __future__ import annotations

import asyncio
import dataclasses
import struct
from collections.abc import Awaitable, Callable
from typing import TypeVar

import pytest

import ib_async as ibi
from ib_async._pb_msgids import PROTOBUF_MSG_ID
from ib_async._requests import ReqIdKey
from ib_async._server_versions import MAX_CLIENT_VER
from ib_async._subscriptions import TickByTickSub
from ib_async.runtime import (
    CodeCount,
    Counters,
    RequestState,
    RuntimeState,
    SubscriptionState,
    Tally,
)
from tests._session import Session, errorFrame, frame, ready

T = TypeVar("T")

STOCK = ibi.Stock("AAPL", "SMART", "USD", conId=265598)
OPTION = ibi.Option("AAPL", "20261218", 150, "C", "SMART")
OPTION_STR_STRIKE = ibi.Option("AAPL", "20261218", "150", "C", "SMART")  # type: ignore[arg-type]
SCAN = ibi.ScannerSubscription(
    instrument="STK", locationCode="STK.US", scanCode="TOP_PERC_GAIN"
)


def connected() -> Session:
    session = Session()
    ready(session)
    return session


def opened(session: Session) -> set[int]:
    return {r.reqId for r in session.ib.wrapper.requests if isinstance(r.key, ReqIdKey)}


def started(
    session: Session, request: Callable[[], Awaitable[T]]
) -> tuple[asyncio.Future[T], int]:
    """Start a request; return its future and its new reqId."""
    before = opened(session)
    future = asyncio.ensure_future(request(), loop=session.loop)
    session.run()
    (reqId,) = opened(session) - before
    return future, reqId


def assertConserved(state: RuntimeState, liveRequests: int, liveSubs: int) -> None:
    c = state.counters
    assert c.requestsOpened == c.requestsEnded + liveRequests, c
    assert c.subscriptionsAdded == c.subscriptionsEnded + liveSubs, c


def test_the_tally_and_its_frozen_copy_have_the_same_fields() -> None:
    assert [f.name for f in dataclasses.fields(Tally)] == [
        f.name for f in dataclasses.fields(Counters)
    ]


def test_a_new_ib_is_disconnected_with_nothing_counted() -> None:
    state = ibi.IB().runtimeState()
    assert state.connection.phase == "disconnected"
    assert not state.connection.apiReady
    assert state.connection.serverVersion is None
    assert state.counters == Tally().counters()
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.counters.framesSent = 1  # type: ignore[misc]


def test_a_connection_is_described_and_its_traffic_counted() -> None:
    session = connected()
    state = session.ib.runtimeState()
    connection = state.connection
    assert (connection.phase, connection.apiReady) == ("connected", True)
    assert (connection.host, connection.port, connection.clientId) == (
        "127.0.0.1",
        7497,
        1,
    )
    assert connection.serverVersion == MAX_CLIENT_VER
    assert connection.accounts == ("DU1",)
    transport = state.transport
    assert transport.framesSent == len(session.conn.sent)
    assert transport.bytesSent == sum(len(f) for f in session.conn.sent)
    # The handshake, nextValidId and managedAccounts.
    assert transport.framesReceived == 3
    c = state.counters
    assert (c.connectAttempts, c.connects, c.connectFailures) == (1, 1, 0)
    assert (c.framesSent, c.bytesSent) == (transport.framesSent, transport.bytesSent)
    assert c.framesReceived == 3 and c.bytesReceived == transport.bytesReceived


def test_counters_outlive_a_disconnect_and_the_transport_starts_over() -> None:
    session = connected()
    sent = session.ib.runtimeState().counters.framesSent
    session.client.disconnect()
    state = session.ib.runtimeState()
    assert state.connection.phase == "disconnected"
    assert state.counters.disconnects == 1
    assert state.counters.framesSent == sent
    assert state.transport.framesSent == 0


def test_each_request_is_counted_once_by_how_it_ends() -> None:
    session = connected()
    ib, wrapper = session.ib, session.ib.wrapper

    answered, answeredId = started(session, lambda: ib.reqContractDetailsAsync(STOCK))
    wrapper.contractDetailsEnd(answeredId)
    refused, refusedId = started(
        session, lambda: ib.reqHeadTimeStampAsync(STOCK, "TRADES", True, 1)
    )
    session.receive(errorFrame(refusedId, 162, "no data", False))
    abandoned, _ = started(session, ib.reqExecutionsAsync)
    abandoned.cancel()
    withdrawn, withdrawnId = started(
        session, lambda: ib.reqHeadTimeStampAsync(STOCK, "BID", True, 1)
    )
    ib.cancelHeadTimeStamp(withdrawnId)
    with pytest.raises(TypeError):
        ib.reqContractDetailsAsync(OPTION_STR_STRIKE)
    first = asyncio.ensure_future(ib.reqPositionsAsync(), loop=session.loop)
    second = asyncio.ensure_future(ib.reqPositionsAsync(), loop=session.loop)
    whatIf = ib.whatIfOrderAsync(STOCK, ibi.LimitOrder("BUY", 1, 150.0))
    session.run()

    state = ib.runtimeState()
    # Positions (two callers) and the whatIf wait; the abandoned executions
    # request's answer is owed.
    assert state.requests == RequestState(
        reqIdRequests=0,
        singletonRequests=1,
        compositeRequests=0,
        whatIfRequests=1,
        waitingCallers=2,
        owedAnswers=1,
    )
    c = state.counters
    assert (c.requestsOpened, c.requestsJoined) == (7, 1)
    assert (c.requestsAnswered, c.requestsRefused, c.requestsAbandoned) == (1, 1, 1)
    assert (c.requestsWithdrawn, c.requestsNotSent) == (1, 1)
    assertConserved(state, liveRequests=2, liveSubs=0)

    session.client.disconnect()
    session.run()
    state = ib.runtimeState()
    assert state.counters.requestsDisconnected == 2
    assertConserved(state, liveRequests=0, liveSubs=0)
    assert answered.result() == [] and refused.result() is None
    assert abandoned.cancelled() and withdrawn.cancelled()
    for failed in (first, second, whatIf):
        assert isinstance(failed.exception(), ConnectionError)


def test_each_subscription_is_counted_by_kind_and_by_how_it_ends() -> None:
    session = connected()
    ib = session.ib
    ib.reqMktData(STOCK)
    ib.reqMktData(OPTION, snapshot=True)
    tickByTick = ib.reqTickByTickData(STOCK, "Last")
    ib.reqMktDepth(STOCK)
    ib.reqRealTimeBars(STOCK, 5, "TRADES", True)
    ib.reqScannerSubscription(SCAN)
    ib.reqPnL("DU1")
    ib.reqPnLSingle("DU1", "", 265598)
    with pytest.raises(TypeError):
        ib.reqRealTimeBars(OPTION_STR_STRIKE, 5, "TRADES", True)

    state = ib.runtimeState()
    assert state.subscriptions == SubscriptionState(
        marketData=1,
        snapshots=1,
        tickByTick=1,
        marketDepth=1,
        realTimeBars=1,
        historicalBars=0,
        scanners=1,
        pnl=1,
        pnlSingle=1,
        pooledTickers=1,
    )
    assert tickByTick is ib.ticker(STOCK)

    reqId = next(
        sub.reqId for sub in ib.wrapper.subscriptions if isinstance(sub, TickByTickSub)
    )
    session.receive(errorFrame(reqId, 354, "not subscribed", True))
    ib.cancelMktDepth(STOCK)
    c = ib.runtimeState().counters
    assert (c.subscriptionsAdded, c.subscriptionsNotSent) == (9, 1)
    assert c.subscriptionsRefused == 1
    # The one not sent, the one refused, the one cancelled.
    assert c.subscriptionsEnded == 3
    assertConserved(ib.runtimeState(), liveRequests=0, liveSubs=6)

    session.client.disconnect()
    state = ib.runtimeState()
    assert state.counters.subscriptionsDisconnected == 6
    assertConserved(state, liveRequests=0, liveSubs=0)


def test_errors_and_warnings_are_counted_by_code() -> None:
    session = connected()
    session.receive(
        errorFrame(-1, 2104, "Market data farm connection is OK", False),
        errorFrame(-1, 2104, "Market data farm connection is OK", True),
        errorFrame(77, 354, "not subscribed", False),
    )
    c = session.ib.runtimeState().counters
    assert c.warnings == (CodeCount(2104, 2),)
    assert c.errors == (CodeCount(354, 1),)


def test_unknown_and_undecodable_messages_are_counted() -> None:
    session = connected()
    session.receive(
        frame(struct.pack(">I", PROTOBUF_MSG_ID + 999)),
        frame(struct.pack(">I", PROTOBUF_MSG_ID + 4) + b"\xff\xff\xff"),
    )
    c = session.ib.runtimeState().counters
    assert (c.unknownMessages, c.decodeFailures) == (1, 1)


def test_requests_held_back_are_counted_and_shown() -> None:
    # The API start request filled the one slot, for an interval that does
    # not pass during the test.
    session = connected()
    session.client.MaxRequests = 1
    session.client.RequestsInterval = 3600
    for symbol in ("A", "B", "C"):
        session.ib.reqMktData(ibi.Stock(symbol, "SMART", "USD", conId=ord(symbol)))
    state = session.ib.runtimeState()
    assert state.transport.throttling
    assert state.transport.queuedFrames == 3
    assert state.counters.throttleStarts == 1
    assert state.counters.mostQueued == 3
