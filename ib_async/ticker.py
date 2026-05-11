"""Access to realtime market information."""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar

from eventkit import Event, Op

from ib_async.contract import Contract
from ib_async.objects import (
    Dividends,
    DOMLevel,
    EfpData,
    FundamentalRatios,
    IBDefaults,
    MktDepthData,
    NewsTick,
    OptionComputation,
    TickAttrib,
    TickByTickAllLast,
    TickByTickBidAsk,
    TickByTickMidPoint,
    TickData,
)
from ib_async.util import dataclassRepr

# Bounded ring of most-recent per-contract news ticks. NewsTick already
# fans out through ``IB.tickNewsEvent`` for streaming consumers; this
# deque is the snapshot view a holder of a Ticker reference can read
# without their own subscriber bookkeeping. Sized for the eyeball
# "what's recent for this name" case; raise via ``Ticker.news.maxlen``
# replacement if a strategy needs longer retention.
_NEWS_MAXLEN: int = 5


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
    :class:`.DOMLevel` in ``domBids`` and ``domAsks``.

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
    halted: float | None = None
    rtHistVolatility: float | None = None
    rtVolume: float | None = None
    rtTradeVolume: float | None = None
    rtTime: datetime | None = None
    avVolume: float | None = None
    tradeCount: float | None = None
    tradeRate: float | None = None
    volumeRate: float | None = None
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
    delayedHalted: float | None = None
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
    fundamentalRatios: FundamentalRatios | None = None
    ticks: list[TickData] = field(default_factory=list)
    tickByTicks: list[TickByTickAllLast | TickByTickBidAsk | TickByTickMidPoint] = (
        field(default_factory=list)
    )
    domBids: list[DOMLevel] = field(default_factory=list)
    domBidsDict: dict[int, DOMLevel] = field(default_factory=dict)
    domAsks: list[DOMLevel] = field(default_factory=list)
    domAsksDict: dict[int, DOMLevel] = field(default_factory=dict)
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

    def __hash__(self):
        return id(self)

    __repr__ = dataclassRepr
    __str__ = dataclassRepr

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


class TickerUpdateEvent(Event):
    __slots__ = ()

    def trades(self) -> "Tickfilter":
        """Emit trade ticks."""
        return Tickfilter((4, 5, 48, 68, 71), self)

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


class Tickfilter(Op):
    """Tick filtering event operators that ``emit(time, price, size)``."""

    __slots__ = ("_tickTypes",)

    def __init__(self, tickTypes, source=None):
        Op.__init__(self, source)
        self._tickTypes = set(tickTypes)

    def on_source(self, ticker):
        for t in ticker.ticks:
            if t.tickType in self._tickTypes:
                self.emit(t.time, t.price, t.size)

    def timebars(self, timer: Event) -> "TimeBars":
        """
        Aggregate ticks into time bars, where the timing of new bars
        is derived from a timer event.
        Emits a completed :class:`Bar`.

        This event stores a :class:`BarList` of all created bars in the
        ``bars`` property.

        Args:
            timer: Event for timing when a new bar starts.
        """
        return TimeBars(timer, self)

    def tickbars(self, count: int) -> "TickBars":
        """
        Aggregate ticks into bars that have the same number of ticks.
        Emits a completed :class:`Bar`.

        This event stores a :class:`BarList` of all created bars in the
        ``bars`` property.

        Args:
            count: Number of ticks to use to form one bar.
        """
        return TickBars(count, self)

    def volumebars(self, volume: int) -> "VolumeBars":
        """
        Aggregate ticks into bars that have the same volume.
        Emits a completed :class:`Bar`.

        This event stores a :class:`BarList` of all created bars in the
        ``bars`` property.

        Args:
            count: Number of ticks to use to form one bar.
        """
        return VolumeBars(volume, self)


class Midpoints(Tickfilter):
    __slots__ = ()

    def on_source(self, ticker):
        if ticker.ticks:
            self.emit(ticker.time, ticker.midpoint(), 0)


@dataclass
class Bar:
    time: datetime | None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int = 0
    count: int = 0


class BarList(list[Bar]):
    def __init__(self, *args):
        super().__init__(*args)
        self.updateEvent = Event("updateEvent")

    def __eq__(self, other) -> bool:
        return self is other


class TimeBars(Op):
    __slots__ = (
        "_timer",
        "bars",
    )
    __doc__ = Tickfilter.timebars.__doc__

    bars: BarList

    def __init__(self, timer, source=None):
        Op.__init__(self, source)
        self._timer = timer
        self._timer.connect(self._on_timer, None, self._on_timer_done)
        self.bars = BarList()

    def on_source(self, time, price, size):
        if not self.bars:
            return
        bar = self.bars[-1]

        if bar.open is None:
            bar.open = bar.high = bar.low = price

        if bar.high is not None:
            bar.high = max(bar.high, price)
        else:
            bar.high = price
        if bar.low is not None:
            bar.low = min(bar.low, price)
        else:
            bar.low = price
        bar.close = price
        bar.volume += size
        bar.count += 1
        self.bars.updateEvent.emit(self.bars, False)

    def _on_timer(self, time):
        if self.bars:
            bar = self.bars[-1]
            if bar.close is None and len(self.bars) > 1:
                prev_close = self.bars[-2].close
                bar.open = bar.high = bar.low = bar.close = prev_close

            self.bars.updateEvent.emit(self.bars, True)
            self.emit(bar)

        self.bars.append(Bar(time))

    def _on_timer_done(self, timer):
        self._timer = None
        self.set_done()


class TickBars(Op):
    __slots__ = ("_count", "bars")
    __doc__ = Tickfilter.tickbars.__doc__

    bars: BarList

    def __init__(self, count, source=None):
        Op.__init__(self, source)
        self._count = count
        self.bars = BarList()

    def on_source(self, time, price, size):
        if not self.bars or self.bars[-1].count == self._count:
            bar = Bar(time, price, price, price, price, size, 1)
            self.bars.append(bar)
        else:
            bar = self.bars[-1]
            bar.high = max(bar.high, price)
            bar.low = min(bar.low, price)
            bar.close = price
            bar.volume += size
            bar.count += 1
        if bar.count == self._count:
            self.bars.updateEvent.emit(self.bars, True)
            self.emit(self.bars)


class VolumeBars(Op):
    __slots__ = ("_volume", "bars")
    __doc__ = Tickfilter.volumebars.__doc__

    bars: BarList

    def __init__(self, volume, source=None):
        Op.__init__(self, source)
        self._volume = volume
        self.bars = BarList()

    def on_source(self, time, price, size):
        if not self.bars or self.bars[-1].volume >= self._volume:
            bar = Bar(time, price, price, price, price, size, 1)
            self.bars.append(bar)
        else:
            bar = self.bars[-1]
            bar.high = max(bar.high, price)
            bar.low = min(bar.low, price)
            bar.close = price
            bar.volume += size
            bar.count += 1
        if bar.volume >= self._volume:
            self.bars.updateEvent.emit(self.bars, True)
            self.emit(self.bars)
