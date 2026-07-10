"""Order types used by Interactive Brokers."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import ClassVar, NamedTuple

from eventkit import Event

from .contract import Contract, TagValue
from .objects import Fill, SoftDollarTier, TradeLogEntry, _install_commission_alias
from .util import UNSET_DOUBLE, dataclassNonDefaults


@dataclass
class Order:
    """
    Order for trading contracts.

    https://interactivebrokers.github.io/tws-api/available_orders.html
    """

    orderId: int = 0
    clientId: int = 0
    permId: int = 0
    action: str = ""
    # Primary quantity / price fields are ``Decimal | None`` — ``None``
    # means the wire didn't carry a value, which is falsy under
    # ``if order.lmtPrice:`` checks. ``Decimal('NaN')`` would be
    # silently truthy and break those checks across user code.
    totalQuantity: Decimal | None = None
    orderType: str = ""
    lmtPrice: Decimal | None = None
    auxPrice: Decimal | None = None
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
    # ``None`` is the unset sentinel for every optional numeric field —
    # the wire encoder translates None to IBKR's UNSET_INTEGER / UNSET_DOUBLE
    # magic values at send time, but user code never sees those.
    minQty: int | None = None
    percentOffset: Decimal | None = None
    overridePercentageConstraints: bool = False
    trailStopPrice: Decimal | None = None
    trailingPercent: Decimal | None = None
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
    nbboPriceCap: Decimal | None = None
    optOutSmartRouting: bool = False
    auctionStrategy: int = 0
    startingPrice: Decimal | None = None
    stockRefPrice: Decimal | None = None
    delta: Decimal | None = None
    stockRangeLower: Decimal | None = None
    stockRangeUpper: Decimal | None = None
    randomizePrice: bool = False
    randomizeSize: bool = False
    volatility: Decimal | None = None
    volatilityType: int | None = None
    deltaNeutralOrderType: str = ""
    deltaNeutralAuxPrice: Decimal | None = None
    deltaNeutralConId: int = 0
    deltaNeutralSettlingFirm: str = ""
    deltaNeutralClearingAccount: str = ""
    deltaNeutralClearingIntent: str = ""
    deltaNeutralOpenClose: str = ""
    deltaNeutralShortSale: bool = False
    deltaNeutralShortSaleSlot: int = 0
    deltaNeutralDesignatedLocation: str = ""
    continuousUpdate: bool = False
    referencePriceType: int | None = None
    basisPoints: Decimal | None = None
    basisPointsType: int | None = None
    scaleInitLevelSize: int | None = None
    scaleSubsLevelSize: int | None = None
    scalePriceIncrement: Decimal | None = None
    scalePriceAdjustValue: Decimal | None = None
    scalePriceAdjustInterval: int | None = None
    scaleProfitOffset: Decimal | None = None
    scaleAutoReset: bool = False
    scaleInitPosition: int | None = None
    scaleInitFillQty: int | None = None
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
    triggerPrice: Decimal | None = None
    adjustedStopPrice: Decimal | None = None
    adjustedStopLimitPrice: Decimal | None = None
    adjustedTrailingAmount: Decimal | None = None
    adjustableTrailingUnit: int = 0
    lmtPriceOffset: Decimal | None = None
    conditions: list[OrderCondition] = field(default_factory=list)
    conditionsCancelOrder: bool = False
    conditionsIgnoreRth: bool = False
    extOperator: str = ""
    # Attached-order (stop-loss / profit-take) cross-references — IBKR
    # reference ``ibapi/order.py`` carries them; the wire ships them on
    # the ``PlaceOrderRequest.attachedOrders`` sub-message rather than
    # ``Order`` itself, but the domain dataclass keeps them here so user
    # code at the call site has a single object to populate.
    slOrderId: int | None = None
    slOrderType: str = ""
    ptOrderId: int | None = None
    ptOrderType: str = ""
    softDollarTier: SoftDollarTier = field(default_factory=SoftDollarTier)
    cashQty: Decimal | None = None
    mifid2DecisionMaker: str = ""
    mifid2DecisionAlgo: str = ""
    mifid2ExecutionTrader: str = ""
    mifid2ExecutionAlgo: str = ""
    dontUseAutoPriceForHedge: bool = False
    isOmsContainer: bool = False
    discretionaryUpToLimitPrice: bool = False
    autoCancelDate: str = ""
    filledQuantity: Decimal | None = None
    refFuturesConId: int = 0
    autoCancelParent: bool = False
    shareholder: str = ""
    imbalanceOnly: bool = False
    routeMarketableToBbo: bool = False
    parentPermId: int = 0
    usePriceMgmtAlgo: bool = False
    duration: int | None = None
    postToAts: int | None = None
    advancedErrorOverride: str = ""
    manualOrderTime: str = ""
    minTradeQty: int | None = None
    minCompeteSize: int | None = None
    competeAgainstBestOffset: Decimal | None = None
    midOffsetAtWhole: Decimal | None = None
    midOffsetAtHalf: Decimal | None = None
    # Compliance / origination fields IBKR added in the 195-198 gate
    # window. Read on receive (binary ``openOrder`` / protobuf
    # ``OpenOrder``), written on send (binary ``placeOrder``) when the
    # negotiated server supports the respective gate.
    customerAccount: str = ""
    professionalCustomer: bool = False
    bondAccruedInterest: Decimal | None = None
    includeOvernight: bool = False
    # ``manualOrderIndicator`` pairs with ``extOperator`` for CME-tagged
    # placements. ``None`` means unset; the wire encoder skips the
    # field at send time.
    manualOrderIndicator: int | None = None
    # ``submitter`` identifies the originating session for compliance
    # logging. Empty means IBKR did not supply one for this order.
    submitter: str = ""
    # ``allowPreOpen`` / ``ignoreOpenAuction`` control auction-window
    # routing. ``deactivate`` flags the order to be killed on fill or
    # completion. ``postOnly`` rejects an order that would immediately
    # match (maker-only constraint). ``seekPriceImprovement`` /
    # ``whatIfType`` / ``hedgeMaxSize`` parameterize specialized order
    # types. All accept ``None`` to mean "leave at server default".
    allowPreOpen: bool = False
    deactivate: bool = False
    postOnly: bool = False
    ignoreOpenAuction: bool = False
    seekPriceImprovement: int | None = None
    whatIfType: int | None = None
    hedgeMaxSize: int | None = None

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

    # Quantity / price fields that must be ``Decimal`` (or ``None``).
    # ``__post_init__`` coerces user-supplied ``float`` / ``int`` /
    # ``str`` values for these to ``Decimal`` via ``str()`` so a clean
    # ``Order(lmtPrice=50.5)`` user-construction lands the right type
    # without forcing every caller to write ``Decimal('50.5')``.
    _DECIMAL_FIELDS: ClassVar[tuple[str, ...]] = (
        "totalQuantity",
        "filledQuantity",
        "lmtPrice",
        "auxPrice",
        "trailStopPrice",
        "trailingPercent",
        "lmtPriceOffset",
        "triggerPrice",
        "adjustedStopPrice",
        "adjustedStopLimitPrice",
        "adjustedTrailingAmount",
    )

    def __post_init__(self) -> None:
        for name in self._DECIMAL_FIELDS:
            v = getattr(self, name)
            if v is None:
                continue
            # Always route through ``_toDecimal`` — even pre-coerced
            # ``Decimal`` inputs — so a stray ``Decimal('NaN')`` /
            # ``Decimal('Infinity')`` from user code lands as ``None``
            # instead of as a silently-truthy ``Decimal('NaN')`` that
            # breaks every downstream ``if order.lmtPrice:`` guard and
            # corrupts ``_decimalToWireString`` to emit ``"NaN"`` on
            # the wire.
            setattr(self, name, _toDecimal(v))


def _toDecimal(value: Decimal | float | int | str | None) -> Decimal | None:
    """Coerce a user-supplied numeric to ``Decimal | None``.

    Goes through ``str()`` for floats so binary-float imprecision (e.g.
    ``Decimal(0.1) → Decimal('0.1000000000000000055...')``) doesn't
    contaminate user-provided fractional-share quantities or option
    prices. ``None`` / ``""`` / ``float('nan')`` / ``float('inf')`` /
    ``Decimal('NaN')`` / ``Decimal('Infinity')`` all round-trip to
    ``None`` so the ``Decimal | None`` field semantics hold: ``None``
    is the unset sentinel and ``if order.lmtPrice:`` checks stay
    correct, instead of a silently-truthy ``Decimal('NaN')`` slipping
    past the guard and corrupting downstream wire writes.
    """
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        if value.is_nan() or value.is_infinite():
            return None
        return value
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if result.is_nan() or result.is_infinite():
        return None
    return result


class LimitOrder(Order):
    def __init__(
        self,
        action: str,
        totalQuantity: Decimal | float | int | str,
        lmtPrice: Decimal | float | int | str,
        **kwargs,
    ):
        Order.__init__(
            self,
            orderType="LMT",
            action=action,
            totalQuantity=_toDecimal(totalQuantity),
            lmtPrice=_toDecimal(lmtPrice),
            **kwargs,
        )


class MarketOrder(Order):
    def __init__(
        self,
        action: str,
        totalQuantity: Decimal | float | int | str,
        **kwargs,
    ):
        Order.__init__(
            self,
            orderType="MKT",
            action=action,
            totalQuantity=_toDecimal(totalQuantity),
            **kwargs,
        )


class StopOrder(Order):
    def __init__(
        self,
        action: str,
        totalQuantity: Decimal | float | int | str,
        stopPrice: Decimal | float | int | str,
        **kwargs,
    ):
        Order.__init__(
            self,
            orderType="STP",
            action=action,
            totalQuantity=_toDecimal(totalQuantity),
            auxPrice=_toDecimal(stopPrice),
            **kwargs,
        )


class StopLimitOrder(Order):
    def __init__(
        self,
        action: str,
        totalQuantity: Decimal | float | int | str,
        lmtPrice: Decimal | float | int | str,
        stopPrice: Decimal | float | int | str,
        **kwargs,
    ):
        Order.__init__(
            self,
            orderType="STP LMT",
            action=action,
            totalQuantity=_toDecimal(totalQuantity),
            lmtPrice=_toDecimal(lmtPrice),
            auxPrice=_toDecimal(stopPrice),
            **kwargs,
        )


@dataclass
class OrderStatus:
    orderId: int = 0
    status: str = ""
    # Quantity / price fields default to ``None`` so unset is falsy.
    # ``Decimal('NaN')`` would be silently truthy and break ``if filled:``
    # checks across user code.
    filled: Decimal | None = None
    remaining: Decimal | None = None
    avgFillPrice: Decimal | None = None
    permId: int = 0
    parentId: int = 0
    lastFillPrice: Decimal | None = None
    clientId: int = 0
    whyHeld: str = ""
    mktCapPrice: Decimal | None = None

    @property
    def total(self) -> Decimal | None:
        """Total size of this requested order: ``filled`` + ``remaining``.

        Returns ``None`` when either side is unset — there is no honest
        sum we can report. Callers that want a definite zero-floor
        should substitute via ``order.total or Decimal('0')``.
        """
        if self.filled is None or self.remaining is None:
            return None
        return self.filled + self.remaining

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
    Disconnected: ClassVar[str] = "Disconnected"
    ValidationError: ClassVar[str] = "ValidationError"

    # order has either been completed, cancelled, or destroyed by IBKR's risk management
    DoneStates: ClassVar[frozenset[str]] = frozenset(
        ["Filled", "Cancelled", "ApiCancelled", "Inactive"]
    )

    # Local transport loss cannot prove whether a remotely working order
    # filled, remained active, or was cancelled. Keep this distinct from
    # broker-reported Inactive, which is a terminal rejection.
    UncertainStates: ClassVar[frozenset[str]] = frozenset(["Disconnected"])

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

    # order hasn't triggered "live" yet (but it could become live and execute before we receive a notice)
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
            # If ValidationError happens on submit, the states go PreSubmitted -> ValidationError -> Submitted (if it can be ignored automatically), so order is still live.
            # If ValidationError happens on modify, the update is just ValidationError with no new Submitted, so the previous order state remains active.
            "ValidationError",
            "ApiUpdate",
        ]
    )


@dataclass(slots=True, frozen=True)
class OrderCancel:
    """CME-tagging envelope for cancelOrder + reqGlobalCancel.

    IBKR's reference cancelOrder / reqGlobalCancel take this object
    rather than scalar arguments so callers can attach the
    ``manualOrderCancelTime`` (gate 169), ``extOperator`` (gate 192),
    and ``manualOrderIndicator`` (gate 192) fields the wire protocol
    grew for CME compliance. ``None`` means unset — the wire encoder
    skips the field at send time.
    """

    manualOrderCancelTime: str = ""
    extOperator: str = ""
    manualOrderIndicator: int | None = None


@dataclass(slots=True, frozen=True)
class OrderAllocation:
    """Per-account allocation snapshot carried on an ``OrderState``
    for FA / model orders. Mirrors IBKR's reference shape.
    """

    account: str = ""
    position: Decimal | None = None
    positionDesired: Decimal | None = None
    positionAfter: Decimal | None = None
    desiredAllocQty: Decimal | None = None
    allowedAllocQty: Decimal | None = None
    isMonetary: bool = False


@dataclass
class OrderState:
    status: str = ""
    initMarginBefore: str = ""
    maintMarginBefore: str = ""
    equityWithLoanBefore: str = ""
    initMarginChange: str = ""
    maintMarginChange: str = ""
    equityWithLoanChange: str = ""
    initMarginAfter: str = ""
    maintMarginAfter: str = ""
    equityWithLoanAfter: str = ""
    # OutsideRTH variants — same str-typed margin shape, but for
    # the after-hours session window the wire reports separately.
    initMarginBeforeOutsideRTH: str = ""
    maintMarginBeforeOutsideRTH: str = ""
    equityWithLoanBeforeOutsideRTH: str = ""
    initMarginChangeOutsideRTH: str = ""
    maintMarginChangeOutsideRTH: str = ""
    equityWithLoanChangeOutsideRTH: str = ""
    initMarginAfterOutsideRTH: str = ""
    maintMarginAfterOutsideRTH: str = ""
    equityWithLoanAfterOutsideRTH: str = ""
    marginCurrency: str = ""
    # Monetary fields are ``Decimal | None`` end-to-end so user code
    # treats unset as falsy without the ``Decimal('NaN')`` truthy trap.
    # ``commissionAndFees`` is the IBKR-aligned canonical name in v3.0+;
    # ``commission`` continues to work via the deprecation alias installed
    # below (removal target: v4.0).
    commissionAndFees: Decimal | None = None
    minCommission: Decimal | None = None
    maxCommission: Decimal | None = None
    commissionCurrency: str = ""
    warningText: str = ""
    suggestedSize: Decimal | None = None
    rejectReason: str = ""
    orderAllocations: list[OrderAllocation] = field(default_factory=list)
    completedTime: str = ""
    completedStatus: str = ""

    def transform(self, transformer):
        """Convert the numeric values of this OrderState into a new OrderState transformed by 'using'"""
        return dataclasses.replace(
            self,
            initMarginBefore=transformer(self.initMarginBefore),
            maintMarginBefore=transformer(self.maintMarginBefore),
            equityWithLoanBefore=transformer(self.equityWithLoanBefore),
            initMarginChange=transformer(self.initMarginChange),
            maintMarginChange=transformer(self.maintMarginChange),
            equityWithLoanChange=transformer(self.equityWithLoanChange),
            initMarginAfter=transformer(self.initMarginAfter),
            maintMarginAfter=transformer(self.maintMarginAfter),
            equityWithLoanAfter=transformer(self.equityWithLoanAfter),
            # OutsideRTH variants — same str-typed margin shape, populated
            # from the wire alongside the non-OutsideRTH fields. Without
            # transforming them ``state.numeric()`` and ``.formatted()``
            # would silently leave them as raw strings while their
            # non-OutsideRTH siblings were converted, breaking callers
            # iterating margin fields uniformly.
            initMarginBeforeOutsideRTH=transformer(self.initMarginBeforeOutsideRTH),
            maintMarginBeforeOutsideRTH=transformer(self.maintMarginBeforeOutsideRTH),
            equityWithLoanBeforeOutsideRTH=transformer(
                self.equityWithLoanBeforeOutsideRTH
            ),
            initMarginChangeOutsideRTH=transformer(self.initMarginChangeOutsideRTH),
            maintMarginChangeOutsideRTH=transformer(self.maintMarginChangeOutsideRTH),
            equityWithLoanChangeOutsideRTH=transformer(
                self.equityWithLoanChangeOutsideRTH
            ),
            initMarginAfterOutsideRTH=transformer(self.initMarginAfterOutsideRTH),
            maintMarginAfterOutsideRTH=transformer(self.maintMarginAfterOutsideRTH),
            equityWithLoanAfterOutsideRTH=transformer(
                self.equityWithLoanAfterOutsideRTH
            ),
            commissionAndFees=transformer(self.commissionAndFees),
            minCommission=transformer(self.minCommission),
            maxCommission=transformer(self.maxCommission),
        )

    def numeric(self, digits: int = 2) -> OrderStateNumeric:
        """Return a new OrderState with the current values values to floats instead of strings as returned from IBKR directly."""

        def floatOrNone(what, precision) -> float | None:
            """Attempt to convert input to a float, but if we fail (value is just empty string) return None"""
            try:
                # convert
                floated = float(what)

                # if the conversion is IBKR speak for "this value is not set" then give us None
                if floated == UNSET_DOUBLE:
                    return None

                # else, round to the requested precision
                return round(floated, precision)
            except Exception as _:
                # initial conversion failed so just return None in its place
                return None

        return self.transform(lambda x: floatOrNone(x, digits))

    def formatted(self, digits: int = 2):
        """Return a new OrderState with the current values as formatted strings."""
        return self.numeric(8).transform(
            # 300000.21 -> 300,000.21
            # 0.0 -> 0.00
            # 431.342000000001 -> 431.34
            # Note: we need 'is not None' here because 'x=0' is a valid numeric input too
            lambda x: f"{x:,.{digits}f}" if x is not None else None
        )


@dataclass
class OrderStateNumeric(OrderState):
    """Just a type helper for mypy to check against if you convert OrderState to .numeric().

    Usage:

    state_numeric: OrderStateNumeric = state.numeric(digits=2)"""

    initMarginBefore: float | None = None  # type: ignore[assignment]
    maintMarginBefore: float | None = None  # type: ignore[assignment]
    equityWithLoanBefore: float | None = None  # type: ignore[assignment]
    initMarginChange: float | None = None  # type: ignore[assignment]
    maintMarginChange: float | None = None  # type: ignore[assignment]
    equityWithLoanChange: float | None = None  # type: ignore[assignment]
    initMarginAfter: float | None = None  # type: ignore[assignment]
    maintMarginAfter: float | None = None  # type: ignore[assignment]
    equityWithLoanAfter: float | None = None  # type: ignore[assignment]
    initMarginBeforeOutsideRTH: float | None = None  # type: ignore[assignment]
    maintMarginBeforeOutsideRTH: float | None = None  # type: ignore[assignment]
    equityWithLoanBeforeOutsideRTH: float | None = None  # type: ignore[assignment]
    initMarginChangeOutsideRTH: float | None = None  # type: ignore[assignment]
    maintMarginChangeOutsideRTH: float | None = None  # type: ignore[assignment]
    equityWithLoanChangeOutsideRTH: float | None = None  # type: ignore[assignment]
    initMarginAfterOutsideRTH: float | None = None  # type: ignore[assignment]
    maintMarginAfterOutsideRTH: float | None = None  # type: ignore[assignment]
    equityWithLoanAfterOutsideRTH: float | None = None  # type: ignore[assignment]
    commissionAndFees: float | None = None  # type: ignore[assignment]
    minCommission: float | None = None  # type: ignore[assignment]
    maxCommission: float | None = None  # type: ignore[assignment]


# Install legacy ``commission`` deprecation alias on both ``OrderState``
# and ``OrderStateNumeric``. v2.x callers that read or set
# ``state.commission`` continue to work but emit ``DeprecationWarning``;
# the alias is slated for removal in v4.0. The same helper is applied to
# ``CommissionReport`` in ``objects.py``.
_install_commission_alias(OrderState)
_install_commission_alias(OrderStateNumeric)


@dataclass
class OrderComboLeg:
    price: Decimal | None = None


# Trade is deliberately not @dataclass(slots=True). __post_init__ assigns
# seven Event attributes that would first need to become declared fields
# with a ``created`` guard (see ``Ticker`` for the pattern), and slot
# enforcement would break user code that attaches arbitrary attributes to
# Trade instances for application-side bookkeeping.
@dataclass
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

    # Most recent unmerged TWS-authored snapshot of this order's state.
    # ``order`` is updated through the MUTABLE_ORDER_FIELDS allowlist in
    # ``Wrapper.openOrder`` to keep user-set fields safe from TWS
    # placeholder values; ``serverOrder`` is the raw TWS view, so callers
    # who need a field that isn't in the allowlist can still read it
    # without waiting for the allowlist to grow. ``None`` until the first
    # ``openOrder`` callback for this trade.
    serverOrder: Order | None = None

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
        """True if the order is live and "working" at the broker against
        public exchanges (e.g. Submitted)."""
        return self.orderStatus.status in OrderStatus.WorkingStates

    def isActive(self) -> bool:
        """True if eligible for execution, false otherwise."""
        return self.orderStatus.status in OrderStatus.ActiveStates

    def isDone(self) -> bool:
        """True if completely filled or cancelled, false otherwise."""
        return self.orderStatus.status in OrderStatus.DoneStates

    def isUncertain(self) -> bool:
        """True when local state cannot prove the broker order outcome."""
        return self.orderStatus.status in OrderStatus.UncertainStates

    def filled(self) -> Decimal:
        """Number of shares filled across all observed executions.

        Returns ``Decimal('0')`` when no fills exist or none have a
        share quantity yet — never ``None``, since "the trade has
        zero shares filled so far" is a definite answer that user
        code can do arithmetic on.
        """
        fills = self.fills
        if self.contract.secType == "BAG":
            # don't count fills for the leg contracts
            fills = [f for f in fills if f.contract.secType == "BAG"]

        total = Decimal(0)
        for f in fills:
            shares = f.execution.shares
            if shares is not None:
                total += shares
        return total

    def remaining(self) -> Decimal:
        """Number of shares remaining to be filled.

        Returns ``Decimal('0')`` when ``order.totalQuantity`` is
        unset — there is no honest non-zero "remaining" to report
        without a known total. Negative outcomes (over-fill) propagate
        unchanged.
        """
        total = self.order.totalQuantity
        if total is None:
            return Decimal(0)
        return total - self.filled()


class BracketOrder(NamedTuple):
    parent: Order
    takeProfit: Order
    stopLoss: Order


@dataclass
class OrderCondition:
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


@dataclass
class PriceCondition(OrderCondition):
    condType: int = 1
    conjunction: str = "a"
    isMore: bool = True
    price: float = 0.0
    conId: int = 0
    exch: str = ""
    triggerMethod: int = 0


@dataclass
class TimeCondition(OrderCondition):
    condType: int = 3
    conjunction: str = "a"
    isMore: bool = True
    time: str = ""


@dataclass
class MarginCondition(OrderCondition):
    condType: int = 4
    conjunction: str = "a"
    isMore: bool = True
    percent: int = 0


@dataclass
class ExecutionCondition(OrderCondition):
    condType: int = 5
    conjunction: str = "a"
    secType: str = ""
    exch: str = ""
    symbol: str = ""


@dataclass
class VolumeCondition(OrderCondition):
    condType: int = 6
    conjunction: str = "a"
    isMore: bool = True
    volume: int = 0
    conId: int = 0
    exch: str = ""


@dataclass
class PercentChangeCondition(OrderCondition):
    condType: int = 7
    conjunction: str = "a"
    isMore: bool = True
    changePercent: float = 0.0
    conId: int = 0
    exch: str = ""
