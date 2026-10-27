"""Access to realtime market information."""

from __future__ import annotations

import math
import numbers
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import ClassVar, Generic

from eventkit import Event, Op, event_class

from ib_async.contract import Contract
from ib_async.depth import DepthBook
from ib_async.objects import (
    Dividends,
    DOMLevel,
    EfpData,
    EmptyT,
    IBDefaults,
    MktDepthData,
    NewsTick,
    OptionComputation,
    RealTimeBar,
    TickAttrib,
    TickByTickAllLast,
    TickByTickBidAsk,
    TickByTickMidPoint,
    TickData,
)
from ib_async.order import finiteDecimal
from ib_async.util import dataclassDisplayFields, dataclassDisplayPairs

# Bounded ring of most-recent per-contract news ticks. NewsTick already
# fans out through ``IB.tickNewsEvent`` for streaming consumers; this
# deque is the snapshot view a holder of a Ticker reference can read
# without their own subscriber bookkeeping. Sized for the eyeball
# "what's recent for this name" case; raise via ``Ticker.news.maxlen``
# replacement if a strategy needs longer retention.
_NEWS_MAXLEN: int = 5


class HaltedStatus(IntEnum):
    UNAVAILABLE = -1
    NOT_HALTED = 0
    GENERAL = 1
    VOLATILITY = 2


def _new_news_deque() -> deque[NewsTick]:
    return deque(maxlen=_NEWS_MAXLEN)


def _new_update_event() -> TickerUpdateEvent:
    return TickerUpdateEvent("updateEvent")


