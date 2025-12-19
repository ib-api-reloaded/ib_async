"""Access to realtime market information."""

import logging
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import ClassVar, Final, TypeAlias

from eventkit import Event, Op

from .contract import Contract
from .objects import (
    Dividends,
    DOMLevel,
    EfpData,
    FundamentalRatios,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    IBDefaults,
    MktDepthData,
    OptionComputation,
    TickComputationData,
    TickData,
    TickDataType,
    TickGenericData,
    TickPriceData,
    TickSizeData,
    TickStringData,
    TickType,
)
from .util import dataclassRepr, isNan, parseIBDatetime

nan = float("nan")
TickDict: TypeAlias = dict[TickType, str]


PRICE_TICK_MAP: Final[TickDict] = {
    TickType.HIGH: "high",
    TickType.DELAYED_HIGH: "high",
    TickType.LOW: "low",
    TickType.DELAYED_LOW: "low",
    TickType.CLOSE: "close",
    TickType.DELAYED_CLOSE: "close",
    TickType.OPEN: "open",
    TickType.DELAYED_OPEN: "open",
    TickType.LOW_13_WEEK: "low13week",
    TickType.HIGH_13_WEEK: "high13week",
    TickType.LOW_26_WEEK: "low26week",
    TickType.HIGH_26_WEEK: "high26week",
    TickType.LOW_52_WEEK: "low52week",
    TickType.HIGH_52_WEEK: "high52week",
    TickType.AUCTION_PRICE: "auctionPrice",
    TickType.MARK_PRICE: "markPrice",
    TickType.BID_YIELD: "bidYield",
    TickType.DELAYED_YIELD_BID: "bidYield",
    TickType.ASK_YIELD: "askYield",
    TickType.DELAYED_YIELD_ASK: "askYield",
    TickType.LAST_YIELD: "lastYield",
    TickType.LAST_RTH_TRADE: "lastRthTrade",
    TickType.CREDITMAN_MARK_PRICE: "creditmanMarkPrice",
    TickType.CREDITMAN_SLOW_MARK_PRICE: "creditmanSlowMarkPrice",
    TickType.ETF_NAV_CLOSE: "etfNavClose",
    TickType.ETF_NAV_PRIOR_CLOSE: "etfNavPriorClose",
    TickType.ETF_NAV_BID: "etfNavBid",
    TickType.ETF_NAV_ASK: "etfNavAsk",
    TickType.ETF_NAV_LAST: "etfNavLast",
    TickType.ETF_FROZEN_NAV_LAST: "etfFrozenNavLast",
    TickType.ETF_NAV_HIGH: "etfNavHigh",
    TickType.ETF_NAV_LOW: "etfNavLow",
}


SIZE_TICK_MAP: Final[TickDict] = {
    TickType.VOLUME: "volume",
    TickType.DELAYED_VOLUME: "volume",
    TickType.SHORT_TERM_VOLUME_3_MIN: "volumeRate3Min",
    TickType.SHORT_TERM_VOLUME_5_MIN: "volumeRate5Min",
    TickType.SHORT_TERM_VOLUME_10_MIN: "volumeRate10Min",
    TickType.AVG_VOLUME: "avVolume",
    TickType.OPTION_CALL_OPEN_INTEREST: "callOpenInterest",
    TickType.OPTION_PUT_OPEN_INTEREST: "putOpenInterest",
    TickType.OPTION_CALL_VOLUME: "callVolume",
    TickType.OPTION_PUT_VOLUME: "putVolume",
    TickType.AUCTION_VOLUME: "auctionVolume",
    TickType.AUCTION_IMBALANCE: "auctionImbalance",
    TickType.REGULATORY_IMBALANCE: "regulatoryImbalance",
    TickType.FUTURES_OPEN_INTEREST: "futuresOpenInterest",
    TickType.AVG_OPT_VOLUME: "avOptionVolume",
    TickType.SHORTABLE_SHARES: "shortableShares",
}

