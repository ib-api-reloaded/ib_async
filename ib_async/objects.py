"""Object hierarchy."""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date as date_
from datetime import datetime, timezone, tzinfo
from enum import Enum
from typing import TYPE_CHECKING, Any, List, NamedTuple, Optional, TypeAlias, Union

if TYPE_CHECKING:
    from ib_async import IB


from eventkit import Event

from .contract import Contract, ScanData, TagValue
from .util import EPOCH, UNSET_DOUBLE, UNSET_INTEGER

nan = float("nan")


class OptionExerciseType(Enum):
    NoneItem = (-1, "None")
    Exercise = (1, "Exercise")
    Lapse = (2, "Lapse")
    DoNothing = (3, "DoNothing")
    Assigned = (100, "Assigned ")
    AutoexerciseClearing = (101, "AutoexerciseClearing")
    Expired = (102, "Expired")
    Netting = (103, "Netting")
    AutoexerciseTrading = (200, "AutoexerciseTrading")


@dataclass
class ScannerSubscription:
    numberOfRows: int = -1
    instrument: str = ""
    locationCode: str = ""
    scanCode: str = ""
    abovePrice: float = UNSET_DOUBLE
    belowPrice: float = UNSET_DOUBLE
    aboveVolume: int = UNSET_INTEGER
    marketCapAbove: float = UNSET_DOUBLE
    marketCapBelow: float = UNSET_DOUBLE
    moodyRatingAbove: str = ""
    moodyRatingBelow: str = ""
    spRatingAbove: str = ""
    spRatingBelow: str = ""
    maturityDateAbove: str = ""
    maturityDateBelow: str = ""
    couponRateAbove: float = UNSET_DOUBLE
    couponRateBelow: float = UNSET_DOUBLE
    excludeConvertible: bool = False
    averageOptionVolumeAbove: int = UNSET_INTEGER
    scannerSettingPairs: str = ""
    stockTypeFilter: str = ""


@dataclass
class SoftDollarTier:
    name: str = ""
    val: str = ""
    displayName: str = ""

    def __bool__(self):
        return bool(self.name or self.val or self.displayName)


@dataclass(slots=True)
class Execution:
    execId: str = ""
    time: datetime = field(default=EPOCH)
    acctNumber: str = ""
    exchange: str = ""
    side: str = ""
    shares: float = 0.0
    price: float = 0.0
    permId: int = 0
    clientId: int = 0
    orderId: int = 0
    liquidation: int = 0
    cumQty: float = 0.0
    avgPrice: float = 0.0
    orderRef: str = ""
    evRule: str = ""
    evMultiplier: float = 0.0
    modelCode: str = ""
    lastLiquidity: int = 0
    pendingPriceRevision: bool = False
    submitter: str = ""
    optExerciseOrLapseType: OptionExerciseType = field(
        default=OptionExerciseType.NoneItem
    )


@dataclass(slots=True)
class CommissionReport:
    execId: str = ""
    commission: float = 0.0
    currency: str = ""
    realizedPNL: float = 0.0
    yield_: float = 0.0
    yieldRedemptionDate: int = 0


@dataclass(slots=True)
class ExecutionFilter:
    clientId: int = 0
    acctCode: str = ""
    time: str = ""
    symbol: str = ""
    secType: str = ""
    exchange: str = ""
    side: str = ""
    lastNDays: int = UNSET_INTEGER
    specificDates: list[int] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class BarData:
    date: Union[date_, datetime] = EPOCH
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0
    average: float = 0.0
    barCount: int = 0


@dataclass(slots=True, frozen=True)
class RealTimeBar:
    time: datetime = EPOCH
    endTime: int = -1
    open_: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: float = 0.0
    wap: float = 0.0
    count: int = 0