@dataclass(slots=True)
class Ticker(Generic[EmptyT]):
    """
    Current market data such as bid, ask, last price, etc. for a contract.

    Streaming level-1 ticks of type :class:`.TickData` are stored in
    the ``ticks`` list.

    Streaming level-2 ticks of type :class:`.MktDepthData` are stored in the
    ``domTicks`` list. The order book (DOM) is available as lists of
    :class:`.DOMLevel` in ``domBids`` and ``domAsks``, best price first,
    and keyed by row in ``domBidsDict`` and ``domAsksDict``. Each is a
    read-only snapshot of the :class:`.DepthBook` in ``dom``.

    Streaming tick-by-tick ticks are stored in ``tickByTicks``.

    For options the :class:`.OptionComputation` values for the bid, ask, resp.
    last price are stored in the ``bidGreeks``, ``askGreeks`` resp.
    ``lastGreeks`` attributes. There is also ``modelGreeks`` that conveys
    the greeks as calculated by Interactive Brokers' option model.

    A numeric field holds a number, or one of the empty values of
    ``defaults`` (:class:`.IBDefaults`): ``unset`` before its first tick,
    ``emptyPrice`` and ``emptySize`` for a side with no quote. ``EmptyT``
    is the type of the empty values that are not numbers.
    ``defaults.isPrice`` and ``defaults.isSize`` tell a number from them.

    Events:
        * ``updateEvent`` (ticker: :class:`.Ticker`)
    """

    events: ClassVar = ("updateEvent",)

    contract: Contract | None = None
    time: datetime | None = None
    timestamp: float | None = None
    marketDataType: int = 1
    minTick: float | EmptyT | None = None
    bid: float | EmptyT | None = None
    bidSize: float | EmptyT | None = None
    bidExchange: str = ""
    ask: float | EmptyT | None = None
    askSize: float | EmptyT | None = None
    askExchange: str = ""
    last: float | EmptyT | None = None
    lastSize: float | EmptyT | None = None
    lastExchange: str = ""
    lastTimestamp: datetime | None = None
    prevBid: float | EmptyT | None = None
    prevBidSize: float | EmptyT | None = None
    prevAsk: float | EmptyT | None = None
    prevAskSize: float | EmptyT | None = None
    prevLast: float | EmptyT | None = None
    prevLastSize: float | EmptyT | None = None
    volume: float | EmptyT | None = None
    open: float | EmptyT | None = None
    high: float | EmptyT | None = None
    low: float | EmptyT | None = None
    close: float | EmptyT | None = None
    vwap: float | EmptyT | None = None
    low13week: float | EmptyT | None = None
    high13week: float | EmptyT | None = None
    low26week: float | EmptyT | None = None
    high26week: float | EmptyT | None = None
    low52week: float | EmptyT | None = None
    high52week: float | EmptyT | None = None
    bidYield: float | EmptyT | None = None
    askYield: float | EmptyT | None = None
    lastYield: float | EmptyT | None = None
    markPrice: float | EmptyT | None = None
    halted: HaltedStatus | float | EmptyT | None = None
    rtHistVolatility: float | EmptyT | None = None
    rtVolume: float | EmptyT | None = None
    rtTradeVolume: float | EmptyT | None = None
    rtTime: datetime | None = None
    avVolume: float | EmptyT | None = None
    tradeCount: float | EmptyT | None = None
    tradeRate: float | EmptyT | None = None
    volumeRate: float | EmptyT | None = None
    # generic tick 595: the volume traded in the last 3, 5 and 10 minutes
    volumeRate3Min: float | EmptyT | None = None
    volumeRate5Min: float | EmptyT | None = None
    volumeRate10Min: float | EmptyT | None = None
    shortable: float | EmptyT | None = None
    shortableShares: float | EmptyT | None = None
    indexFuturePremium: float | EmptyT | None = None
    futuresOpenInterest: float | EmptyT | None = None
    putOpenInterest: float | EmptyT | None = None
    callOpenInterest: float | EmptyT | None = None
    putVolume: float | EmptyT | None = None
    callVolume: float | EmptyT | None = None
    avOptionVolume: float | EmptyT | None = None
    histVolatility: float | EmptyT | None = None
    impliedVolatility: float | EmptyT | None = None
    openInterest: float | EmptyT | None = None
    lastRthTrade: float | EmptyT | None = None
    lastRegTime: str = ""
    optionBidExch: str = ""
    optionAskExch: str = ""
    bondFactorMultiplier: float | EmptyT | None = None
    creditmanMarkPrice: float | EmptyT | None = None
    creditmanSlowMarkPrice: float | EmptyT | None = None
    delayedLastTimestamp: datetime | None = None
    delayedHalted: HaltedStatus | float | EmptyT | None = None
    reutersMutualFunds: str = ""
    etfNavClose: float | EmptyT | None = None
    etfNavPriorClose: float | EmptyT | None = None
    etfNavBid: float | EmptyT | None = None
    etfNavAsk: float | EmptyT | None = None
    etfNavLast: float | EmptyT | None = None
    etfFrozenNavLast: float | EmptyT | None = None
    etfNavHigh: float | EmptyT | None = None
    etfNavLow: float | EmptyT | None = None
    socialMarketAnalytics: str = ""
    estimatedIpoMidpoint: float | EmptyT | None = None
    finalIpoLast: float | EmptyT | None = None
    # Odd-lot quote board (TickType 105-110, IBKR ``ODD_LOT_*``). Sized
    # smaller than round-lot prints; arrives only when the user includes
    # the ODD_LOT generic tick in ``reqMktData``.
    oddLotBid: float | EmptyT | None = None
    oddLotAsk: float | EmptyT | None = None
    oddLotBidSize: float | EmptyT | None = None
    oddLotAskSize: float | EmptyT | None = None
    oddLotBidExch: str = ""
    oddLotAskExch: str = ""
    dividends: Dividends | None = None
    ticks: list[TickData[EmptyT]] = field(default_factory=list)
    tickByTicks: list[
        TickByTickAllLast[EmptyT] | TickByTickBidAsk | TickByTickMidPoint
    ] = field(default_factory=list)
    dom: DepthBook = field(default_factory=DepthBook)
    domTicks: list[MktDepthData] = field(default_factory=list)
    bidGreeks: OptionComputation | None = None
    askGreeks: OptionComputation | None = None
    lastGreeks: OptionComputation | None = None
    modelGreeks: OptionComputation | None = None
    custGreeks: OptionComputation | None = None
    bidEfp: EfpData | None = None
    askEfp: EfpData | None = None
    lastEfp: EfpData | None = None
    openEfp: EfpData | None = None
    highEfp: EfpData | None = None
    lowEfp: EfpData | None = None
    closeEfp: EfpData | None = None
    auctionVolume: float | EmptyT | None = None
    auctionPrice: float | EmptyT | None = None
    auctionImbalance: float | EmptyT | None = None
    regulatoryImbalance: float | EmptyT | None = None
    bboExchange: str = ""
    snapshotPermissions: int = 0
    # Most-recent per-quote attribute flags decoded from the wire
    # ``attrMask`` on every bid/ask/last ``priceSizeTick``: ``pastLimit``
    # (consolidated quote is stale relative to its source venue),
    # ``preOpen`` (pre-market auction), ``canAutoExecute`` (regulatory
    # NBBO eligibility). Single attribute write per tick — overwrites
    # rather than appending so the hot path stays O(1) and bounded.
    tickAttrib: TickAttrib | None = None
    # Bounded ring of most-recent ``NewsTick`` items keyed by the
    # ``reqMktData`` reqId for this Ticker. Capped at ``_NEWS_MAXLEN``
    # via ``deque(maxlen=...)`` so the oldest news rolls off
    # automatically — no growth even for a long-lived ticker on a
    # news-heavy name. Empty deque by default to keep the
    # ``dataclassRepr`` output unchanged on tickers without news.
    news: deque[NewsTick] = field(default_factory=_new_news_deque, repr=False)

    defaults: IBDefaults[EmptyT] = field(default_factory=IBDefaults, repr=False)
    created: bool = False
    # The update event of this Ticker. It is a field so that
    # ``slots=True`` reserves a slot for it. ``TickerUpdateEvent`` is
    # defined further down, and the factory looks it up when a Ticker is
    # created.
    updateEvent: TickerUpdateEvent = field(
        default_factory=_new_update_event, repr=False
    )

    def __post_init__(self):
        # when copying a dataclass, the __post_init__ runs again, so we
        # want to make sure if this was _already_ created, we don't overwrite
        # everything with _another_ post_init clear.
        if not self.created:
            # Reset all float fields to the configured unset sentinel.
            # Users may provide a custom sentinel (e.g., -1.0) via IBDefaults(unset=...).
            # This ensures consistent unset semantics across all float-typed fields.
            unset = self.defaults.unset
            if unset is not None:
                self.minTick = unset
                self.bid = unset
                self.bidSize = unset
                self.ask = unset
                self.askSize = unset
                self.last = unset
                self.lastSize = unset
                self.prevBid = unset
                self.prevBidSize = unset
                self.prevAsk = unset
                self.prevAskSize = unset
                self.prevLast = unset
                self.prevLastSize = unset
                self.volume = unset
                self.open = unset
                self.high = unset
                self.low = unset
                self.close = unset
                self.vwap = unset
                self.low13week = unset
                self.high13week = unset
                self.low26week = unset
                self.high26week = unset
                self.low52week = unset
                self.high52week = unset
                self.bidYield = unset
                self.askYield = unset
                self.lastYield = unset
                self.markPrice = unset
                self.halted = unset
                self.rtHistVolatility = unset
                self.rtVolume = unset
                self.rtTradeVolume = unset
                self.avVolume = unset
                self.tradeCount = unset
                self.tradeRate = unset
                self.volumeRate = unset
                self.volumeRate3Min = unset
                self.volumeRate5Min = unset
                self.volumeRate10Min = unset
                self.shortable = unset
                self.shortableShares = unset
                self.indexFuturePremium = unset
                self.futuresOpenInterest = unset
                self.putOpenInterest = unset
                self.callOpenInterest = unset
                self.putVolume = unset
                self.callVolume = unset
                self.avOptionVolume = unset
                self.histVolatility = unset
                self.impliedVolatility = unset
                self.auctionVolume = unset
                self.auctionPrice = unset
                self.auctionImbalance = unset
                self.regulatoryImbalance = unset
                self.openInterest = unset
                self.lastRthTrade = unset
                self.bondFactorMultiplier = unset
                self.creditmanMarkPrice = unset
                self.creditmanSlowMarkPrice = unset
                self.delayedHalted = unset
                self.etfNavClose = unset
                self.etfNavPriorClose = unset
                self.etfNavBid = unset
                self.etfNavAsk = unset
                self.etfNavLast = unset
                self.etfFrozenNavLast = unset
                self.etfNavHigh = unset
                self.etfNavLow = unset
                self.estimatedIpoMidpoint = unset
                self.finalIpoLast = unset
                self.oddLotBid = unset
                self.oddLotAsk = unset
                self.oddLotBidSize = unset
                self.oddLotAskSize = unset
            self.created = True

    def __eq__(self, other):
        return self is other

    @property
    def domBids(self) -> Sequence[DOMLevel]:
        """Snapshot of the bid side of ``dom``, best price first;
        assigning replaces the bid rows."""
        return self.dom.bids

    @domBids.setter
    def domBids(self, rows: Iterable[DOMLevel]) -> None:
        self.dom.setRows(1, rows)

    @property
    def domAsks(self) -> Sequence[DOMLevel]:
        """Snapshot of the ask side of ``dom``, best price first;
        assigning replaces the ask rows."""
        return self.dom.asks

    @domAsks.setter
    def domAsks(self, rows: Iterable[DOMLevel]) -> None:
        self.dom.setRows(0, rows)

    @property
    def domBidsDict(self) -> Mapping[int, DOMLevel]:
        """Snapshot of the bid side of ``dom`` keyed by row."""
        return self.dom.bidsByRow()

    @property
    def domAsksDict(self) -> Mapping[int, DOMLevel]:
        """Snapshot of the ask side of ``dom`` keyed by row."""
        return self.dom.asksByRow()

    def __hash__(self):
        return id(self)

    def __repr__(self):
        attrs = dataclassDisplayFields(self)
        if not self.dom:
            attrs.pop("dom", None)

        clsName = self.__class__.__qualname__
        return f"{clsName}({dataclassDisplayPairs(attrs)})"

    __str__ = __repr__

    def isUnset(self, value: float | EmptyT | None) -> bool:
        """Whether ``value`` is None or the ``unset`` value of ``defaults``
        (the same object, so a NaN ``unset`` is recognized too)."""
        unset = self.defaults.unset
        return value is None or value is unset or value == unset

    def _hasSize(self, size: float | EmptyT | None) -> bool:
        """Whether ``size`` is a size above 0."""
        return self.defaults.isSize(size) and size > 0

    def hasBidAsk(self) -> bool:
        """Whether the bid and the ask each have a price and a size above 0."""
        return self.midpoint() is not None

    def midpoint(self) -> float | None:
        """
        Return average of bid and ask, or None unless the bid and the ask
        each have a price and a size above 0.
        """
        bid, ask = self.bid, self.ask
        if (
            self.defaults.isPrice(bid)
            and self.defaults.isPrice(ask)
            and self._hasSize(self.bidSize)
            and self._hasSize(self.askSize)
        ):
            return (bid + ask) * 0.5
        return None

    def marketPrice(self) -> float | None:
        """
        Return the first available one of

        * last price if within current bid/ask or no bid/ask available;
        * average of bid and ask (midpoint).

        None when there is neither: an empty value is not a price.
        """
        mid = self.midpoint()
        last, bid, ask = self.last, self.bid, self.ask
        if not self.defaults.isPrice(last):
            return mid
        if mid is None:
            return last
        if self.defaults.isPrice(bid) and self.defaults.isPrice(ask):
            if bid <= last <= ask:
                return last
        return mid