GENERIC_TICK_MAP: Final[TickDict] = {
    TickType.OPTION_HISTORICAL_VOL: "histVolatility",
    TickType.OPTION_IMPLIED_VOL: "impliedVolatility",
    TickType.INDEX_FUTURE_PREMIUM: "indexFuturePremium",
    TickType.SHORTABLE: "shortable",
    TickType.HALTED: "halted",
    TickType.DELAYED_HALTED: "halted",
    TickType.TRADE_COUNT: "tradeCount",
    TickType.TRADE_RATE: "tradeRate",
    TickType.VOLUME_RATE: "volumeRate",
    TickType.RT_HISTORICAL_VOL: "rtHistVolatility",
    TickType.BOND_FACTOR_MULTIPLIER: "bondFactorMultiplier",
    TickType.ESTIMATED_IPO_MIDPOINT: "estimatedIpoMidpoint",
    TickType.FINAL_IPO_LAST: "finalIpoLast",
}

GREEKS_TICK_MAP: Final[TickDict] = {
    TickType.BID_OPTION_COMPUTATION: "bidGreeks",
    TickType.DELAYED_BID_OPTION: "bidGreeks",
    TickType.ASK_OPTION_COMPUTATION: "askGreeks",
    TickType.DELAYED_ASK_OPTION: "askGreeks",
    TickType.LAST_OPTION_COMPUTATION: "lastGreeks",
    TickType.DELAYED_LAST_OPTION: "lastGreeks",
    TickType.MODEL_OPTION: "modelGreeks",
    TickType.DELAYED_MODEL_OPTION: "modelGreeks",
    TickType.CUST_OPTION_COMPUTATION: "custGreeks",
}

TICK_STRING_MAP: Final[TickDict] = {
    TickType.OPTION_BID_EXCH: "optionBidExch",
    TickType.OPTION_ASK_EXCH: "optionAskExch",
    TickType.BID_EXCH: "bidExchange",
    TickType.ASK_EXCH: "askExchange",
    TickType.LAST_EXCH: "lastExchange",
    TickType.LAST_REG_TIME: "lastRegTime",
}