@dataclass(slots=True, frozen=True)
class OptionComputation:
    tickAttrib: int
    impliedVol: float | None = None
    delta: float | None = None
    optPrice: float | None = None
    pvDividend: float | None = None
    gamma: float | None = None
    vega: float | None = None
    theta: float | None = None
    undPrice: float | None = None

    def __add__(self, other: OptionComputation) -> OptionComputation:
        if not isinstance(other, self.__class__):
            raise TypeError(f"Cannot add {type(self)} and {type(other)}")

        return self.__class__(
            tickAttrib=0,
            impliedVol=(self.impliedVol or 0) + (other.impliedVol or 0),
            delta=(self.delta or 0) + (other.delta or 0),
            optPrice=(self.optPrice or 0) + (other.optPrice or 0),
            gamma=(self.gamma or 0) + (other.gamma or 0),
            vega=(self.vega or 0) + (other.vega or 0),
            theta=(self.theta or 0) + (other.theta or 0),
            undPrice=self.undPrice,
        )

    def __sub__(self, other: OptionComputation) -> OptionComputation:
        if not isinstance(other, self.__class__):
            raise TypeError(f"Cannot subtract {type(self)} and {type(other)}")

        return self.__class__(
            tickAttrib=0,
            impliedVol=(self.impliedVol or 0) - (other.impliedVol or 0),
            delta=(self.delta or 0) - (other.delta or 0),
            optPrice=(self.optPrice or 0) - (other.optPrice or 0),
            gamma=(self.gamma or 0) - (other.gamma or 0),
            vega=(self.vega or 0) - (other.vega or 0),
            theta=(self.theta or 0) - (other.theta or 0),
            undPrice=self.undPrice,
        )

    def __mul__(self, other: int | float) -> OptionComputation:
        if not isinstance(other, (int, float)):
            raise TypeError(f"Cannot multiply {type(self)} and {type(other)}")

        return self.__class__(
            tickAttrib=0,
            impliedVol=(self.impliedVol or 0) * other,
            delta=(self.delta or 0) * other,
            optPrice=(self.optPrice or 0) * other,
            gamma=(self.gamma or 0) * other,
            vega=(self.vega or 0) * other,
            theta=(self.theta or 0) * other,
            undPrice=self.undPrice,
        )


class TickType(Enum):
    BID_SIZE = 0
    BID = 1
    ASK = 2
    ASK_SIZE = 3
    LAST = 4
    LAST_SIZE = 5
    HIGH = 6
    LOW = 7
    VOLUME = 8
    CLOSE = 9
    BID_OPTION_COMPUTATION = 10
    ASK_OPTION_COMPUTATION = 11
    LAST_OPTION_COMPUTATION = 12
    MODEL_OPTION = 13
    OPEN = 14
    LOW_13_WEEK = 15
    HIGH_13_WEEK = 16
    LOW_26_WEEK = 17
    HIGH_26_WEEK = 18
    LOW_52_WEEK = 19
    HIGH_52_WEEK = 20
    AVG_VOLUME = 21
    OPEN_INTEREST = 22
    OPTION_HISTORICAL_VOL = 23
    OPTION_IMPLIED_VOL = 24
    OPTION_BID_EXCH = 25
    OPTION_ASK_EXCH = 26
    OPTION_CALL_OPEN_INTEREST = 27
    OPTION_PUT_OPEN_INTEREST = 28
    OPTION_CALL_VOLUME = 29
    OPTION_PUT_VOLUME = 30
    INDEX_FUTURE_PREMIUM = 31
    BID_EXCH = 32
    ASK_EXCH = 33
    AUCTION_VOLUME = 34
    AUCTION_PRICE = 35
    AUCTION_IMBALANCE = 36
    MARK_PRICE = 37
    BID_EFP_COMPUTATION = 38
    ASK_EFP_COMPUTATION = 39
    LAST_EFP_COMPUTATION = 40
    OPEN_EFP_COMPUTATION = 41
    HIGH_EFP_COMPUTATION = 42
    LOW_EFP_COMPUTATION = 43
    CLOSE_EFP_COMPUTATION = 44
    LAST_TIMESTAMP = 45
    SHORTABLE = 46
    FUNDAMENTAL_RATIOS = 47
    RT_VOLUME = 48
    HALTED = 49
    BID_YIELD = 50
    ASK_YIELD = 51
    LAST_YIELD = 52
    CUST_OPTION_COMPUTATION = 53
    TRADE_COUNT = 54
    TRADE_RATE = 55
    VOLUME_RATE = 56
    LAST_RTH_TRADE = 57
    RT_HISTORICAL_VOL = 58
    IB_DIVIDENDS = 59
    BOND_FACTOR_MULTIPLIER = 60
    REGULATORY_IMBALANCE = 61
    NEWS_TICK = 62
    SHORT_TERM_VOLUME_3_MIN = 63
    SHORT_TERM_VOLUME_5_MIN = 64
    SHORT_TERM_VOLUME_10_MIN = 65
    DELAYED_BID = 66
    DELAYED_ASK = 67
    DELAYED_LAST = 68
    DELAYED_BID_SIZE = 69
    DELAYED_ASK_SIZE = 70
    DELAYED_LAST_SIZE = 71
    DELAYED_HIGH = 72
    DELAYED_LOW = 73
    DELAYED_VOLUME = 74
    DELAYED_CLOSE = 75
    DELAYED_OPEN = 76
    RT_TRD_VOLUME = 77
    CREDITMAN_MARK_PRICE = 78
    CREDITMAN_SLOW_MARK_PRICE = 79
    DELAYED_BID_OPTION = 80
    DELAYED_ASK_OPTION = 81
    DELAYED_LAST_OPTION = 82
    DELAYED_MODEL_OPTION = 83
    LAST_EXCH = 84
    LAST_REG_TIME = 85
    FUTURES_OPEN_INTEREST = 86
    AVG_OPT_VOLUME = 87
    DELAYED_LAST_TIMESTAMP = 88
    SHORTABLE_SHARES = 89
    DELAYED_HALTED = 90
    REUTERS_2_MUTUAL_FUNDS = 91
    ETF_NAV_CLOSE = 92
    ETF_NAV_PRIOR_CLOSE = 93
    ETF_NAV_BID = 94
    ETF_NAV_ASK = 95
    ETF_NAV_LAST = 96
    ETF_FROZEN_NAV_LAST = 97
    ETF_NAV_HIGH = 98
    ETF_NAV_LOW = 99
    SOCIAL_MARKET_ANALYTICS = 100
    ESTIMATED_IPO_MIDPOINT = 101
    FINAL_IPO_LAST = 102
    DELAYED_YIELD_BID = 103
    DELAYED_YIELD_ASK = 104
    NOT_SET = 105