@event_class
class TickerUpdateEvent(Event):
    def trades(self) -> Tickfilter:
        """Emit trade ticks: last price and size (ticks 4 and 5, delayed
        68 and 71), RT Volume (48, generic tick 233) and RT Trade Volume
        (77, generic tick 375, which leaves out unreportable trades).

        Each of these streams reports the same trades, so bars built on a
        subscription carrying more than one count a trade once per
        stream. For bars that count each trade once, request one of
        233 or 375 and filter its tick alone:
        ``Tickfilter((48,), ticker.updateEvent)``."""
        return Tickfilter((4, 5, 48, 68, 71, 77), self)

    def bids(self) -> Tickfilter:
        """Emit bid ticks."""
        return Tickfilter((0, 1, 66, 69), self)

    def asks(self) -> Tickfilter:
        """Emit ask ticks."""
        return Tickfilter((2, 3, 67, 70), self)

    def bidasks(self) -> Tickfilter:
        """Emit bid and ask ticks."""
        return Tickfilter((0, 1, 66, 69, 2, 3, 67, 70), self)

    def midpoints(self) -> Tickfilter:
        """Emit midpoint ticks."""
        return Midpoints((), self)


@event_class
class Tickfilter(Op):
    """Tick filtering event operators that ``emit(time, price, size)``.

    ``price`` and ``size`` are floats, or None for a tick without one: an
    empty value of the ticker's :class:`~ib_async.objects.IBDefaults`
    (a side with no quote) is emitted as None, as a midpoint without a
    bid and ask is."""

    _tickTypes: set[int]

    def __init__(self, tickTypes, source=None):
        Op.__init__(self, source)
        self._tickTypes = set(tickTypes)

    def on_source(self, ticker: Ticker[EmptyT]) -> None:
        defaults = ticker.defaults
        for t in ticker.ticks:
            if t.tickType in self._tickTypes:
                price, size = t.price, t.size
                self.emit(
                    t.time,
                    price if defaults.isPrice(price) else None,
                    size if defaults.isSize(size) else None,
                )

    def timebars(self, timer: Event, maxBars: int | None = None) -> TimeBars:
        """
        Aggregate the ticks into bars of equal time: a bar completes, and
        the next starts, on each event of ``timer``, whose value is the new
        bar's time (a naive time is taken as local time);
        ``Event.timerange(start=0, step=60)`` gives a bar per minute,
        starting on the minute. A bar without ticks repeats the
        previous bar's close, with no volume; without a previous close
        (no tick yet) there is no bar. Ticks before the first timer event
        are in no bar.

        Emits each completed :class:`~ib_async.objects.RealTimeBar`; see
        :class:`BarList` for ``bars`` and its ``updateEvent``.

        Args:
            timer: The event that ends one bar and starts the next, emitting
                the next bar's ``datetime``.
            maxBars: Keep at most this many completed bars in ``bars``,
                besides the one in progress, dropping the oldest; all of
                them by default.
        """
        return TimeBars(timer, self, maxBars)

    def tickbars(self, count: int, maxBars: int | None = None) -> TickBars:
        """
        Aggregate the ticks into bars of ``count`` ticks each.

        Emits each completed :class:`~ib_async.objects.RealTimeBar`; see
        :class:`BarList` for ``bars`` and its ``updateEvent``.

        Args:
            count: The number of ticks in a bar.
            maxBars: Keep at most this many completed bars in ``bars``,
                besides the one in progress, dropping the oldest; all of
                them by default.
        """
        return TickBars(count, self, maxBars)

    def volumebars(
        self, volume: Decimal | float, maxBars: int | None = None
    ) -> VolumeBars:
        """
        Aggregate the ticks into bars of at least ``volume`` each: a bar
        completes with the tick that brings it to ``volume``, which can
        take it past (a tick is not split).

        Emits each completed :class:`~ib_async.objects.RealTimeBar`; see
        :class:`BarList` for ``bars`` and its ``updateEvent``.

        Args:
            volume: The volume of a bar.
            maxBars: Keep at most this many completed bars in ``bars``,
                besides the one in progress, dropping the oldest; all of
                them by default.
        """
        return VolumeBars(volume, self, maxBars)


