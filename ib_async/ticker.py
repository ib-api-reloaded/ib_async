"""Access to realtime market information."""

import math
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import IntEnum
from typing import Any, ClassVar

from eventkit import Event, Op, event_class

from ib_async.contract import Contract
from ib_async.depth import DepthBook
from ib_async.objects import (
    Dividends,
    DOMLevel,
    EfpData,
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


@dataclass(slots=True)
class Ticker:
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

    Events:
        * ``updateEvent`` (ticker: :class:`.Ticker`)
    """

    events: ClassVar = ("updateEvent",)

    contract: Contract | None = None
    time: datetime | None = None
    timestamp: float | None = None
    marketDataType: int = 1
    minTick: float | None = None
    bid: float | None = None
    bidSize: float | None = None
    bidExchange: str = ""
    ask: float | None = None
    askSize: float | None = None
    askExchange: str = ""
    last: float | None = None
    lastSize: float | None = None
    lastExchange: str = ""
    lastTimestamp: datetime | None = None
    prevBid: float | None = None
    prevBidSize: float | None = None
    prevAsk: float | None = None
    prevAskSize: float | None = None
    prevLast: float | None = None
    prevLastSize: float | None = None
    volume: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    vwap: float | None = None
    low13week: float | None = None
    high13week: float | None = None
    low26week: float | None = None
    high26week: float | None = None
    low52week: float | None = None
    high52week: float | None = None
    bidYield: float | None = None
    askYield: float | None = None
    lastYield: float | None = None
    markPrice: float | None = None
    halted: HaltedStatus | float | None = None
    rtHistVolatility: float | None = None
    rtVolume: float | None = None
    rtTradeVolume: float | None = None
    rtTime: datetime | None = None
    avVolume: float | None = None
    tradeCount: float | None = None
    tradeRate: float | None = None
    volumeRate: float | None = None
    # generic tick 595: the volume traded in the last 3, 5 and 10 minutes
    volumeRate3Min: float | None = None
    volumeRate5Min: float | None = None
    volumeRate10Min: float | None = None
    shortable: float | None = None
    shortableShares: float | None = None
    indexFuturePremium: float | None = None
    futuresOpenInterest: float | None = None
    putOpenInterest: float | None = None
    callOpenInterest: float | None = None
    putVolume: float | None = None
    callVolume: float | None = None
    avOptionVolume: float | None = None
    histVolatility: float | None = None
    impliedVolatility: float | None = None
    openInterest: float | None = None
    lastRthTrade: float | None = None
    lastRegTime: str = ""
    optionBidExch: str = ""
    optionAskExch: str = ""
    bondFactorMultiplier: float | None = None
    creditmanMarkPrice: float | None = None
    creditmanSlowMarkPrice: float | None = None
    delayedLastTimestamp: datetime | None = None
    delayedHalted: HaltedStatus | float | None = None
    reutersMutualFunds: str = ""
    etfNavClose: float | None = None
    etfNavPriorClose: float | None = None
    etfNavBid: float | None = None
    etfNavAsk: float | None = None
    etfNavLast: float | None = None
    etfFrozenNavLast: float | None = None
    etfNavHigh: float | None = None
    etfNavLow: float | None = None
    socialMarketAnalytics: str = ""
    estimatedIpoMidpoint: float | None = None
    finalIpoLast: float | None = None
    # Odd-lot quote board (TickType 105-110, IBKR ``ODD_LOT_*``). Sized
    # smaller than round-lot prints; arrives only when the user includes
    # the ODD_LOT generic tick in ``reqMktData``.
    oddLotBid: float | None = None
    oddLotAsk: float | None = None
    oddLotBidSize: float | None = None
    oddLotAskSize: float | None = None
    oddLotBidExch: str = ""
    oddLotAskExch: str = ""
    dividends: Dividends | None = None
    ticks: list[TickData] = field(default_factory=list)
    tickByTicks: list[TickByTickAllLast | TickByTickBidAsk | TickByTickMidPoint] = (
        field(default_factory=list)
    )
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
    auctionVolume: float | None = None
    auctionPrice: float | None = None
    auctionImbalance: float | None = None
    regulatoryImbalance: float | None = None
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

    defaults: IBDefaults = field(default_factory=IBDefaults, repr=False)
    created: bool = False
    # Per-Ticker update event. Assigned in __post_init__ — declared as
    # a field (typed Any to avoid a forward reference to
    # ``TickerUpdateEvent`` which is defined further down) so that
    # ``slots=True`` reserves a slot for it.
    updateEvent: Any = field(default=None, repr=False)

    def __post_init__(self):
        # when copying a dataclass, the __post_init__ runs again, so we
        # want to make sure if this was _already_ created, we don't overwrite
        # everything with _another_ post_init clear.
        if not self.created:
            self.updateEvent = TickerUpdateEvent("updateEvent")
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

    def isUnset(self, value) -> bool:
        # if value is None, it is unset.
        # else, if value matches the default unset sentinel, it is unset.
        dev = self.defaults.unset
        return value is None or (value == dev)

    def hasBidAsk(self) -> bool:
        """See if this ticker has a valid bid and ask."""
        return (
            self.bid is not None
            and self.bid != -1
            and self.bidSize is not None
            and self.bidSize > 0
            and self.ask is not None
            and self.ask != -1
            and self.askSize is not None
            and self.askSize > 0
        )

    def midpoint(self) -> float | None:
        """
        Return average of bid and ask, or None if no valid bid and ask
        are available.
        """
        if self.hasBidAsk() and self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) * 0.5
        return None

    def marketPrice(self) -> float | None:
        """
        Return the first available one of

        * last price if within current bid/ask or no bid/ask available;
        * average of bid and ask (midpoint).
        """
        price: float | None
        if self.hasBidAsk() and self.bid is not None and self.ask is not None:
            if self.last is not None and self.bid <= self.last <= self.ask:
                price = self.last
            else:
                price = self.midpoint()
        else:
            price = self.last

        return price


@event_class
class TickerUpdateEvent(Event):
    def trades(self) -> "Tickfilter":
        """Emit trade ticks."""
        # 48 RT Volume, 77 RT Trade Volume (without unreportable trades)
        return Tickfilter((4, 5, 48, 68, 71, 77), self)

    def bids(self) -> "Tickfilter":
        """Emit bid ticks."""
        return Tickfilter((0, 1, 66, 69), self)

    def asks(self) -> "Tickfilter":
        """Emit ask ticks."""
        return Tickfilter((2, 3, 67, 70), self)

    def bidasks(self) -> "Tickfilter":
        """Emit bid and ask ticks."""
        return Tickfilter((0, 1, 66, 69, 2, 3, 67, 70), self)

    def midpoints(self) -> "Tickfilter":
        """Emit midpoint ticks."""
        return Midpoints((), self)


@event_class
class Tickfilter(Op):
    """Tick filtering event operators that ``emit(time, price, size)``."""

    _tickTypes: set[int]

    def __init__(self, tickTypes, source=None):
        Op.__init__(self, source)
        self._tickTypes = set(tickTypes)

    def on_source(self, ticker):
        for t in ticker.ticks:
            if t.tickType in self._tickTypes:
                self.emit(t.time, t.price, t.size)

    def timebars(self, timer: Event, maxBars: int | None = None) -> "TimeBars":
        """
        Aggregate the ticks into bars of equal time: a bar completes, and
        the next starts, on each event of ``timer``, whose value is the new
        bar's time; ``Event.timerange(start=0, step=60)`` gives a bar per
        minute, starting on the minute. A bar without ticks repeats the
        previous bar's close, with no volume. Ticks before the first timer
        event are in no bar.

        Emits each completed :class:`~ib_async.objects.RealTimeBar`; see
        :class:`BarList` for ``bars`` and its ``updateEvent``.

        Args:
            timer: The event that ends one bar and starts the next, emitting
                the next bar's ``datetime``.
            maxBars: Keep at most this many bars in ``bars``, dropping the
                oldest; all of them by default.
        """
        return TimeBars(timer, self, maxBars)

    def tickbars(self, count: int, maxBars: int | None = None) -> "TickBars":
        """
        Aggregate the ticks into bars of ``count`` ticks each.

        Emits each completed :class:`~ib_async.objects.RealTimeBar`; see
        :class:`BarList` for ``bars`` and its ``updateEvent``.

        Args:
            count: The number of ticks in a bar.
            maxBars: Keep at most this many bars in ``bars``, dropping the
                oldest; all of them by default.
        """
        return TickBars(count, self, maxBars)

    def volumebars(
        self, volume: Decimal | float, maxBars: int | None = None
    ) -> "VolumeBars":
        """
        Aggregate the ticks into bars of at least ``volume`` each: a bar
        completes with the tick that brings it to ``volume``, which can
        take it past (a tick is not split).

        Emits each completed :class:`~ib_async.objects.RealTimeBar`; see
        :class:`BarList` for ``bars`` and its ``updateEvent``.

        Args:
            volume: The volume of a bar.
            maxBars: Keep at most this many bars in ``bars``, dropping the
                oldest; all of them by default.
        """
        return VolumeBars(volume, self, maxBars)


@event_class
class Midpoints(Tickfilter):
    def on_source(self, ticker):
        if ticker.ticks:
            self.emit(ticker.time, ticker.midpoint(), 0)


class BarList(list[RealTimeBar]):
    """The bars of a bar operator, oldest first; the last is in progress
    until it completes.

    ``updateEvent(bars, hasNewBar)`` fires with ``hasNewBar`` False when a
    tick changes the bar in progress, and True when the last bar has just
    completed.

    Without ``maxlen`` it keeps every bar. With one, it keeps at most that
    many, as a ``deque(maxlen=...)`` does: appending a bar to a full list
    drops the oldest."""

    maxlen: int | None

    def __init__(self, *args, maxlen: int | None = None):
        if maxlen is not None and maxlen < 1:
            raise ValueError(f"maxlen keeps at least 1 bar, not {maxlen}")
        super().__init__(*args)
        self.maxlen = maxlen
        self.updateEvent = Event("updateEvent")
        self._trim()

    def append(self, bar: RealTimeBar) -> None:
        super().append(bar)
        self._trim()

    def _trim(self) -> None:
        if self.maxlen is not None and len(self) > self.maxlen:
            del self[: len(self) - self.maxlen]

    def __eq__(self, other) -> bool:
        return self is other

    def __ne__(self, other) -> bool:
        return self is not other

    # Identity-hashable to match the identity equality above (list itself
    # is unhashable, hence the override).
    def __hash__(self) -> int:  # type: ignore[override]
        return id(self)


def _decimal(value: Decimal | float) -> Decimal:
    """A float (a tick's price or size) as the Decimal it reads as."""
    return Decimal(str(value))


@dataclass(slots=True)
class _BarBuilder:
    """The bar in progress, updated in constant time per tick: its prices,
    volume and tick count, and the running sum of price × size its WAP
    (volume-weighted average price) comes from. Each :meth:`bar` is a new
    snapshot, so a bar already handed out never changes."""

    time: datetime
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

    def repeat(self, close: Decimal | None) -> None:
        """A bar without ticks: flat at ``close``, with no volume."""
        self.open = self.high = self.low = self.close = close

    def bar(self) -> RealTimeBar:
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
    a bid and ask) are skipped."""

    bars: BarList
    _builder: _BarBuilder | None
    # The close of the last completed bar, which an empty time bar repeats;
    # kept here, since a capped ``bars`` may have dropped that bar.
    _lastClose: Decimal | None

    def __init__(self, source=None, maxBars: int | None = None):
        Op.__init__(self, source)
        self.bars = BarList(maxlen=maxBars)
        self._builder = None
        self._lastClose = None

    def on_source(self, time: datetime, price: float | None, size: float | None):
        if price is None or math.isnan(price):
            return
        builder = self._builder
        if builder is None:
            if not self._startsOnTick():
                return
            builder = self._begin(time)
        quantity = Decimal(0) if size is None or math.isnan(size) else _decimal(size)
        builder.add(_decimal(price), quantity)
        self.bars[-1] = builder.bar()
        if self._isComplete(builder):
            self._complete()
        else:
            self.bars.updateEvent.emit(self.bars, False)

    def _startsOnTick(self) -> bool:
        """Whether a tick starts a bar when none is in progress."""
        return True

    def _isComplete(self, builder: _BarBuilder) -> bool:
        """Whether the bar in progress is complete after a tick."""
        return False

    def _begin(self, time: datetime) -> _BarBuilder:
        self._builder = _BarBuilder(time)
        self.bars.append(self._builder.bar())
        return self._builder

    def _complete(self) -> None:
        bar = self.bars[-1]
        self._builder = None
        self._lastClose = bar.close
        self.bars.updateEvent.emit(self.bars, True)
        self.emit(bar)


@event_class
class TimeBars(_Bars):
    __doc__ = Tickfilter.timebars.__doc__

    _timer: Event | None

    def __init__(self, timer: Event, source=None, maxBars: int | None = None):
        _Bars.__init__(self, source, maxBars)
        self._timer = timer
        self._timer.connect(self._on_timer, None, self._on_timer_done)

    def _startsOnTick(self) -> bool:
        # A time bar starts on the timer; ticks before the first are not
        # in any bar.
        return False

    def _on_timer(self, time: datetime) -> None:
        builder = self._builder
        if builder is not None:
            if builder.count == 0 and self._lastClose is not None:
                builder.repeat(self._lastClose)
                self.bars[-1] = builder.bar()
            self._complete()
        self._begin(time)

    def _on_timer_done(self, timer):
        self._timer = None
        self.set_done()


@event_class
class TickBars(_Bars):
    __doc__ = Tickfilter.tickbars.__doc__

    _count: int

    def __init__(self, count: int, source=None, maxBars: int | None = None):
        if count < 1:
            raise ValueError(f"a tick bar has at least 1 tick, not {count}")
        _Bars.__init__(self, source, maxBars)
        self._count = count

    def _isComplete(self, builder: _BarBuilder) -> bool:
        return builder.count >= self._count


@event_class
class VolumeBars(_Bars):
    __doc__ = Tickfilter.volumebars.__doc__

    _volume: Decimal

    def __init__(
        self, volume: Decimal | float, source=None, maxBars: int | None = None
    ):
        if volume <= 0:
            raise ValueError(f"a volume bar has a positive volume, not {volume}")
        _Bars.__init__(self, source, maxBars)
        self._volume = _decimal(volume)

    def _isComplete(self, builder: _BarBuilder) -> bool:
        return builder.volume >= self._volume
