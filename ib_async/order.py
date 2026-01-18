"""Order types used by Interactive Brokers."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from math import nan
from typing import ClassVar, TypeAlias

from eventkit import Event

from .contract import Contract, TagValue
from .objects import Fill, SoftDollarTier, TradeLogEntry
from .util import (
    DECIMAL_NAN,
    DECIMAL_ZERO,
    UNSET_DOUBLE,
    UNSET_INTEGER,
    dataclassNonDefaults,
)


class OrderTIF(StrEnum):
    """order time in force
    https://www.ibkrguides.com/traderworkstation/order-types.htm
    https://www.interactivebrokers.com/en/trading/ordertypes.php
    """

    DAY = "DAY"
    GTC = "GTC"  # good til cancelled
    OPG = "OPG"  #
    GTD = "GTD"  # good til date
    IOC = "IOC"  # Immediate or Cancel
    FOK = "FOK"  # fill or kill
    GAT = "GAT"  # good after time
    OVERNIGHT = "OVERNIGHT"  # overnight
    OVERNIGHT_DAY = "OVERNIGHT + DAY"  # overnight & day
    AUC = "AUC"  # at auction


@dataclass(slots=True)
class Order:
    """
    Order for trading contracts.

    https://interactivebrokers.github.io/tws-api/available_orders.html

    https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-ref/#order-ref
    """

    orderId: int = 0
    clientId: int = 0
    permId: int = 0
    action: str = ""
    totalQuantity: float | Decimal = DECIMAL_ZERO
    orderType: str = ""
    lmtPrice: float | Decimal | None = UNSET_DOUBLE
    auxPrice: float | Decimal | None = UNSET_DOUBLE
    tif: str = ""
    activeStartTime: str = ""
    activeStopTime: str = ""
    ocaGroup: str = ""
    ocaType: int = 0
    orderRef: str = ""
    transmit: bool = True
    parentId: int = 0
    blockOrder: bool = False
    sweepToFill: bool = False
    displaySize: int = 0
    triggerMethod: int = 0
    outsideRth: bool = False
    hidden: bool = False
    goodAfterTime: str = ""
    goodTillDate: str = ""
    rule80A: str = ""
    allOrNone: bool = False
    minQty: int = UNSET_INTEGER
    percentOffset: float | Decimal = UNSET_DOUBLE
    overridePercentageConstraints: bool = False
    trailStopPrice: float | Decimal = UNSET_DOUBLE
    trailingPercent: float | Decimal = UNSET_DOUBLE
    faGroup: str = ""
    faProfile: str = ""  # obsolete
    faMethod: str = ""
    faPercentage: str = ""
    designatedLocation: str = ""
    openClose: str = "O"
    origin: int = 0
    shortSaleSlot: int = 0
    exemptCode: int = -1
    discretionaryAmt: float = 0.0
    eTradeOnly: bool = False
    firmQuoteOnly: bool = False
    nbboPriceCap: float | Decimal = UNSET_DOUBLE
    optOutSmartRouting: bool = False
    auctionStrategy: int = 0
    startingPrice: float | Decimal = UNSET_DOUBLE
    stockRefPrice: float | Decimal = UNSET_DOUBLE
    delta: float | Decimal = UNSET_DOUBLE
    stockRangeLower: float | Decimal = UNSET_DOUBLE
    stockRangeUpper: float | Decimal = UNSET_DOUBLE
    randomizePrice: bool = False
    randomizeSize: bool = False
    volatility: float | Decimal = UNSET_DOUBLE
    volatilityType: int = UNSET_INTEGER
    deltaNeutralOrderType: str = ""
    deltaNeutralAuxPrice: float | Decimal = UNSET_DOUBLE
    deltaNeutralConId: int = 0
    deltaNeutralSettlingFirm: str = ""
    deltaNeutralClearingAccount: str = ""
    deltaNeutralClearingIntent: str = ""
    deltaNeutralOpenClose: str = ""
    deltaNeutralShortSale: bool = False
    deltaNeutralShortSaleSlot: int = 0
    deltaNeutralDesignatedLocation: str = ""
    continuousUpdate: bool = False
    referencePriceType: int = UNSET_INTEGER
    basisPoints: float | Decimal = UNSET_DOUBLE
    basisPointsType: int = UNSET_INTEGER
    scaleInitLevelSize: int = UNSET_INTEGER
    scaleSubsLevelSize: int = UNSET_INTEGER
    scalePriceIncrement: float | Decimal = UNSET_DOUBLE
    scalePriceAdjustValue: float | Decimal = UNSET_DOUBLE
    scalePriceAdjustInterval: int = UNSET_INTEGER
    scaleProfitOffset: float | Decimal = UNSET_DOUBLE
    scaleAutoReset: bool = False
    scaleInitPosition: int = UNSET_INTEGER
    scaleInitFillQty: int = UNSET_INTEGER
    scaleRandomPercent: bool = False
    scaleTable: str = ""
    hedgeType: str = ""
    hedgeParam: str = ""
    account: str = ""
    settlingFirm: str = ""
    clearingAccount: str = ""
    clearingIntent: str = ""
    algoStrategy: str = ""
    algoParams: list[TagValue] = field(default_factory=list)
    smartComboRoutingParams: list[TagValue] = field(default_factory=list)
    algoId: str = ""
    whatIf: bool = False
    notHeld: bool = False
    solicited: bool = False
    modelCode: str = ""
    orderComboLegs: list[OrderComboLeg] = field(default_factory=list)
    orderMiscOptions: list[TagValue] = field(default_factory=list)
    referenceContractId: int = 0
    peggedChangeAmount: float = 0.0
    isPeggedChangeAmountDecrease: bool = False
    referenceChangeAmount: float = 0.0
    referenceExchangeId: str = ""
    adjustedOrderType: str = ""
    triggerPrice: float | Decimal | None = UNSET_DOUBLE
    adjustedStopPrice: float | Decimal = UNSET_DOUBLE
    adjustedStopLimitPrice: float | Decimal = UNSET_DOUBLE
    adjustedTrailingAmount: float | Decimal = UNSET_DOUBLE
    adjustableTrailingUnit: int = 0
    lmtPriceOffset: float | Decimal = UNSET_DOUBLE
    conditions: list[OrderConditionType] = field(default_factory=list)
    conditionsCancelOrder: bool = False
    conditionsIgnoreRth: bool = False
    extOperator: str = ""
    softDollarTier: SoftDollarTier = field(default_factory=SoftDollarTier)
    cashQty: float | Decimal = UNSET_DOUBLE
    mifid2DecisionMaker: str = ""
    mifid2DecisionAlgo: str = ""
    mifid2ExecutionTrader: str = ""
    mifid2ExecutionAlgo: str = ""
    dontUseAutoPriceForHedge: bool = False
    isOmsContainer: bool = False
    discretionaryUpToLimitPrice: bool = False
    autoCancelDate: str = ""
    filledQuantity: float | Decimal = DECIMAL_ZERO
    refFuturesConId: int = 0
    autoCancelParent: bool = False
    shareholder: str = ""
    imbalanceOnly: bool = False
    routeMarketableToBbo: bool = False
    parentPermId: int = 0
    usePriceMgmtAlgo: bool = False
    duration: int = UNSET_INTEGER
    postToAts: int = UNSET_INTEGER
    advancedErrorOverride: str = ""
    manualOrderTime: str = ""
    minTradeQty: int = UNSET_INTEGER
    minCompeteSize: int = UNSET_INTEGER
    competeAgainstBestOffset: float | Decimal = UNSET_DOUBLE
    midOffsetAtWhole: float | Decimal = UNSET_DOUBLE
    midOffsetAtHalf: float | Decimal = UNSET_DOUBLE
    customerAccount: str = ""
    professionalCustomer: bool = False
    bondAccruedInterest: str = ""
    includeOvernight: bool = False
    manualOrderIndicator: int = UNSET_INTEGER
    submitter: str = ""

    def __repr__(self):
        attrs = dataclassNonDefaults(self)
        if self.__class__ is not Order:
            attrs.pop("orderType", None)

        if not self.softDollarTier:
            attrs.pop("softDollarTier")

        clsName = self.__class__.__qualname__
        kwargs = ", ".join(f"{k}={v!r}" for k, v in attrs.items())
        return f"{clsName}({kwargs})"

    __str__ = __repr__

    def __eq__(self, other):
        return self is other

    def __hash__(self):
        return id(self)


class LimitOrder(Order):
    def __init__(self, action: str, totalQuantity: float, lmtPrice: float, **kwargs):
        Order.__init__(
            self,
            orderType="LMT",
            action=action,
            totalQuantity=totalQuantity,
            lmtPrice=lmtPrice,
            **kwargs,
        )


class MarketOrder(Order):
    def __init__(self, action: str, totalQuantity: float, **kwargs):
        Order.__init__(
            self, orderType="MKT", action=action, totalQuantity=totalQuantity, **kwargs
        )


class StopOrder(Order):
    def __init__(self, action: str, totalQuantity: float, stopPrice: float, **kwargs):
        Order.__init__(
            self,
            orderType="STP",
            action=action,
            totalQuantity=totalQuantity,
            auxPrice=stopPrice,
            **kwargs,
        )


class StopLimitOrder(Order):
    def __init__(
        self,
        action: str,
        totalQuantity: float,
        lmtPrice: float,
        stopPrice: float,
        **kwargs,
    ):
        Order.__init__(
            self,
            orderType="STP LMT",
            action=action,
            totalQuantity=totalQuantity,
            lmtPrice=lmtPrice,
            auxPrice=stopPrice,
            **kwargs,
        )


@dataclass(slots=True)
class OrderStatus:
    """
    Reference:
    https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/#order-status
    """

    orderId: int = 0
    status: str = ""
    filled: float | Decimal = 0.0
    remaining: float | Decimal = 0.0
    avgFillPrice: float | Decimal = 0.0
    permId: int = 0
    parentId: int = 0
    lastFillPrice: float | Decimal = 0.0
    clientId: int = 0
    whyHeld: str = ""
    mktCapPrice: float | Decimal = 0.0

    @property
    def total(self) -> float | Decimal:
        """Helper property to return the total size of this requested order."""
        return self.filled + self.remaining  # type: ignore

    PendingSubmit: ClassVar[str] = "PendingSubmit"
    PendingCancel: ClassVar[str] = "PendingCancel"
    PreSubmitted: ClassVar[str] = "PreSubmitted"
    Submitted: ClassVar[str] = "Submitted"
    ApiPending: ClassVar[str] = "ApiPending"
    ApiCancelled: ClassVar[str] = "ApiCancelled"
    ApiUpdate: ClassVar[str] = "ApiUpdate"
    Cancelled: ClassVar[str] = "Cancelled"
    Filled: ClassVar[str] = "Filled"
    Inactive: ClassVar[str] = "Inactive"
    ValidationError: ClassVar[str] = "ValidationError"

    # order has either been completed, cancelled, or destroyed by IBKR's risk management
    DoneStates: ClassVar[frozenset[str]] = frozenset(
        ["Filled", "Cancelled", "ApiCancelled", "Inactive"]
    )

    # order is capable of executing at sometime in the future
    ActiveStates: ClassVar[frozenset[str]] = frozenset(
        [
            "PendingSubmit",
            "ApiPending",
            "PreSubmitted",
            "Submitted",
            "ValidationError",
            "ApiUpdate",
        ]
    )

    # order hasn't triggered "live" yet (but it could become live and execute before we
    # receive a notice)
    WaitingStates: ClassVar[frozenset[str]] = frozenset(
        [
            "PendingSubmit",
            "ApiPending",
            "PreSubmitted",
        ]
    )

    # order is live and "working" at the broker against public exchanges
    WorkingStates: ClassVar[frozenset[str]] = frozenset(
        [
            "Submitted",
            # ValidationError can happen on submit or modify.
            # If ValidationError happens on submit, the states go PreSubmitted ->
            # ValidationError -> Submitted (if it can be ignored automatically), so
            # order is still live.
            # If ValidationError happens on modify, the update is just ValidationError
            # with no new Submitted, so the previous order state remains active.
            "ValidationError",
            "ApiUpdate",
        ]
    )


@dataclass(slots=True)
class OrderState:
    status: str = ""
    initMarginBefore: float | Decimal = nan
    maintMarginBefore: float | Decimal = nan
    equityWithLoanBefore: float | Decimal = nan
    initMarginChange: float | Decimal = nan
    maintMarginChange: float | Decimal = nan
    equityWithLoanChange: float | Decimal = nan
    initMarginAfter: float | Decimal = nan
    maintMarginAfter: float | Decimal = nan
    equityWithLoanAfter: float | Decimal = nan
    commission: float | Decimal = nan
    minCommission: float | Decimal = nan
    maxCommission: float | Decimal = nan
    commissionCurrency: str = ""
    marginCurrency: str = ""
    initMarginBeforeOutsideRTH: float | Decimal = nan
    maintMarginBeforeOutsideRTH: float | Decimal = nan
    equityWithLoanBeforeOutsideRTH: float | Decimal = nan
    initMarginChangeOutsideRTH: float | Decimal = nan
    maintMarginChangeOutsideRTH: float | Decimal = nan
    equityWithLoanChangeOutsideRTH: float | Decimal = nan
    initMarginAfterOutsideRTH: float | Decimal = nan
    maintMarginAfterOutsideRTH: float | Decimal = nan
    equityWithLoanAfterOutsideRTH: float | Decimal = nan
    suggestedSize: Decimal = DECIMAL_NAN
    rejectReason: str = ""
    orderAllocations: list[OrderAllocation] | None = None
    warningText: str = ""
    completedTime: str = ""
    completedStatus: str = ""


@dataclass(slots=True)
class OrderComboLeg:
    price: float | Decimal = UNSET_DOUBLE


@dataclass(slots=True)
class Trade:
    """
    Trade keeps track of an order, its status and all its fills.

    Events:
        * ``statusEvent`` (trade: :class:`.Trade`)
        * ``modifyEvent`` (trade: :class:`.Trade`)
        * ``fillEvent`` (trade: :class:`.Trade`, fill: :class:`.Fill`)
        * ``commissionReportEvent`` (trade: :class:`.Trade`,
          fill: :class:`.Fill`, commissionReport: :class:`.CommissionReport`)
        * ``filledEvent`` (trade: :class:`.Trade`)
        * ``cancelEvent`` (trade: :class:`.Trade`)
        * ``cancelledEvent`` (trade: :class:`.Trade`)
    """

    contract: Contract = field(default_factory=Contract)
    order: Order = field(default_factory=Order)
    orderStatus: OrderStatus = field(default_factory=OrderStatus)
    fills: list[Fill] = field(default_factory=list)
    log: list[TradeLogEntry] = field(default_factory=list)
    advancedError: str = ""

    # instance Events must be declared as fields so they exist in __slots__
    statusEvent: Event = field(init=False, repr=False, compare=False)
    modifyEvent: Event = field(init=False, repr=False, compare=False)
    fillEvent: Event = field(init=False, repr=False, compare=False)
    commissionReportEvent: Event = field(init=False, repr=False, compare=False)
    filledEvent: Event = field(init=False, repr=False, compare=False)
    cancelEvent: Event = field(init=False, repr=False, compare=False)
    cancelledEvent: Event = field(init=False, repr=False, compare=False)

    # TODO: replace these with an enum?
    events: ClassVar = (
        "statusEvent",
        "modifyEvent",
        "fillEvent",
        "commissionReportEvent",
        "filledEvent",
        "cancelEvent",
        "cancelledEvent",
    )

    def __post_init__(self):
        self.statusEvent = Event("statusEvent")
        self.modifyEvent = Event("modifyEvent")
        self.fillEvent = Event("fillEvent")
        self.commissionReportEvent = Event("commissionReportEvent")
        self.filledEvent = Event("filledEvent")
        self.cancelEvent = Event("cancelEvent")
        self.cancelledEvent = Event("cancelledEvent")

    def isWaiting(self) -> bool:
        """True if sent to IBKR but not "Submitted" for live execution yet."""
        return self.orderStatus.status in OrderStatus.WaitingStates

    def isWorking(self) -> bool:
        """True if sent to IBKR but not "Submitted" for live execution yet."""
        return self.orderStatus.status in OrderStatus.WorkingStates

    def isActive(self) -> bool:
        """True if eligible for execution, false otherwise."""
        return self.orderStatus.status in OrderStatus.ActiveStates

    def isDone(self) -> bool:
        """True if completely filled or cancelled, false otherwise."""
        return self.orderStatus.status in OrderStatus.DoneStates

    def filled(self) -> Decimal:
        """Number of shares filled."""
        fills = self.fills
        if self.contract.secType == "BAG":
            # don't count fills for the leg contracts
            fills = [f for f in fills if f.contract.secType == "BAG"]

        return sum((f.execution.shares for f in fills), DECIMAL_ZERO)

    def remaining(self) -> Decimal:
        """Number of shares remaining to be filled."""
        return Decimal(self.order.totalQuantity) - self.filled()


@dataclass(slots=True)
class BracketOrder:
    parent: Order
    takeProfit: Order
    stopLoss: Order


@dataclass(slots=True)
class OrderCondition:
    condType: ClassVar[int]
    conjunction: str = "a"

    @staticmethod
    def createClass(condType):
        d = {
            1: PriceCondition,
            3: TimeCondition,
            4: MarginCondition,
            5: ExecutionCondition,
            6: VolumeCondition,
            7: PercentChangeCondition,
        }
        return d[condType]

    def And(self):
        self.conjunction = "a"
        return self

    def Or(self):
        self.conjunction = "o"
        return self


@dataclass(slots=True)
class PriceCondition(OrderCondition):
    condType: ClassVar[int] = 1
    isMore: bool = True
    price: float = 0.0
    conId: int = 0
    exch: str = ""
    triggerMethod: int = 0


@dataclass(slots=True)
class TimeCondition(OrderCondition):
    condType: ClassVar[int] = 3
    isMore: bool = True
    time: str = ""


@dataclass(slots=True)
class MarginCondition(OrderCondition):
    condType: ClassVar[int] = 4
    isMore: bool = True
    percent: int = 0


@dataclass(slots=True)
class ExecutionCondition(OrderCondition):
    condType: ClassVar[int] = 5
    secType: str = ""
    exch: str = ""
    symbol: str = ""


@dataclass(slots=True)
class VolumeCondition(OrderCondition):
    condType: ClassVar[int] = 6
    isMore: bool = True
    volume: int = 0
    conId: int = 0
    exch: str = ""


@dataclass(slots=True)
class PercentChangeCondition(OrderCondition):
    condType: ClassVar[int] = 7
    isMore: bool = True
    changePercent: float = 0.0
    conId: int = 0
    exch: str = ""


OrderConditionType: TypeAlias = (
    PriceCondition
    | TimeCondition
    | MarginCondition
    | ExecutionCondition
    | VolumeCondition
    | PercentChangeCondition
)


@dataclass(slots=True)
class OrderAllocation:
    """
    Reference: https://ibkrcampus.com/campus/ibkr-api-page/twsapi-ref/#order-static-pub-func
    """

    account: str = field(default="")
    position: Decimal = field(default=DECIMAL_NAN)
    positionDesired: Decimal = field(default=DECIMAL_NAN)
    positionAfter: Decimal = field(default=DECIMAL_NAN)
    desiredAllocQty: Decimal = field(default=DECIMAL_NAN)
    allowedAllocQty: Decimal = field(default=DECIMAL_NAN)
    isMonetary: bool = field(default=False)


@dataclass(slots=True, frozen=True)
class OrderCancel:
    """
    Reference https://ibkrcampus.com/campus/ibkr-api-page/twsapi-ref/#orderallocation-ref

    manualOrderCancelTime: Used by brokers and advisors when manually entering an order
                           cancellation request. Format should be “YYYYMMDD-HH:mm:ss”
                           using UTC as the timezone value.

    extOperator: Following CME Rule 576, the ExtOperator field will signify the unique
                 API operator at the time of trading for order management.

    manualOrderIndicator: Following CME Rule 576, the ManualOrderIndicator field will
                          signify if an order is manual (1) or automated (0).
    """

    manualOrderCancelTime: str = field(default="")
    extOperator: str = field(default="")
    manualOrderIndicator: int = field(default=UNSET_INTEGER)
