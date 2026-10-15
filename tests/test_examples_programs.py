"""The example programs' logic, driven without a server.

The programs in ``examples/programs/`` need TWS / IB Gateway to run. Their
logic does not: each is written against a few ``IB`` methods and events,
so a stand-in that returns prepared results and emits events by hand runs
the same code paths a live session would.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from eventkit import Event

from ib_async import BarData, BarDataList, LimitOrder, Stock, TickData, Ticker, Trade

PROGRAMS = Path(__file__).resolve().parent.parent / "examples" / "programs"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, PROGRAMS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


download_bars = load("download_bars")
stream_quotes = load("stream_quotes")
order_lifecycle = load("order_lifecycle")
live_bars = load("live_bars")

T0 = dt.datetime(2026, 10, 1, 14, tzinfo=dt.UTC)


def bar(hour: int) -> BarData:
    return BarData(date=T0 + dt.timedelta(hours=hour), close=Decimal(hour))


class HistoricalData:
    """Answers each historical data request with the next prepared chunk."""

    def __init__(self, chunks: list[list[BarData]]):
        self.chunks = chunks
        self.ends: list[object] = []

    async def reqHistoricalDataAsync(self, contract, *, endDateTime, **_):
        self.ends.append(endDateTime)
        bars = BarDataList()
        if self.chunks:
            bars.extend(self.chunks.pop(0))
        return bars


async def test_download_pages_backwards_and_returns_oldest_first():
    # newest chunk first; consecutive chunks share a bar
    ib = HistoricalData([[bar(4), bar(5), bar(6)], [bar(2), bar(3), bar(4)], []])
    bars = await download_bars.downloadBars(
        ib,
        Stock("TSLA"),
        barSize="1 hour",
        chunk="1 D",
        chunks=5,
        what="TRADES",
        useRTH=True,
        pause=0,
    )
    assert [b.close for b in bars] == [Decimal(n) for n in (2, 3, 4, 5, 6)]
    # each request ends where the previous chunk started; stops at no data
    assert ib.ends == ["", bar(4).date, bar(2).date]


async def test_download_stops_after_the_chunks_asked_for():
    ib = HistoricalData([[bar(4)], [bar(3)], [bar(2)]])
    bars = await download_bars.downloadBars(
        ib,
        Stock("TSLA"),
        barSize="1 hour",
        chunk="1 D",
        chunks=2,
        what="TRADES",
        useRTH=True,
        pause=0,
    )
    assert [b.close for b in bars] == [Decimal(3), Decimal(4)]


class Session:
    """The events stream_quotes listens to."""

    def __init__(self):
        self.pendingTickersEvent = Event("pendingTickersEvent")
        self.disconnectedEvent = Event("disconnectedEvent")


async def test_stream_prints_quotes_until_the_time_is_up(capsys):
    ib = Session()
    ticker = Ticker(contract=Stock("AAPL"), time=T0, bid=1.5, bidSize=100)
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, ib.pendingTickersEvent.emit, {ticker})
    assert await stream_quotes.streamUntil(ib, 0.1) is True
    assert "AAPL   bid 100 @ 1.5  ask - @ -  last -" in capsys.readouterr().out


async def test_stream_stops_when_the_connection_drops():
    ib = Session()
    asyncio.get_running_loop().call_later(0.01, ib.disconnectedEvent.emit)
    assert await stream_quotes.streamUntil(ib, 5) is False


class Orders:
    """Accepts orders and cancels: each status change arrives a moment
    later, as it would from TWS."""

    def __init__(self, accept: str | None = "Submitted"):
        self.accept = accept
        self.trade: Trade | None = None

    def setStatus(self, status: str) -> None:
        assert self.trade is not None
        self.trade.orderStatus.status = status
        self.trade.statusEvent.emit(self.trade)

    def placeOrder(self, contract, order) -> Trade:
        self.trade = Trade(contract=contract, order=order)
        self.trade.orderStatus.status = "PendingSubmit"
        if self.accept:
            asyncio.get_running_loop().call_later(0.01, self.setStatus, self.accept)
        return self.trade

    def cancelOrder(self, order) -> None:
        asyncio.get_running_loop().call_later(0.01, self.setStatus, "Cancelled")


@pytest.mark.parametrize("accept", ["Submitted", "PreSubmitted"])
async def test_place_waits_for_the_order_then_cancels_it(accept, capsys):
    ib = Orders(accept)
    order = LimitOrder("BUY", 1, "1.00")
    assert await order_lifecycle.placeAndCancel(ib, Stock("AAPL"), order, 1) is True
    assert ib.trade is not None
    assert ib.trade.orderStatus.status == "Cancelled"
    assert "log:" in capsys.readouterr().out


async def test_an_order_never_accepted_is_still_cancelled():
    ib = Orders(accept=None)
    order = LimitOrder("BUY", 1, "1.00")
    assert await order_lifecycle.placeAndCancel(ib, Stock("AAPL"), order, 0.1) is False
    # cancelled on the way out, although it was never accepted
    assert ib.trade is not None
    assert ib.trade.orderStatus.status == "Cancelled"


async def test_waiting_stops_when_the_trade_events_end():
    # a dropped connection ends every trade's events
    trade = Trade(contract=Stock("AAPL"), order=LimitOrder("BUY", 1, "1.00"))
    trade.orderStatus.status = "PendingSubmit"
    asyncio.get_running_loop().call_later(0.01, trade.statusEvent.set_done)
    reached = await order_lifecycle.waitUntil(trade, trade.isDone, 5)
    assert reached is False


def trade(ticker: Ticker, seconds: int, price: float, size: float) -> None:
    """Deliver one trade tick to the ticker's update stream."""
    at = T0 + dt.timedelta(seconds=seconds)
    ticker.time = at
    ticker.ticks = [TickData(at, 4, price, size)]
    ticker.updateEvent.emit(ticker)


def test_live_bars_annotates_each_completed_bar():
    ticker = Ticker(contract=Stock("AAPL"))
    timer = Event("timer")
    bars = ticker.updateEvent.trades().timebars(timer)
    annotated: list = []
    live_bars.annotate(bars, emaBars=3).connect(annotated.append)

    timer.emit(T0)
    trade(ticker, 1, 10.0, 100)
    trade(ticker, 2, 12.0, 300)  # bar 1: wap (1000 + 3600) / 400 = 11.5
    timer.emit(T0 + dt.timedelta(minutes=1))
    timer.emit(T0 + dt.timedelta(minutes=2))  # bar 2: no trades, close 12
    trade(ticker, 121, 11.0, 100)  # bar 3: wap 11
    timer.emit(T0 + dt.timedelta(minutes=3))

    assert [a.bar.close for a in annotated] == [Decimal(12), Decimal(12), Decimal(11)]
    # the empty bar adds no volume, so the session VWAP holds
    assert [a.vwap for a in annotated] == [
        Decimal("11.5"),
        Decimal("11.5"),
        Decimal("5700.0") / 500,
    ]
    # EMA over 3 bars weighs each new close by 2 / (3 + 1)
    assert [a.ema for a in annotated] == [12.0, 12.0, 11.5]
    assert "session vwap 11.5000  ema 12.0000" in live_bars.formatBar(annotated[0])


def test_session_vwap_starts_unset():
    assert live_bars.SessionVwap().value is None