@dataclass(slots=True, frozen=True)
class TickParams:
    reqId: int
    minTick: float
    bboExchange: str
    snapshotPermissions: int


@dataclass(slots=True, frozen=True)
class TickData:
    """For Ticker.ticks[TickData]"""

    time: datetime
    tickType: TickType
    price: float
    size: float


@dataclass(slots=True)
class TickAttrib:
    canAutoExecute: bool = False
    pastLimit: bool = False
    preOpen: bool = False


@dataclass(slots=True)
class TickAttribBidAsk:
    bidPastLow: bool = False
    askPastHigh: bool = False


@dataclass(slots=True)
class TickAttribLast:
    pastLimit: bool = False
    unreported: bool = False


@dataclass(slots=True, frozen=True)
class TickPriceData:
    """Data from a TickPriceProto message."""

    reqId: int
    tickType: TickType
    price: float
    size: float
    attribs: TickAttrib


@dataclass(slots=True, frozen=True)
class TickSizeData:
    """Data from a TickSizeProto message."""

    reqId: int
    tickType: TickType
    size: float


@dataclass(slots=True, frozen=True)
class TickStringData:
    """Data from a TickStringProto message."""

    reqId: int
    tickType: TickType
    value: str


@dataclass(slots=True, frozen=True)
class TickGenericData:
    """Data from a generic tick message."""

    reqId: int
    tickType: TickType
    value: float


@dataclass(slots=True, frozen=True)
class TickComputationData:
    """Data from a TickComputationProto message."""

    reqId: int
    tickType: TickType
    computation: OptionComputation


@dataclass(slots=True, frozen=True)
class TickByTickAllLastData:
    """Data from a TickByTickAllLastProto message."""

    reqId: int
    tickType: int
    time: int
    price: float
    size: int
    tickAttribLast: TickAttribLast
    exchange: str
    specialConditions: str


@dataclass(slots=True, frozen=True)
class TickByTickBidAskData:
    """Data from a TickByTickBidAskProto message."""

    reqId: int
    time: int
    bidPrice: float
    askPrice: float
    bidSize: int
    askSize: int
    tickAttribBidAsk: TickAttribBidAsk


@dataclass(slots=True, frozen=True)
class TickByTickMidPointData:
    """Data from a TickByTickMidPointProto message."""

    reqId: int
    time: int
    midPoint: float


TickDataType: TypeAlias = (
    TickPriceData
    | TickSizeData
    | TickStringData
    | TickGenericData
    | TickByTickAllLastData
    | TickByTickBidAskData
    | TickByTickMidPointData
    | TickComputationData
)


@dataclass(slots=True)
class HistogramData:
    price: float = 0.0
    count: int = 0


@dataclass(slots=True)
class NewsProvider:
    code: str = ""
    name: str = ""