@event_class
class Midpoints(Tickfilter):
    def on_source(self, ticker: Ticker[EmptyT]) -> None:
        if ticker.ticks:
            self.emit(ticker.time, ticker.midpoint(), 0)


class BarList(list[RealTimeBar]):
    """The bars of a bar operator, oldest first; the last is in progress
    until it completes.

    ``updateEvent(bars, hasNewBar)`` fires with ``hasNewBar`` True when
    the last bar has just completed (by a tick, or by a time bar's timer),
    and with False when the bar in progress changes otherwise: a tick, or
    a time bar starting flat at the last close."""

    def __init__(self, *args):
        super().__init__(*args)
        self.updateEvent = Event("updateEvent")

    def __eq__(self, other) -> bool:
        return self is other

    def __ne__(self, other) -> bool:
        return self is not other

    # Identity-hashable to match the identity equality above (list itself
    # is unhashable, hence the override).
    def __hash__(self) -> int:  # type: ignore[override]
        return id(self)


def _wholeCount(value: int) -> int | None:
    """``value`` as an int when it is a whole number (an int, numpy's; a
    bool is not), at least 1; else None."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        return None
    count = int(value)
    return count if count >= 1 else None


def _positiveVolume(value: Decimal | float) -> Decimal | None:
    """``value`` as a Decimal when it is a finite real number (a Decimal,
    an int, a float, a fraction, numpy's; a bool is not) above 0, read as
    an Order's numbers are (:func:`~ib_async.order.finiteDecimal`): an int
    of any size exactly, a float as it prints; else None."""
    if not isinstance(value, Decimal | numbers.Real):
        return None
    volume = finiteDecimal(value)
    return volume if volume is not None and volume > 0 else None


def _decimal(value: Decimal | float) -> Decimal:
    """A float (a tick's price or size) as the Decimal it reads as."""
    return Decimal(str(value))


@dataclass(slots=True)
class _BarBuilder:
    """The bar in progress, updated in constant time per tick: its prices,
    volume and tick count, and the running sum of price × size its WAP
    (volume-weighted average price) comes from. Each :meth:`bar` is a new
    snapshot, so a bar already handed out never changes.

    Until its first tick the bar is flat at ``previousClose``, the close of
    the bar before it, with no volume."""

    time: datetime
    previousClose: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: Decimal = Decimal(0)
    count: int = 0
    priceVolume: Decimal = Decimal(0)

    def add(self, price: Decimal, size: Decimal) -> None:
        if self.open is None or self.high is None or self.low is None:
            self.open = self.high = self.low = price
        else:
            self.high = max(self.high, price)
            self.low = min(self.low, price)
        self.close = price
        self.volume += size
        self.count += 1
        self.priceVolume += price * size

    @property
    def hasPrice(self) -> bool:
        return self.count > 0 or self.previousClose is not None

    def bar(self) -> RealTimeBar:
        if not self.count:
            flat = self.previousClose
            return RealTimeBar(self.time, flat, flat, flat, flat, Decimal(0), None, 0)
        return RealTimeBar(
            time=self.time,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            wap=self.priceVolume / self.volume if self.volume else None,
            count=self.count,
        )


@event_class
class _Bars(Op):
    """Aggregates ``(time, price, size)`` ticks into bars; each kind of
    bar says when one completes. Ticks without a price (a midpoint without
    a bid and ask) are skipped.

    The operator keeps its own state (the bar in progress, the last close),
    so ``bars`` is the user's: clearing or trimming it changes nothing but
    the bars it holds. When its source ends, the operator ends too; the
    bar in progress, not complete, stays in ``bars`` as it is."""

    bars: BarList
    _maxBars: int | None
    _builder: _BarBuilder | None
    # The snapshot of the bar in progress in ``bars``, which each tick's
    # snapshot replaces while it is still the last bar there.
    _published: RealTimeBar | None
    # The close of the last completed bar, which the next bar is flat at
    # until its first tick.
    _lastClose: Decimal | None

    def __init__(self, source=None, maxBars: int | None = None):
        Op.__init__(self)
        self.bars = BarList()
        self.maxBars = maxBars
        self._builder = None
        self._published = None
        self._lastClose = None
        # Last: an ended source ends the operator at once, which needs
        # its state.
        if source is not None:
            self.set_source(source)

    @property
    def maxBars(self) -> int | None:
        """The completed bars ``bars`` keeps, besides the one in progress,
        the oldest dropped first; None keeps every bar."""
        return self._maxBars

    @maxBars.setter
    def maxBars(self, maxBars: int | None) -> None:
        count = None if maxBars is None else _wholeCount(maxBars)
        if maxBars is not None and count is None:
            raise ValueError(
                f"maxBars keeps a whole number of bars, at least 1, not {maxBars!r}"
            )
        self._maxBars = count

    def on_source(self, time: datetime, price: float | None, size: float | None):
        # A tick without a finite price (a midpoint without a bid and ask)
        # is in no bar; one without a finite size adds no volume.
        if price is None or not math.isfinite(price):
            return
        builder = self._builder
        if builder is None:
            if not self._startsOnTick():
                return
            builder = self._begin(time)
        quantity = (
            _decimal(size) if size is not None and math.isfinite(size) else Decimal(0)
        )
        builder.add(_decimal(price), quantity)
        if self._isComplete(builder):
            self._complete(builder)
        else:
            self._publish(builder.bar())
            self.bars.updateEvent.emit(self.bars, False)

    def _startsOnTick(self) -> bool:
        """Whether a tick starts a bar when none is in progress."""
        return True

    def _isComplete(self, builder: _BarBuilder) -> bool:
        """Whether the bar in progress is complete after a tick."""
        return False

    def _publish(self, bar: RealTimeBar) -> None:
        """Show ``bar`` as the bar in progress: in place of its previous
        snapshot, or appended if ``bars`` no longer ends with that."""
        if self._shown():
            self.bars[-1] = bar
        else:
            self.bars.append(bar)
        self._published = bar

    def _shown(self) -> bool:
        """Whether ``bars`` still ends with the bar in progress."""
        return (
            self._published is not None
            and bool(self.bars)
            and self.bars[-1] is self._published
        )

    def _begin(self, time: datetime) -> _BarBuilder:
        """Start a bar at ``time``, shown in ``bars`` once it has a
        price."""
        self._builder = _BarBuilder(time, self._lastClose)
        return self._builder

    def _complete(self, builder: _BarBuilder) -> None:
        bar = builder.bar()
        self._publish(bar)
        self._builder = None
        self._published = None
        self._lastClose = bar.close
        if self._maxBars is not None and len(self.bars) > self._maxBars:
            del self.bars[: len(self.bars) - self._maxBars]
        self.bars.updateEvent.emit(self.bars, True)
        self.emit(bar)


@event_class
class TimeBars(_Bars):
    __doc__ = Tickfilter.timebars.__doc__

    _timer: Event | None

    def __init__(self, timer: Event, source=None, maxBars: int | None = None):
        _Bars.__init__(self, None, maxBars)
        self._timer = None
        if timer.done():
            # no bar would ever start
            self.set_done()
            return
        self._timer = timer
        timer.connect(self._on_timer, None, self._on_timer_done)
        # Last: an ended source ends the operator at once, timer and all.
        if source is not None:
            self.set_source(source)

    def _startsOnTick(self) -> bool:
        # A time bar starts on the timer; ticks before the first are not
        # in any bar.
        return False

    def _on_timer(self, time: datetime) -> None:
        if time.tzinfo is None:
            # a naive time (Event.timerange from a number of seconds) is
            # local time
            time = time.astimezone()
        builder = self._builder
        # A bar with no tick and no close to repeat was never shown: it is
        # no bar, and the next one starts in its place.
        if builder is not None and builder.hasPrice:
            self._complete(builder)
        builder = self._begin(time)
        if builder.hasPrice:
            # flat at the last close until its first tick
            self._publish(builder.bar())
            self.bars.updateEvent.emit(self.bars, False)

    def _on_timer_done(self, _timer):
        self._end()

    def on_source_done(self, _source):
        self._end()

    def _end(self) -> None:
        """Without ticks or a timer there is no next bar: stop listening
        to both, and end."""
        if self._timer is not None:
            self._timer.disconnect(self._on_timer, None, self._on_timer_done)
            self._timer = None
        self._detach()
        self.set_done()


@event_class
class TickBars(_Bars):
    __doc__ = Tickfilter.tickbars.__doc__

    _count: int

    def __init__(self, count: int, source=None, maxBars: int | None = None):
        ticks = _wholeCount(count)
        if ticks is None:
            raise ValueError(
                f"a tick bar has a whole number of ticks, at least 1, not {count!r}"
            )
        self._count = ticks
        _Bars.__init__(self, source, maxBars)

    def _isComplete(self, builder: _BarBuilder) -> bool:
        return builder.count >= self._count


@event_class
class VolumeBars(_Bars):
    __doc__ = Tickfilter.volumebars.__doc__

    _volume: Decimal

    def __init__(
        self, volume: Decimal | float, source=None, maxBars: int | None = None
    ):
        positive = _positiveVolume(volume)
        if positive is None:
            raise ValueError(f"a volume bar has a positive volume, not {volume!r}")
        self._volume = positive
        _Bars.__init__(self, source, maxBars)

    def _isComplete(self, builder: _BarBuilder) -> bool:
        return builder.volume >= self._volume
