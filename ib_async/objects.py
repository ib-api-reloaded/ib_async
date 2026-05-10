"""Object hierarchy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, tzinfo
from datetime import date as date_
from decimal import Decimal
from typing import Any

from eventkit import Event

from ._proto.safe import safe_decimal
from .contract import Contract, ScanData, TagValue
from .util import EPOCH, UNSET_DOUBLE, UNSET_INTEGER

nan = float("nan")


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


@dataclass
class Execution:
    execId: str = ""
    time: datetime = field(default=EPOCH)
    acctNumber: str = ""
    exchange: str = ""
    side: str = ""
    # Quantity / price fields are ``Decimal | None``: ``None`` means the
    # wire didn't carry a value, which is falsy under ``if shares:``
    # checks. ``Decimal('NaN')`` would be silently truthy and break
    # those checks across user code.
    shares: Decimal | None = None
    price: Decimal | None = None
    permId: int = 0
    clientId: int = 0
    orderId: int = 0
    liquidation: int = 0
    cumQty: Decimal | None = None
    avgPrice: Decimal | None = None
    orderRef: str = ""
    evRule: str = ""
    evMultiplier: Decimal | None = None
    modelCode: str = ""
    lastLiquidity: int = 0
    pendingPriceRevision: bool = False
    submitter: str = ""
    # IBKR uses ``-1`` (OptionExerciseType.NoneItem) as the unset sentinel,
    # NOT ``0``. ``0`` is "Exercise"; ``2`` is "Lapse". Defaulting to ``-1``
    # preserves the unset semantics across user code that gates on the field.
    optExerciseOrLapseType: int = -1


@dataclass
class CommissionReport:
    execId: str = ""
    commission: Decimal | None = None
    currency: str = ""
    realizedPNL: Decimal | None = None
    yield_: Decimal | None = None
    yieldRedemptionDate: int = 0


@dataclass
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


@dataclass
class BarData:
    date: date_ | datetime = EPOCH
    # OHLC + volume + average are ``Decimal | None`` end-to-end.
    # ``None`` means the wire didn't carry a value; falsy under
    # ``if bar.open:`` checks so user code's existing idioms keep
    # working. ``Decimal('NaN')`` would silently evaluate True.
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: Decimal | None = None
    average: Decimal | None = None
    barCount: int = 0


@dataclass
class RealTimeBar:
    time: datetime = EPOCH
    endTime: int = -1
    open_: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: Decimal | None = None
    wap: Decimal | None = None
    count: int = 0


@dataclass
class TickAttrib:
    canAutoExecute: bool = False
    pastLimit: bool = False
    preOpen: bool = False


@dataclass
class TickAttribBidAsk:
    bidPastLow: bool = False
    askPastHigh: bool = False


@dataclass
class TickAttribLast:
    pastLimit: bool = False
    unreported: bool = False


@dataclass
class HistogramData:
    # ``size`` is the wire-name in IBKR's reference (gate >=130).
    # Earlier ib_async releases coerced this to an integer ``count``,
    # which silently truncated fractional sizes that legitimately ship
    # for crypto / FRACTIONAL_SIZE_SUPPORT (gate 163) instruments.
    # ``Decimal | None`` end-to-end preserves the wire precision and
    # carries the unset semantics the rest of the domain uses.
    price: float = 0.0
    size: Decimal | None = None


@dataclass
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


@dataclass
class PnL:
    account: str = ""
    modelCode: str = ""
    dailyPnL: float = nan
    unrealizedPnL: float = nan
    realizedPnL: float = nan


@dataclass
class TradeLogEntry:
    time: datetime
    status: str = ""
    message: str = ""
    errorCode: int = 0


@dataclass
class PnLSingle:
    account: str = ""
    modelCode: str = ""
    conId: int = 0
    dailyPnL: float = nan
    unrealizedPnL: float = nan
    realizedPnL: float = nan
    # Wire ``position`` is a Decimal-shaped string. Earlier ib_async
    # truncated to ``int``, silently dropping fractional positions for
    # crypto and other FRACTIONAL_SIZE_SUPPORT (gate 163) instruments.
    # ``Decimal | None`` matches the wire and the rest of the v3.0
    # Decimal-native domain; ``None`` is the unset sentinel (falsy
    # without the NaN truthy-trap).
    position: Decimal | None = None
    value: float = nan


@dataclass
class HistoricalSession:
    startDateTime: str = ""
    endDateTime: str = ""
    refDate: str = ""


@dataclass
class HistoricalSchedule:
    startDateTime: str = ""
    endDateTime: str = ""
    timeZone: str = ""
    sessions: list[HistoricalSession] = field(default_factory=list)


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


# IBKR streams every account-update tag through a single
# ``optional string value`` field on the wire. Some tags carry monetary
# numbers (``NetLiquidation``, ``AvailableFunds``), others carry strings
# (``AccountType``, ``Currency``). Callers reaching for the typed
# Decimal view via ``AccountValue.decimalValue`` get back ``None`` when
# the tag isn't on this list, so user code can never accidentally
# coerce ``"USD"`` into a Decimal.
#
# Strictly currency-denominated only: integer-counted tags
# (``DayTradesRemaining``), sorting hints (``ColumnPrio-*``), string
# labels (``SegmentTitle-*``), unit-counted tags (``BillableSize``),
# and pure ratios (``Leverage*``) are intentionally excluded — none
# of them represents an amount of money. ``Cushion`` and
# ``ExchangeRate`` stay because they're shipped as base-currency-
# context numerics that callers do reach for as ``Decimal``.
MONETARY_ACCOUNT_VALUE_TAGS: frozenset[str] = frozenset(
    {
        "AccruedCash",
        "AccruedCash-C",
        "AccruedCash-S",
        "AccruedDividend",
        "AccruedDividend-C",
        "AccruedDividend-S",
        "AvailableFunds",
        "AvailableFunds-C",
        "AvailableFunds-S",
        "Billable",
        "Billable-C",
        "Billable-S",
        "BuyingPower",
        "CashBalance",
        "CorporateBondValue",
        "Cushion",
        "EquityWithLoanValue",
        "EquityWithLoanValue-C",
        "EquityWithLoanValue-S",
        "ExcessLiquidity",
        "ExcessLiquidity-C",
        "ExcessLiquidity-S",
        "ExchangeRate",
        "FullAvailableFunds",
        "FullAvailableFunds-C",
        "FullAvailableFunds-S",
        "FullExcessLiquidity",
        "FullExcessLiquidity-C",
        "FullExcessLiquidity-S",
        "FullInitMarginReq",
        "FullInitMarginReq-C",
        "FullInitMarginReq-S",
        "FullMaintMarginReq",
        "FullMaintMarginReq-C",
        "FullMaintMarginReq-S",
        "FundValue",
        "FutureOptionValue",
        "FuturesPNL",
        "GrossPositionValue",
        "GrossPositionValue-S",
        "Guarantee",
        "Guarantee-C",
        "Guarantee-S",
        "IndianStockHaircut",
        "IndianStockHaircut-C",
        "IndianStockHaircut-S",
        "InitMarginReq",
        "InitMarginReq-C",
        "InitMarginReq-S",
        "IssuerOptionValue",
        "LookAheadAvailableFunds",
        "LookAheadAvailableFunds-C",
        "LookAheadAvailableFunds-S",
        "LookAheadExcessLiquidity",
        "LookAheadExcessLiquidity-C",
        "LookAheadExcessLiquidity-S",
        "LookAheadInitMarginReq",
        "LookAheadInitMarginReq-C",
        "LookAheadInitMarginReq-S",
        "LookAheadMaintMarginReq",
        "LookAheadMaintMarginReq-C",
        "LookAheadMaintMarginReq-S",
        "MaintMarginReq",
        "MaintMarginReq-C",
        "MaintMarginReq-S",
        "MoneyMarketFundValue",
        "MutualFundValue",
        "NetDividend",
        "NetLiquidation",
        "NetLiquidation-C",
        "NetLiquidation-S",
        "NetLiquidationByCurrency",
        "NetLiquidationUncertainty",
        "OptionMarketValue",
        "PASharesValue",
        "PASharesValue-C",
        "PASharesValue-S",
        "PhysicalCertificateValue",
        "PhysicalCertificateValue-C",
        "PhysicalCertificateValue-S",
        "PostExpirationExcess",
        "PostExpirationExcess-C",
        "PostExpirationExcess-S",
        "PostExpirationMargin",
        "PostExpirationMargin-C",
        "PostExpirationMargin-S",
        "PreviousDayEquityWithLoanValue",
        "PreviousDayEquityWithLoanValue-S",
        "RealizedPnL",
        "RegTEquity",
        "RegTEquity-S",
        "RegTMargin",
        "RegTMargin-S",
        # IBKR's ``AccountSummaryTags`` ships these as ``ReqTEquity`` /
        # ``ReqTMargin``. Different streams use ``RegT*`` (above) vs
        # ``ReqT*`` spellings; both are monetary.
        "ReqTEquity",
        "ReqTMargin",
        # ``SettledCash`` ships in IBKR's ``AccountSummaryTags.AllTags``
        # default request and through ``reqAccountSummaryAsync`` here.
        # The ``-C`` / ``-S`` per-segment variants arrive on the live
        # ``updateAccountValue`` stream. All three carry monetary
        # values and need the typed Decimal view to resolve.
        "SettledCash",
        "SettledCash-C",
        "SettledCash-S",
        "SMA",
        "SMA-S",
        "StockMarketValue",
        "TBondValue",
        "TBillValue",
        "TotalCashBalance",
        "TotalCashValue",
        "TotalCashValue-C",
        "TotalCashValue-S",
        "TotalDebitCardPendingCharges",
        "TotalDebitCardPendingCharges-C",
        "TotalDebitCardPendingCharges-S",
        "UnrealizedPnL",
        "WarrantValue",
    }
)


@dataclass(slots=True, frozen=True)
class AccountValue:
    account: str
    tag: str
    value: str
    currency: str
    modelCode: str

    @property
    def decimalValue(self) -> Decimal | None:
        """Typed view of ``value`` for monetary tags.

        Returns ``None`` for non-monetary tags (e.g. ``AccountType``,
        ``Currency``) and for monetary tags whose wire value can't be
        parsed — including IBKR's UNSET_DOUBLE / UNSET_INTEGER /
        UNSET_LONG sentinel strings, empty values, ``"NaN"`` and
        ``"Infinity"``. Routed through ``safe_decimal`` so the sentinel
        guard list stays in lockstep with every other Decimal-coercion
        site (``decoder.parse``, ``_proto/*`` converters); a divergent
        ad-hoc parse here previously surfaced a fake 1.8e308 / 2.1B
        ``NetLiquidation`` whenever IBKR shipped the unset sentinel.
        Never raises.
        """
        if self.tag not in MONETARY_ACCOUNT_VALUE_TAGS:
            return None
        return safe_decimal(self.value)


# Tick / bar / depth records — slotted frozen dataclasses for v3.0.
# Numeric ``price`` / ``size`` fields stay ``float`` here pending the
# Ticker hot-path benchmark in the same phase. Migrating these to
# ``Decimal | None`` is coherent with the framework-wide direction but
# coupled to ``Ticker``'s field types (these tick records are stored
# verbatim onto ``ticker.ticks`` / ``ticker.tickByTicks`` lists, so the
# inner type tracks Ticker exactly). The dataclass-shape change here is
# structural only and adds slots for per-record memory savings.


@dataclass(slots=True, frozen=True)
class TickData:
    time: datetime
    tickType: int
    price: float
    size: float


@dataclass(slots=True, frozen=True)
class HistoricalTick:
    time: datetime
    price: float
    size: float


@dataclass(slots=True, frozen=True)
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


@dataclass(slots=True, frozen=True)
class TickByTickAllLast:
    tickType: int
    time: datetime
    price: float
    size: float
    tickAttribLast: TickAttribLast
    exchange: str
    specialConditions: str


@dataclass(slots=True, frozen=True)
class TickByTickBidAsk:
    time: datetime
    bidPrice: float
    askPrice: float
    bidSize: float
    askSize: float
    tickAttribBidAsk: TickAttribBidAsk


@dataclass(slots=True, frozen=True)
class TickByTickMidPoint:
    time: datetime
    midPoint: float


@dataclass(slots=True, frozen=True)
class MktDepthData:
    time: datetime
    position: int
    marketMaker: str
    operation: int
    side: int
    price: float
    size: float


@dataclass(slots=True, frozen=True)
class DOMLevel:
    price: float
    size: float
    marketMaker: str


@dataclass(slots=True, frozen=True)
class PriceIncrement:
    lowEdge: float
    increment: float


@dataclass(slots=True, frozen=True)
class PortfolioItem:
    contract: Contract
    position: Decimal | None = None
    marketPrice: Decimal | None = None
    marketValue: Decimal | None = None
    averageCost: Decimal | None = None
    unrealizedPNL: Decimal | None = None
    realizedPNL: Decimal | None = None
    account: str = ""


@dataclass(slots=True, frozen=True)
class Position:
    account: str
    contract: Contract
    position: Decimal | None = None
    avgCost: Decimal | None = None


@dataclass(slots=True, frozen=True)
class Fill:
    contract: Contract
    execution: Execution
    commissionReport: CommissionReport
    time: datetime


@dataclass(slots=True, frozen=True)
class EfpData:
    """
    Exchange for Physical (EFP) futures data.

    EFP allows trading a position in a single stock for a position
    in the corresponding single stock future.
    """

    # Annualized basis points (financing rate comparable to broker rates)
    basisPoints: float

    # Basis points formatted as percentage string
    formattedBasisPoints: str

    # The implied Futures price
    impliedFuture: float

    # Number of days until the future's last trade date
    holdDays: int

    # Expiration date of the single stock future
    futureLastTradeDate: str

    # Dividend impact on the annualized basis points interest rate
    dividendImpact: float

    # Expected dividends until future expiration
    dividendsToLastTradeDate: float


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
        if not isinstance(other, int | float):
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


@dataclass(slots=True, frozen=True)
class OptionChain:
    exchange: str
    underlyingConId: int
    tradingClass: str
    multiplier: str
    expirations: list[str]
    strikes: list[float]


@dataclass(slots=True, frozen=True)
class Dividends:
    past12Months: float | None
    next12Months: float | None
    nextDate: date_ | None
    nextAmount: float | None


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
    contract: Contract | None = None


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


class BarDataList(list[BarData]):
    """
    List of :class:`.BarData` that also stores all request parameters.

    Events:

        * ``updateEvent``
          (bars: :class:`.BarDataList`, hasNewBar: bool)
    """

    reqId: int
    contract: Contract
    endDateTime: datetime | date_ | str | None
    durationStr: str
    barSizeSetting: str
    whatToShow: str
    useRTH: bool
    formatDate: int
    keepUpToDate: bool
    chartOptions: list[TagValue]

    def __init__(self, *args):
        super().__init__(*args)
        self.updateEvent = Event("updateEvent")

    def __eq__(self, other) -> bool:
        return self is other


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

    def __eq__(self, other) -> bool:
        return self is other


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

    def __eq__(self, other):
        return self is other


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
    timezone: tzinfo = UTC