@dataclass
class DepthMktDataDescription:
    exchange: str = ""
    secType: str = ""
    listingExch: str = ""
    serviceDataType: str = ""
    aggGroup: int = UNSET_INTEGER


@dataclass(slots=True)
class PnL:
    account: str = ""
    modelCode: str = ""
    dailyPnL: float = nan
    unrealizedPnL: float = nan
    realizedPnL: float = nan

    def getKey(self):
        """return PnL key
        ie: ib.cancelPnL(pnl.getKey())
        """
        return (self.account, self.modelCode)


@dataclass(slots=True)
class TradeLogEntry:
    time: datetime
    status: str = ""
    message: str = ""
    errorCode: int = 0


@dataclass(slots=True)
class PnLSingle:
    account: str = ""
    modelCode: str = ""
    conId: int = 0
    dailyPnL: float = nan
    unrealizedPnL: float = nan
    realizedPnL: float = nan
    position: int = 0
    value: float = nan

    def getKey(self):
        """return PnLSingle key
        ie: ib.cancelPnLSingle(pnl_single.getKey())
        """
        return (self.account, self.modelCode, self.conId)


@dataclass(slots=True, frozen=True)
class HistoricalSession:
    startDateTime: str = ""
    endDateTime: str = ""
    refDate: str = ""


@dataclass(slots=True, frozen=True)
class HistoricalSchedule:
    startDateTime: str = ""
    endDateTime: str = ""
    timeZone: str = ""
    sessions: List[HistoricalSession] = field(default_factory=list)


@dataclass
class WshEventData:
    conId: int = UNSET_INTEGER
    filter: str = ""
    fillWatchlist: bool = False
    fillPortfolio: bool = False
    fillCompetitors: bool = False
    startDate: str = ""
    endDate: str = ""
    totalLimit: int = UNSET_INTEGER


class AccountValue(NamedTuple):
    account: str
    tag: str
    value: str
    currency: str
    modelCode: str


@dataclass(slots=True)
class HistoricalTick:
    time: datetime
    price: float
    size: float


@dataclass(slots=True)
class HistoricalTickBidAsk:
    time: datetime
    tickAttribBidAsk: TickAttribBidAsk
    priceBid: float
    priceAsk: float
    sizeBid: float
    sizeAsk: float


@dataclass(slots=True, frozen=True)
class HistoricalTickLast:
    time: datetime
    tickAttribLast: TickAttribLast
    price: float
    size: float
    exchange: str
    specialConditions: str


class TickByTickAllLast(NamedTuple):
    tickType: int
    time: datetime
    price: float
    size: float
    tickAttribLast: TickAttribLast
    exchange: str
    specialConditions: str


class TickByTickBidAsk(NamedTuple):
    time: datetime
    bidPrice: float
    askPrice: float
    bidSize: float
    askSize: float
    tickAttribBidAsk: TickAttribBidAsk


class TickByTickMidPoint(NamedTuple):
    time: datetime
    midPoint: float


class MktDepthData(NamedTuple):
    time: datetime
    position: int
    marketMaker: str
    operation: int
    side: int
    price: float
    size: float


class DOMLevel(NamedTuple):
    price: float
    size: float
    marketMaker: str


class PriceIncrement(NamedTuple):
    lowEdge: float
    increment: float


class PortfolioItem(NamedTuple):
    contract: Contract
    position: float
    marketPrice: float
    marketValue: float
    averageCost: float
    unrealizedPNL: float
    realizedPNL: float
    account: str


class Position(NamedTuple):
    account: str
    contract: Contract
    position: float
    avgCost: float


@dataclass(slots=True)
class Fill:
    contract: Contract
    execution: Execution
    commissionReport: CommissionReport
    time: datetime


@dataclass(slots=True, frozen=True)
class OptionChain:
    exchange: str
    underlyingConId: int
    tradingClass: str
    multiplier: str
    expirations: List[str]
    strikes: List[float]


@dataclass(slots=True, frozen=True)
class Dividends:
    past12Months: Optional[float]
    next12Months: Optional[float]
    nextDate: Optional[date_]
    nextAmount: Optional[float]


@dataclass(slots=True, frozen=True)
class NewsArticle:
    articleType: int
    articleText: str


@dataclass(slots=True, frozen=True)
class HistoricalNews:
    time: datetime
    providerCode: str
    articleId: str
    headline: str


@dataclass(slots=True, frozen=True)
class NewsTick:
    timeStamp: int
    providerCode: str
    articleId: str
    headline: str
    extraData: str