_logger = logging.getLogger("ib_async.ticker")


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
    minTick: float = nan
    bid: float = nan
    bidSize: float = nan
    bidExchange: str = ""
    ask: float = nan
    askSize: float = nan
    askExchange: str = ""
    last: float = nan
    lastSize: float = nan
    lastExchange: str = ""
    lastTimestamp: datetime | None = None
    prevBid: float = nan
    prevBidSize: float = nan
    prevAsk: float = nan
    prevAskSize: float = nan
    prevLast: float = nan
    prevLastSize: float = nan
    volume: float = nan
    open: float = nan
    high: float = nan
    low: float = nan
    close: float = nan
    vwap: float = nan
    low13week: float = nan
    high13week: float = nan
    low26week: float = nan
    high26week: float = nan
    low52week: float = nan
    high52week: float = nan
    bidYield: float = nan
    askYield: float = nan
    lastYield: float = nan
    markPrice: float = nan
    halted: float = nan
    rtHistVolatility: float = nan
    rtVolume: float = nan
    rtTradeVolume: float = nan
    rtTime: None | datetime = None
    avVolume: float = nan
    tradeCount: float = nan
    tradeRate: float = nan
    volumeRate: float = nan
    volumeRate3Min: float = nan
    volumeRate5Min: float = nan
    volumeRate10Min: float = nan
    shortable: float = nan
    shortableShares: float = nan
    indexFuturePremium: float = nan
    futuresOpenInterest: float = nan
    putOpenInterest: float = nan
    callOpenInterest: float = nan
    putVolume: float = nan
    callVolume: float = nan
    avOptionVolume: float = nan
    optionBidExch: str = ""
    optionAskExch: str = ""
    histVolatility: float = nan
    impliedVolatility: float = nan
    dividends: None | Dividends = None
    fundamentalRatios: None | FundamentalRatios = None
    ticks: list[TickData] = field(default_factory=list)
    tickByTicks: list[HistoricalTickLast | HistoricalTickBidAsk | HistoricalTick] = (
        field(default_factory=list)
    )
    domBids: list[DOMLevel] = field(default_factory=list)
    domBidsDict: dict[int, DOMLevel] = field(default_factory=dict)
    domAsks: list[DOMLevel] = field(default_factory=list)
    domAsksDict: dict[int, DOMLevel] = field(default_factory=dict)
    domTicks: list[MktDepthData] = field(default_factory=list)
    bidGreeks: None | OptionComputation = None
    askGreeks: None | OptionComputation = None
    lastGreeks: None | OptionComputation = None
    modelGreeks: None | OptionComputation = None
    custGreeks: OptionComputation | None = None
    bidEfp: EfpData | None = None
    askEfp: EfpData | None = None
    lastEfp: EfpData | None = None
    openEfp: EfpData | None = None
    highEfp: EfpData | None = None
    lowEfp: EfpData | None = None
    closeEfp: EfpData | None = None
    auctionVolume: float = nan
    auctionPrice: float = nan
    auctionImbalance: float = nan
    regulatoryImbalance: float = nan
    bboExchange: str = ""
    snapshotPermissions: int = 0
    bondFactorMultiplier: float = nan
    creditmanMarkPrice: float = nan
    creditmanSlowMarkPrice: float = nan
    reutersMutualFunds: str = ""
    etfNavClose: float | Decimal = nan
    etfNavPriorClose: float | Decimal = nan
    etfNavBid: float | Decimal = nan
    etfNavAsk: float | Decimal = nan
    etfNavLast: float | Decimal = nan
    etfFrozenNavLast: float | Decimal = nan
    etfNavHigh: float | Decimal = nan
    etfNavLow: float | Decimal = nan
    socialMarketAnalytics: str = ""
    estimatedIpoMidpoint: float = nan
    finalIpoLast: float = nan

    defaults: IBDefaults = field(default_factory=IBDefaults, repr=False)
    created: bool = field(default=False, repr=False)
    updateEvent: Event = field(repr=False, init=False)
    ticker_bus: Event = field(repr=False, init=False)

    def __post_init__(self):
        # when copying a dataclass, the __post_init__ runs again, so we
        # want to make sure if this was _already_ created, we don't overwrite
        # everything with _another_ post_init clear.
        if not self.created:
            self.updateEvent = TickerUpdateEvent("updateEvent")
            self.ticker_bus = Event("Ticker bus")
            """ticker bus event [TickDataType,datetime|None]
            """
            self.minTick = self.defaults.unset
            self.bid = self.defaults.unset
            self.bidSize = self.defaults.unset
            self.ask = self.defaults.unset
            self.askSize = self.defaults.unset
            self.last = self.defaults.unset
            self.lastSize = self.defaults.unset
            self.prevBid = self.defaults.unset
            self.prevBidSize = self.defaults.unset
            self.prevAsk = self.defaults.unset
            self.prevAskSize = self.defaults.unset
            self.prevLast = self.defaults.unset
            self.prevLastSize = self.defaults.unset
            self.volume = self.defaults.unset
            self.open = self.defaults.unset
            self.high = self.defaults.unset
            self.low = self.defaults.unset
            self.close = self.defaults.unset
            self.vwap = self.defaults.unset
            self.low13week = self.defaults.unset
            self.high13week = self.defaults.unset
            self.low26week = self.defaults.unset
            self.high26week = self.defaults.unset
            self.low52week = self.defaults.unset
            self.high52week = self.defaults.unset
            self.bidYield = self.defaults.unset
            self.askYield = self.defaults.unset
            self.lastYield = self.defaults.unset
            self.markPrice = self.defaults.unset
            self.halted = self.defaults.unset
            self.rtHistVolatility = self.defaults.unset
            self.rtVolume = self.defaults.unset
            self.rtTradeVolume = self.defaults.unset
            self.avVolume = self.defaults.unset
            self.tradeCount = self.defaults.unset
            self.tradeRate = self.defaults.unset
            self.volumeRate = self.defaults.unset
            self.volumeRate3Min = self.defaults.unset
            self.volumeRate5Min = self.defaults.unset
            self.volumeRate10Min = self.defaults.unset
            self.shortable = self.defaults.unset
            self.shortableShares = self.defaults.unset
            self.indexFuturePremium = self.defaults.unset
            self.futuresOpenInterest = self.defaults.unset
            self.putOpenInterest = self.defaults.unset
            self.callOpenInterest = self.defaults.unset
            self.putVolume = self.defaults.unset
            self.callVolume = self.defaults.unset
            self.avOptionVolume = self.defaults.unset
            self.histVolatility = self.defaults.unset
            self.impliedVolatility = self.defaults.unset
            self.auctionVolume = self.defaults.unset
            self.auctionPrice = self.defaults.unset
            self.auctionImbalance = self.defaults.unset
            self.regulatoryImbalance = self.defaults.unset
            self.etfNavClose = self.defaults.unset
            self.etfNavPriorClose = self.defaults.unset
            self.etfNavBid = self.defaults.unset
            self.etfNavAsk = self.defaults.unset
            self.etfNavLast = self.defaults.unset
            self.etfFrozenNavLast = self.defaults.unset
            self.etfNavHigh = self.defaults.unset
            self.etfNavLow = self.defaults.unset
            self.bidExchange = self.defaults.unset
            self.askExchange = self.defaults.unset
            self.lastExchange = self.defaults.unset
            self.optionBidExch = self.defaults.unset
            self.optionAskExch = self.defaults.unset
            self.bboExchange = self.defaults.unset
            self.snapshotPermissions = self.defaults.unset
            self.bondFactorMultiplier = self.defaults.unset
            self.creditmanMarkPrice = self.defaults.unset
            self.creditmanSlowMarkPrice = self.defaults.unset
            self.reutersMutualFunds = self.defaults.unset
            self.socialMarketAnalytics = self.defaults.unset
            self.estimatedIpoMidpoint = self.defaults.unset
            self.finalIpoLast = self.defaults.unset
            self.created = True

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)

    __repr__ = dataclassRepr
    __str__ = dataclassRepr

    def _on_ticker_data(self, tick_data: TickDataType, last_time: datetime):
        """get ticker data updates and dispatch to the right handler."""
        if isinstance(tick_data, TickPriceData):
            self._on_price_tick(tick_data, last_time)
        elif isinstance(tick_data, TickSizeData):
            self._on_size_tick(tick_data, last_time)
        elif isinstance(tick_data, TickStringData):
            self._on_tick_string(tick_data, last_time)
        elif isinstance(tick_data, TickGenericData):
            self._on_tick_generic(tick_data, last_time)
        elif isinstance(tick_data, TickComputationData):
            self._on_opt_computation(tick_data)
        elif isinstance(tick_data, HistoricalTickLast):
            self._on_tick_last(tick_data)
        elif isinstance(tick_data, HistoricalTickBidAsk):
            self._on_tick_bidask(tick_data)
        elif isinstance(tick_data, HistoricalTick):
            self._on_tick_midpoint(tick_data)
        else:
            _logger.error("Ticker %s. Unknown tick data: %s", self.contract, tick_data)

    def _on_price_tick(self, tick_price: TickPriceData, last_time: datetime):
        price = tick_price.price
        size = tick_price.size

        # https://interactivebrokers.github.io/tws-api/tick_types.html
        if tick_price.tickType in {TickType.BID, TickType.DELAYED_BID}:
            # Note: Keep these size==0 overrides INSIDE each tickType where it is
            # needed because other tickTypes like open/high/low/close are values with
            # size=0 but those are still valid prices to receive.
            # Bid/Ask updates always have a Price+Size delivered at the same time,
            # while the other properties are mainly price-only delivery methods.
            if tick_price.size == 0:
                price = self.defaults.emptyPrice
                size = self.defaults.emptySize

            self.prevBid = self.bid
            self.prevBidSize = self.bidSize
            self.bid = price
            self.bidSize = size
        elif tick_price.tickType in {TickType.ASK, TickType.DELAYED_ASK}:
            if tick_price.size == 0:
                price = self.defaults.emptyPrice
                size = self.defaults.emptySize

            self.prevAsk = self.ask
            self.prevAskSize = self.askSize
            self.ask = price
            self.askSize = size
        elif tick_price.tickType in {TickType.LAST, TickType.DELAYED_LAST}:
            # for 'last' values, price can be valid with size=0 for updates like 'last
            # SPX price' since SPX doesn't trade
            # Workaround: for TICK-NYSE, it is valid to have price=-1, size=0 because
            # it can float between -10,000 and 10,000
            # and it also never reports a size. As a workaround, check if
            # ticker.close exists as a proxy for "not TICK-NYSE"
            # because TICK-NYSE never has open/close values populated.
            if tick_price.price == -1 and tick_price.size == 0 and self.close > 0:
                price = self.defaults.emptyPrice
                size = self.defaults.emptyPrice

            # BUG? IBKR is sometimes sending a GOOD VALUE followed by a PREVIOUS value
            # all under tickType=4?
            # e.g. I get the SPX close delivered first with size=0, then I get another
            # data point with size=1 priced one point lower,
            # but since the older price is delivered second, it replaces the "last"
            # value with a wrong value? Not sure if it's
            # an IBKR data problem or a logic problem somewhere here?
            # More research: IBKR also shows the bad value in their own app, so there
            # is a data bug in their own server logic somewhere.

            self.prevLast = self.last
            self.prevLastSize = self.lastSize
            self.last = price
            self.lastSize = size

        else:
            assert tick_price.tickType in PRICE_TICK_MAP, (
                f"Received tick {tick_price.tickType=} {tick_price.price=} but we don't"
                f" have an attribute mapping for it? Triggered from {self.contract=}"
            )

            setattr(self, PRICE_TICK_MAP[tick_price.tickType], tick_price.price)

        if price or size:
            tick = TickData(
                last_time, tick_price.tickType, tick_price.price, tick_price.size
            )
            self.ticks.append(tick)

    def _on_size_tick(self, tick_size: TickSizeData, last_time: datetime):
        price = self.defaults.emptyPrice

        # https://interactivebrokers.github.io/tws-api/tick_types.html
        if tick_size.tickType in {
            TickType.BID_SIZE,
            TickType.DELAYED_BID_SIZE,
        }:
            if tick_size.size == self.bidSize:
                return

            self.prevBidSize = self.bidSize
            if tick_size.size == 0:
                self.bid = self.defaults.emptyPrice
                self.bidSize = self.defaults.emptySize
            else:
                price = self.bid
                self.bidSize = tick_size.size
        elif tick_size.tickType in {
            TickType.ASK_SIZE,
            TickType.DELAYED_ASK_SIZE,
        }:
            if tick_size.size == self.askSize:
                return

            self.prevAskSize = self.askSize
            if tick_size.size == 0:
                self.ask = self.defaults.emptyPrice
                self.askSize = self.defaults.emptySize
            else:
                price = self.ask
                self.askSize = tick_size.size
        elif tick_size.tickType in {
            TickType.LAST_SIZE,
            TickType.DELAYED_LAST_SIZE,
        }:
            price = self.last

            if self.isUnset(price):
                return

            if tick_size.size != self.lastSize:
                self.prevLastSize = self.lastSize
                self.lastSize = tick_size.size
        else:
            assert tick_size.tickType in SIZE_TICK_MAP, (
                f"Received tick {tick_size.tickType=} {tick_size.size=} but we don't"
                f" have an attribute mapping for it? Triggered from {self.contract=}"
            )

            setattr(self, SIZE_TICK_MAP[tick_size.tickType], tick_size.size)

        if price or tick_size.size:
            tick = TickData(last_time, tick_size.tickType, price, tick_size.size)
            self.ticks.append(tick)

    def _on_tick_string(self, tick_string: TickStringData, last_time: datetime):
        try:
            if tick_string.tickType in TICK_STRING_MAP:
                setattr(self, TICK_STRING_MAP[tick_string.tickType], tick_string.value)
            elif tick_string.tickType in {
                TickType.LAST_TIMESTAMP,
                TickType.DELAYED_LAST_TIMESTAMP,
            }:
                timestamp = int(tick_string.value)

                # only populate if timestamp isn't '0' (we don't want to report "last
                # trade: 20,000 days ago")
                if timestamp:
                    self.lastTimestamp = datetime.fromtimestamp(
                        timestamp, self.defaults.timezone
                    )
            elif tick_string.tickType == TickType.FUNDAMENTAL_RATIOS:
                # https://web.archive.org/web/20200725010343/https://interactivebrokers.github.io/tws-api/fundamental_ratios_tags.html
                d = dict(
                    t.split("=")
                    for t in tick_string.value.split(";")
                    if t  # type: ignore
                )  # type: ignore
                for k, v in d.items():
                    with suppress(ValueError):
                        if v == "-99999.99":
                            v = "nan"
                        d[k] = float(v)  # type: ignore
                        # TODO - WTF? https://github.com/ib-api-reloaded/ib_async/blob/2afdae44a47f067bf3d1a23a4840234f2906ef64/ib_async/wrapper.py#L1135
                        # d[k] = int(v)  # type: ignore
                self.fundamentalRatios = FundamentalRatios(**d)
            elif tick_string.tickType in {TickType.RT_VOLUME, TickType.RT_TRD_VOLUME}:
                # RT Volume or RT Trade Volume string format:
                # price;size;ms since epoch;total volume;VWAP;single trade
                # example:
                # 701.28;1;1348075471534;67854;701.46918464;true
                priceStr, sizeStr, rtTime, volume, vwap, _ = tick_string.value.split(
                    ";"
                )
                if volume:
                    if tick_string.tickType == TickType.RT_VOLUME:
                        self.rtVolume = float(volume)
                    elif tick_string.tickType == TickType.RT_TRD_VOLUME:
                        self.rtTradeVolume = float(volume)

                if vwap:
                    self.vwap = float(vwap)

                if rtTime:
                    self.rtTime = datetime.fromtimestamp(
                        int(rtTime) / 1000, self.defaults.timezone
                    )

                if priceStr == "":
                    return

                price = float(priceStr)
                size = float(sizeStr)

                self.prevLast = self.last
                self.prevLastSize = self.lastSize

                self.last = price
                self.lastSize = size

                tick = TickData(last_time, tick_string.tickType, price, size)
                self.ticks.append(tick)
            elif tick_string.tickType == TickType.IB_DIVIDENDS:
                # Dividend tick:
                # https://interactivebrokers.github.io/tws-api/tick_types.html#ib_dividends
                # example value: '0.83,0.92,20130219,0.23'
                past12, next12, nextDate, nextAmount = tick_string.value.split(",")
                self.dividends = Dividends(
                    float(past12) if past12 else None,
                    float(next12) if next12 else None,
                    parseIBDatetime(nextDate) if nextDate else None,
                    float(nextAmount) if nextAmount else None,
                )
            else:
                _logger.error(
                    f"tickString with tickType {tick_string.tickType}: unhandled value: {tick_string.value!r}"
                )

        except ValueError:
            _logger.error(
                f"tickString with tickType {tick_string.tickType}: malformed value: {tick_string.value!r}"
            )

    def _on_tick_generic(self, tick_generic: TickGenericData, last_time: datetime):
        try:
            value = float(tick_generic.value)
            value = value if value > 0 else self.defaults.emptySize
        except ValueError:
            _logger.error(
                f"[tickType {tick_generic.tickType}] genericTick: malformed value: {value!r}"
            )
            return

        assert tick_generic.tickType in GENERIC_TICK_MAP, (
            f"Received tick {tick_generic.tickType=} {value=} but we don't have an"
            f" attribute mapping for it? Triggered from {self.contract=}"
        )

        setattr(self, GENERIC_TICK_MAP[tick_generic.tickType], value)

        tick = TickData(last_time, tick_generic.tickType, value, 0)
        self.ticks.append(tick)

    def _on_opt_computation(self, tick_computation: TickComputationData):
        assert tick_computation.tickType in GREEKS_TICK_MAP, (
            f"Received tick {tick_computation.tickType=} "
            f"{tick_computation.computation.tickAttrib=} but we don't"
            f" have an attribute mapping for it? Triggered from {self.contract=}"
        )
        setattr(
            self,
            GREEKS_TICK_MAP[tick_computation.tickType],
            tick_computation.computation,
        )

    def _on_tick_last(self, historicalTickLast: HistoricalTickLast):
        if historicalTickLast.price == -1 and historicalTickLast.size == 0:
            price = self.defaults.emptyPrice
            size = self.defaults.emptySize
        else:
            price = historicalTickLast.price
            size = historicalTickLast.size

        self.prevLast = self.last
        self.prevLastSize = self.lastSize
        self.last = price
        self.lastSize = size

        self.tickByTicks.append(historicalTickLast)

    def _on_tick_bidask(self, historicalTickBidAsk: HistoricalTickBidAsk):
        if historicalTickBidAsk.priceBid != self.bid:
            self.prevBid = self.bid
            self.bid = (
                historicalTickBidAsk.priceBid
                if historicalTickBidAsk.priceBid > 0
                else self.defaults.emptyPrice
            )

        if historicalTickBidAsk.sizeBid != self.bidSize:
            self.prevBidSize = self.bidSize
            self.bidSize = (
                historicalTickBidAsk.sizeBid
                if historicalTickBidAsk.sizeBid > 0
                else self.defaults.emptySize
            )

        if historicalTickBidAsk.priceAsk != self.ask:
            self.prevAsk = self.ask
            self.ask = (
                historicalTickBidAsk.priceAsk
                if historicalTickBidAsk.priceAsk > 0
                else self.defaults.emptyPrice
            )

        if historicalTickBidAsk.sizeAsk != self.askSize:
            self.prevAskSize = self.askSize
            self.askSize = (
                historicalTickBidAsk.sizeAsk
                if historicalTickBidAsk.sizeAsk > 0
                else self.defaults.emptySize
            )

        self.tickByTicks.append(historicalTickBidAsk)

    def _on_tick_midpoint(self, historicalTickMidPoint: HistoricalTick):
        self.tickByTicks.append(historicalTickMidPoint)

    def isUnset(self, value) -> bool:
        # if default value is nan and value is nan, it is unset.
        # else, if value matches default value, it is unset.
        dev = self.defaults.unset
        return (dev != dev and value != value) or (value == dev)

    def hasBidAsk(self) -> bool:
        """See if this ticker has a valid bid and ask."""
        return (
            self.bid != -1
            and not self.isUnset(self.bid)
            and self.bidSize > 0
            and self.ask != -1
            and not self.isUnset(self.ask)
            and self.askSize > 0
        )

    def midpoint(self) -> float:
        """
        Return average of bid and ask, or defaults.unset if no valid bid and ask
        are available.
        """
        return (self.bid + self.ask) * 0.5 if self.hasBidAsk() else self.defaults.unset

    def marketPrice(self) -> float:
        """
        Return the first available one of

        * last price if within current bid/ask or no bid/ask available;
        * average of bid and ask (midpoint).
        """
        if self.hasBidAsk():
            if self.bid <= self.last <= self.ask:
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
        return Tickfilter(
            (
                TickType.LAST,
                TickType.LAST_SIZE,
                TickType.RT_VOLUME,
                TickType.DELAYED_LAST,
                TickType.DELAYED_LAST_SIZE,
            ),
            self,
        )

    def bids(self) -> "Tickfilter":
        """Emit bid ticks."""
        return Tickfilter(
            (
                TickType.BID_SIZE,
                TickType.BID,
                TickType.DELAYED_BID,
                TickType.DELAYED_BID_SIZE,
            ),
            self,
        )

    def asks(self) -> "Tickfilter":
        """Emit ask ticks."""
        return Tickfilter(
            (
                TickType.ASK,
                TickType.ASK_SIZE,
                TickType.DELAYED_ASK,
                TickType.DELAYED_ASK_SIZE,
            ),
            self,
        )

    def bidasks(self) -> "Tickfilter":
        """Emit bid and ask ticks."""
        return Tickfilter(
            (
                TickType.BID_SIZE,
                TickType.BID,
                TickType.DELAYED_BID,
                TickType.DELAYED_BID_SIZE,
                TickType.ASK,
                TickType.ASK_SIZE,
                TickType.DELAYED_ASK,
                TickType.DELAYED_ASK_SIZE,
            ),
            self,
        )

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
    time: None | datetime
    open: float = nan
    high: float = nan
    low: float = nan
    close: float = nan
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

        if isNan(bar.open):
            bar.open = bar.high = bar.low = price

        bar.high = max(bar.high, price)
        bar.low = min(bar.low, price)
        bar.close = price
        bar.volume += size
        bar.count += 1
        self.bars.updateEvent.emit(self.bars, False)

    def _on_timer(self, time):
        if self.bars:
            bar = self.bars[-1]
            if isNan(bar.close) and len(self.bars) > 1:
                bar.open = bar.high = bar.low = bar.close = self.bars[-2].close

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
