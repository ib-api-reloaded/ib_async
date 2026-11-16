"""A live data stream, as the user sees it.

A stream is a request IBKR keeps answering until it is cancelled: market
data, a snapshot until it ends, tick-by-tick, market depth, real-time or
kept-up-to-date bars, a scanner, PnL. IBKR identifies each by a reqId,
which ``IB.streams()`` maps to its Stream. The events about one stream
(``IB.streamErrorEvent``, the reroute events) carry it, so a handler knows
which of several streams on one contract they concern.

Each kind of stream is its own type and carries exactly what it has. Two
bases group what kinds share: every :class:`ContractStream` is on one
instrument, and every :class:`TickerStream` fills a Ticker. Match on the
type::

    match stream:
        case TickByTickStream(tickType="BidAsk"):
            ...
        case TickerStream(ticker=ticker):
            ...

A Stream is a read-only view built from ib_async's own record of the
request, as the stream was when it was built: a stream sent again under a
new reqId (after a bust event) is a new Stream. Streams are equal when
they are the same type with the same reqId and request fields (a tick
type, a PnL's account and model code). Neither the contract nor the
objects they fill (Ticker, bars, scan data, PnL) are compared, and the
objects they fill are not printed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic

from ib_async.contract import Contract
from ib_async.objects import (
    BarDataList,
    EmptyT,
    PnL,
    PnLSingle,
    RealTimeBarList,
    ScanDataList,
)
from ib_async.ticker import Ticker


@dataclass(frozen=True, slots=True)
class Stream:
    """A live stream: the reqId IBKR knows it by, and logs."""

    reqId: int


@dataclass(frozen=True, slots=True)
class ContractStream(Stream):
    """A stream on one instrument."""

    contract: Contract = field(compare=False)


@dataclass(frozen=True, slots=True)
class TickerStream(ContractStream, Generic[EmptyT]):
    """A stream that fills a Ticker: market data, a snapshot, tick-by-tick
    or market depth. A streaming Ticker is shared by the instrument's
    streams; a snapshot has its own."""

    ticker: Ticker[EmptyT] = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class MarketDataStream(TickerStream[EmptyT]):
    """``IB.reqMktData``."""


@dataclass(frozen=True, slots=True)
class SnapshotStream(TickerStream[EmptyT]):
    """``IB.reqMktData(snapshot=True)``, until the snapshot ends."""


@dataclass(frozen=True, slots=True)
class TickByTickStream(TickerStream[EmptyT]):
    """``IB.reqTickByTickData``: ``tickType`` is ``"Last"``,
    ``"AllLast"``, ``"BidAsk"`` or ``"MidPoint"``."""

    tickType: str


@dataclass(frozen=True, slots=True)
class MarketDepthStream(TickerStream[EmptyT]):
    """``IB.reqMktDepth``."""


@dataclass(frozen=True, slots=True)
class RealTimeBarsStream(ContractStream):
    """``IB.reqRealTimeBars``."""

    bars: RealTimeBarList = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class HistoricalBarsStream(ContractStream):
    """``IB.reqHistoricalData(keepUpToDate=True)``."""

    bars: BarDataList = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class PnLSingleStream(ContractStream):
    """``IB.reqPnLSingle``: one position's PnL. Its contract has only the
    position's conId."""

    account: str
    modelCode: str
    pnlSingle: PnLSingle = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class ScannerStream(Stream):
    """``IB.reqScannerSubscription``."""

    scanData: ScanDataList = field(compare=False, repr=False)


@dataclass(frozen=True, slots=True)
class PnLStream(Stream):
    """``IB.reqPnL``: an account's PnL."""

    account: str
    modelCode: str
    pnl: PnL = field(compare=False, repr=False)