@dataclass(slots=True, frozen=True)
class NewsBulletin:
    msgId: int
    msgType: int
    message: str
    origExchange: str


@dataclass(slots=True, frozen=True)
class FamilyCode:
    accountID: str
    familyCodeStr: str


@dataclass(slots=True, frozen=True)
class SmartComponent:
    bitNumber: int
    exchange: str
    exchangeLetter: str


@dataclass(slots=True, frozen=True)
class ConnectionStats:
    startTime: float
    duration: float
    numBytesRecv: int
    numBytesSent: int
    numMsgRecv: int
    numMsgSent: int


class BarDataList(List[BarData]):
    """
    List of :class:`.BarData` that also stores all request parameters.

    Events:

        * ``updateEvent``
          (bars: :class:`.BarDataList`, hasNewBar: bool)
    """

    reqId: int
    contract: Contract
    endDateTime: Union[datetime, date_, str, None]
    durationStr: str
    barSizeSetting: str
    whatToShow: str
    useRTH: bool
    formatDate: int
    keepUpToDate: bool
    chartOptions: List[TagValue]

    def __init__(self, *args):
        super().__init__(*args)
        self.updateEvent = Event("updateEvent")
        self.subscription_bus = Event("Subscription bus")

    def __eq__(self, other) -> bool:
        return self is other

    def _on_data(self, ib: "IB", bar: BarData):
        """Called on bar update when keepUpToDate=True."""

        lastDate = self[-1].date
        if bar.date < lastDate:
            return

        hasNewBar = len(self) == 0 or bar.date > lastDate
        if hasNewBar:
            self.append(bar)
        elif self[-1] != bar:
            self[-1] = bar
        else:
            return
        ib.barUpdateEvent.emit(self, hasNewBar)
        self.updateEvent.emit(self, hasNewBar)


class RealTimeBarList(list[RealTimeBar]):
    """
    List of :class:`.RealTimeBar` that also stores all request parameters.

    Events:

        * ``updateEvent``
          (bars: :class:`.RealTimeBarList`, hasNewBar: bool)
    """

    reqId: int
    contract: Contract
    barSize: int
    whatToShow: str
    useRTH: bool
    realTimeBarsOptions: list[TagValue]

    def __init__(self, *args):
        super().__init__(*args)
        self.updateEvent = Event("updateEvent")
        self.subscription_bus = Event("Subscription bus")

    def __eq__(self, other) -> bool:
        return self is other

    def _on_data(self, ib: "IB", bar: RealTimeBar):
        """Called on real time bar update."""
        self.append(bar)
        ib.barUpdateEvent.emit(self, True)
        self.updateEvent.emit(self, True)


class ScanDataList(list[ScanData]):
    """
    List of :class:`.ScanData` that also stores all request parameters.

    Events:
        * ``updateEvent`` (:class:`.ScanDataList`)
    """

    reqId: int
    subscription: ScannerSubscription
    scannerSubscriptionOptions: list[TagValue]
    scannerSubscriptionFilterOptions: list[TagValue]

    def __init__(self, *args):
        super().__init__(*args)
        self.updateEvent = Event("updateEvent")
        self.subscription_bus = Event("Subscription bus")

    def __eq__(self, other):
        return self is other

    def _on_data(self, ib: "IB", data: ScanData):
        """Called on scanner data."""
        rank = data[0].rank if 0 <= len(data) else None
        if rank == 0:
            self.clear()
        self.extend(data)
        ib.scannerDataEvent.emit(self)
        self.updateEvent.emit(self)


class DynamicObject:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __repr__(self):
        clsName = self.__class__.__name__
        kwargs = ", ".join(f"{k}={v!r}" for k, v in self.__dict__.items())
        return f"{clsName}({kwargs})"


class FundamentalRatios(DynamicObject):
    """
    See:
    https://web.archive.org/web/20200725010343/https://interactivebrokers.github.io/tws-api/fundamental_ratios_tags.html
    """

    pass


@dataclass
class IBDefaults:
    """A simple way to provide default values when populating API data."""

    # optionally replace IBKR using -1 price and 0 size when quotes don't exist
    emptyPrice: Any = -1
    emptySize: Any = 0

    # optionally replace ib_async default for all instance variable values before popualted from API updates
    unset: Any = nan

    # optionally change the timezone used for log history events in objects (no impact on orders or data processing)
    timezone: tzinfo = timezone.utc
