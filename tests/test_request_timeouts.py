"""IB.requestTimeoutEvent: a request whose time limit passed is reported
once, with its reqId and contract, and counted in the runtime counters.
The call's result is the same as before: empty, or None.

A virtual clock moves the time limits, so nothing waits on real time.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey
from ib_async._server_versions import MAX_CLIENT_VER
from tests._clock import VirtualClock, installClock
from tests._session import (
    Session,
    handshake,
    managedAccountsFrame,
    nextValidIdFrame,
    ready,
)

STOCK = ibi.Stock("AAPL", "SMART", "USD", conId=265598)
OPTION = ibi.Option("AAPL", "20261218", 150, "C", "SMART", conId=1)

# What a request that timed out returns.
Answer = list[ibi.ContractDescription] | ibi.HistoricalSchedule | None


@dataclass(frozen=True, slots=True)
class Clocked:
    """A session whose loop runs on a virtual clock."""

    session: Session
    clock: VirtualClock

    def advance(self, seconds: float) -> None:
        self.clock.advance(seconds)
        self.session.run()


def clocked(monkeypatch: pytest.MonkeyPatch) -> Clocked:
    session = Session()
    return Clocked(session, installClock(session.loop, monkeypatch))


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clocked:
    """A connected session on a virtual clock."""
    connected = clocked(monkeypatch)
    ready(connected.session)
    return connected


def reported(ib: ibi.IB) -> list[ibi.TimedOutRequest]:
    timedOut: list[ibi.TimedOutRequest] = []
    ib.requestTimeoutEvent += timedOut.append
    return timedOut


def reqIdOf(session: Session) -> int:
    (request,) = session.ib.wrapper.requests
    assert isinstance(request.key, ReqIdKey)
    return request.reqId


def test_historical_bars_that_time_out_are_reported(clock: Clocked) -> None:
    ib = clock.session.ib
    timedOut = reported(ib)
    bars = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(STOCK, "", "1 D", "1 min", "TRADES", True, timeout=5),
        loop=clock.session.loop,
    )
    clock.session.run()
    reqId = reqIdOf(clock.session)

    clock.advance(4.9)
    assert not bars.done() and timedOut == []
    clock.advance(0.2)
    assert list(bars.result()) == []
    assert timedOut == [ibi.TimedOutRequest("reqHistoricalDataAsync", 5, reqId, STOCK)]
    assert ib.runtimeState().counters.requestsTimedOut == 1


@dataclass(frozen=True, slots=True)
class Limited:
    """A request with a time limit, what it returns on a timeout, and how
    it is reported."""

    start: Callable[[ibi.IB], Awaitable[Answer]]
    limit: float
    result: Answer
    hasReqId: bool
    contract: ibi.Contract | None = None


LIMITED: dict[str, Limited] = {
    "reqMatchingSymbolsAsync": Limited(
        lambda ib: ib.reqMatchingSymbolsAsync("AAPL"), 4, None, True
    ),
    "reqMarketRuleAsync": Limited(lambda ib: ib.reqMarketRuleAsync(26), 1, None, False),
    "calculateImpliedVolatilityAsync": Limited(
        lambda ib: ib.calculateImpliedVolatilityAsync(OPTION, 1.0, 100.0),
        4,
        None,
        True,
        OPTION,
    ),
    "calculateOptionPriceAsync": Limited(
        lambda ib: ib.calculateOptionPriceAsync(OPTION, 0.2, 100.0),
        4,
        None,
        True,
        OPTION,
    ),
    "requestFAAsync": Limited(lambda ib: ib.requestFAAsync(1), 4, None, False),
    "reqHistoricalNewsAsync": Limited(
        lambda ib: ib.reqHistoricalNewsAsync(265598, "BRFG", "", "", 10, timeout=7),
        7,
        None,
        True,
    ),
    "reqHistoricalScheduleAsync": Limited(
        lambda ib: ib.reqHistoricalScheduleAsync(STOCK, 5, timeout=6),
        6,
        ibi.HistoricalSchedule(),
        True,
        STOCK,
    ),
}


@pytest.mark.parametrize("name", sorted(LIMITED))
def test_each_time_limit_is_reported_once_and_the_result_kept(
    clock: Clocked, name: str
) -> None:
    case = LIMITED[name]
    ib = clock.session.ib
    timedOut = reported(ib)
    call = asyncio.ensure_future(case.start(ib), loop=clock.session.loop)
    clock.session.run()
    reqId = reqIdOf(clock.session) if case.hasReqId else None

    clock.advance(case.limit + 0.1)
    assert call.result() == case.result
    assert timedOut == [ibi.TimedOutRequest(name, case.limit, reqId, case.contract)]
    assert ib.runtimeState().counters.requestsTimedOut == 1


def test_a_request_answered_in_time_is_not_reported(clock: Clocked) -> None:
    ib = clock.session.ib
    timedOut = reported(ib)
    symbols = asyncio.ensure_future(
        ib.reqMatchingSymbolsAsync("AAPL"), loop=clock.session.loop
    )
    clock.session.run()
    ib.wrapper.symbolSamples(reqIdOf(clock.session), [])
    clock.advance(10)
    assert symbols.result() == []
    assert timedOut == []
    assert ib.runtimeState().counters.requestsTimedOut == 0


def test_startup_requests_that_time_out_are_reported_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """connect goes on when a startup request times out (raiseSyncErrors is
    off); each one is reported by what it fetches."""
    clock = clocked(monkeypatch)
    session = clock.session
    timedOut = reported(session.ib)
    connecting = session.loop.create_task(
        session.ib.connectAsync("127.0.0.1", 7497, clientId=1, timeout=2)
    )
    session.run()
    session.receive(
        handshake(MAX_CLIENT_VER),
        nextValidIdFrame(100, proto=False),
        managedAccountsFrame(["DU1"], proto=False),
    )

    clock.advance(2.1)
    startup = [request.name for request in timedOut]
    assert startup and "executions" not in startup
    clock.advance(2.1)
    assert connecting.result() is session.ib
    assert [request.name for request in timedOut] == [*startup, "executions"]
    assert all(request.timeout == 2 for request in timedOut)
    assert session.ib.runtimeState().counters.requestsTimedOut == len(timedOut)
