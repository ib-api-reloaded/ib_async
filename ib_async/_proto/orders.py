"""Protobuf converters for orders, executions, and commissions.

Pure functions: every converter takes only proto inputs (or domain
inputs on the send side). No reads from module-level state, no
dependencies on ``Wrapper``. Decimal fields use ``safe_decimal``;
unset values land as ``None`` so user code's ``if order.lmtPrice:``
keeps working.

The send-side ``create*Proto`` helpers always read from the source
domain object — never from the freshly-empty target proto. That
discipline guards against the contributor's upstream PR bug where
``createOrderProto`` had ``if isValidIntValue(order.clientId):
order.clientId = order.clientId`` (note ``=`` self-assignment) and
silently dropped ``clientId`` from every outbound order. The
``test_orders_proto_round_trips_clientId`` regression test exercises
that exact path.
"""

from __future__ import annotations

from decimal import Decimal

from .._pb import (
    AllOpenOrdersRequest_pb2,
    AttachedOrders_pb2,
    AutoOpenOrdersRequest_pb2,
    CancelOrderRequest_pb2,
    CommissionAndFeesReport_pb2,
    CompletedOrder_pb2,
    CompletedOrdersRequest_pb2,
    Contract_pb2,
    Execution_pb2,
    ExecutionDetails_pb2,
    ExecutionFilter_pb2,
    ExecutionRequest_pb2,
    GlobalCancelRequest_pb2,
    OpenOrder_pb2,
    OpenOrdersRequest_pb2,
    Order_pb2,
    OrderCancel_pb2,
    OrderCondition_pb2,
    OrderState_pb2,
    OrderStatus_pb2,
    PlaceOrderRequest_pb2,
    SoftDollarTier_pb2,
)
from ..contract import Contract, TagValue
from ..objects import CommissionReport, Execution, ExecutionFilter, SoftDollarTier
from ..order import (
    ExecutionCondition,
    MarginCondition,
    Order,
    OrderAllocation,
    OrderComboLeg,
    OrderCondition,
    OrderState,
    OrderStatus,
    PercentChangeCondition,
    PriceCondition,
    TimeCondition,
    VolumeCondition,
)
from ..util import UNSET_INTEGER
from .contracts import createContract, createContractProto
from .safe import (
    is_valid_decimal as _isValidDecimal,
)
from .safe import (
    is_valid_float as _isValidFloat,
)
from .safe import (
    is_valid_int as _isValidInt,
)
from .safe import (
    is_valid_long as _isValidLong,
)
from .safe import (
    safe_decimal,
)


def _decimalToWireString(value: Decimal | None) -> str:
    """Serialize a Decimal to the canonical IBKR wire string form, or
    empty string when unset. Matches what the binary protocol historically
    sent (no trailing zeros, no ``"NaN"``)."""
    if value is None:
        return ""
    # Decimal's default str() preserves the original representation, so
    # ``Decimal('100')`` round-trips as ``"100"`` and ``Decimal('0.5')``
    # as ``"0.5"`` — exactly what IBKR's wire format wants.
    return str(value)


# --- Order ---------------------------------------------------------------


def _fillTagValueMap(items: list[TagValue] | None, target: object) -> None:
    """Copy a domain ``list[TagValue]`` into a proto ``map<string,string>``.

    Mirrors IBKR's ``fillTagValueList`` helper. Empty / ``None`` lists
    leave the target untouched so the field stays unset on the wire.
    The target arg is a ``ScalarMap[str, str]`` from the parent proto;
    typed as ``object`` here because the protobuf generated stubs don't
    expose a public name we can import.
    """
    if not items:
        return
    for tv in items:
        target[tv.tag] = tv.value  # type: ignore[index]


def _parseTagValueList(source: object) -> list[TagValue]:
    """Decode a proto ``map<string,string>`` into a domain
    ``list[TagValue]``. Mirrors IBKR's ``decodeTagValueList``.

    The source arg is a ``ScalarMap[str, str]`` from the parent proto;
    typed as ``object`` here because the protobuf generated stubs don't
    expose a public name we can import.
    """
    if not source:
        return []
    out: list[TagValue] = []
    for tag, value in source.items():  # type: ignore[attr-defined]
        out.append(TagValue(tag=tag, value=value))
    return out


def createOrderProto(order: Order) -> Order_pb2.Order:
    """Encode a domain ``Order`` into its protobuf representation.

    Mirrors IBKR's ``client_utils.createOrderProto`` field-by-field so
    the wire payload carries every order parameter the server expects.
    The previous implementation only wrote ~30 of ~140 fields — most
    catastrophically dropping ``transmit`` (domain default ``True``),
    which made every outbound protobuf-path order land as a
    non-transmitted staged order on the broker.

    Domain fields that exist in IBKR's reference but are NOT on our
    ``Order`` dataclass (``customerAccount``, ``professionalCustomer``,
    ``bondAccruedInterest``, ``includeOvernight``, ``submitter``,
    ``deactivate``, ``postOnly``, ``allowPreOpen``, ``ignoreOpenAuction``,
    ``seekPriceImprovement``, ``whatIfType``, ``hedgeMaxSize``) are
    silently skipped — adding them here without dataclass support would
    invent fields user code can never set. Order proto schema gaps:
    none — every IBKR-reference field maps to an Order_pb2 field at
    this proto version.
    """
    proto = Order_pb2.Order()

    # Order ids — set even at zero where IBKR treats zero as a valid
    # identifier. ``clientId`` MUST round-trip; the contributor's PR
    # had a typo here that silently dropped it from every outbound
    # order, sending fills to the wrong client bucket. IBKR's reference
    # uses ``isValidIntValue`` (≠ UNSET sentinel) so ``0`` flows through.
    if _isValidInt(order.clientId):
        proto.clientId = order.clientId
    if order.orderId:
        proto.orderId = order.orderId
    if _isValidLong(order.permId):
        proto.permId = order.permId
    if _isValidInt(order.parentId):
        proto.parentId = order.parentId

    # Primary attributes
    if order.action:
        proto.action = order.action
    if _isValidDecimal(order.totalQuantity):
        proto.totalQuantity = _decimalToWireString(order.totalQuantity)
    if _isValidInt(order.displaySize):
        proto.displaySize = order.displaySize
    if order.orderType:
        proto.orderType = order.orderType
    if _isValidFloat(order.lmtPrice):
        proto.lmtPrice = float(order.lmtPrice)
    if _isValidFloat(order.auxPrice):
        proto.auxPrice = float(order.auxPrice)
    if order.tif:
        proto.tif = order.tif

    # Clearing info
    if order.account:
        proto.account = order.account
    if order.settlingFirm:
        proto.settlingFirm = order.settlingFirm
    if order.clearingAccount:
        proto.clearingAccount = order.clearingAccount
    if order.clearingIntent:
        proto.clearingIntent = order.clearingIntent

    # Secondary attributes
    if order.allOrNone:
        proto.allOrNone = order.allOrNone
    if order.blockOrder:
        proto.blockOrder = order.blockOrder
    if order.hidden:
        proto.hidden = order.hidden
    if order.outsideRth:
        proto.outsideRth = order.outsideRth
    if order.sweepToFill:
        proto.sweepToFill = order.sweepToFill
    if _isValidFloat(order.percentOffset):
        proto.percentOffset = float(order.percentOffset)
    if _isValidFloat(order.trailingPercent):
        proto.trailingPercent = float(order.trailingPercent)
    if _isValidFloat(order.trailStopPrice):
        proto.trailStopPrice = float(order.trailStopPrice)
    # ``minQty`` defaults to UNSET_INTEGER in our domain — guarding with
    # ``if order.minQty:`` would always write the sentinel value to the
    # wire (UNSET_INTEGER is truthy). Use the explicit unset check.
    if _isValidInt(order.minQty):
        proto.minQty = order.minQty
    if order.goodAfterTime:
        proto.goodAfterTime = order.goodAfterTime
    if order.goodTillDate:
        proto.goodTillDate = order.goodTillDate
    if order.ocaGroup:
        proto.ocaGroup = order.ocaGroup
    if order.orderRef:
        proto.orderRef = order.orderRef
    if order.rule80A:
        proto.rule80A = order.rule80A
    if _isValidInt(order.ocaType):
        proto.ocaType = order.ocaType
    if _isValidInt(order.triggerMethod):
        proto.triggerMethod = order.triggerMethod

    # Extended order fields
    if order.activeStartTime:
        proto.activeStartTime = order.activeStartTime
    if order.activeStopTime:
        proto.activeStopTime = order.activeStopTime

    # Advisor allocation
    if order.faGroup:
        proto.faGroup = order.faGroup
    if order.faMethod:
        proto.faMethod = order.faMethod
    if order.faPercentage:
        proto.faPercentage = order.faPercentage

    # Volatility family (defaults to UNSET sentinels — must guard
    # explicitly against the sentinel rather than truthy-zero).
    if _isValidFloat(order.volatility):
        proto.volatility = float(order.volatility)
    if _isValidInt(order.volatilityType):
        proto.volatilityType = order.volatilityType
    if order.continuousUpdate:
        proto.continuousUpdate = order.continuousUpdate
    if _isValidInt(order.referencePriceType):
        proto.referencePriceType = order.referencePriceType

    # Delta-neutral family
    if order.deltaNeutralOrderType:
        proto.deltaNeutralOrderType = order.deltaNeutralOrderType
    if _isValidFloat(order.deltaNeutralAuxPrice):
        proto.deltaNeutralAuxPrice = float(order.deltaNeutralAuxPrice)
    if _isValidInt(order.deltaNeutralConId):
        proto.deltaNeutralConId = order.deltaNeutralConId
    if order.deltaNeutralOpenClose:
        proto.deltaNeutralOpenClose = order.deltaNeutralOpenClose
    if order.deltaNeutralShortSale:
        proto.deltaNeutralShortSale = order.deltaNeutralShortSale
    if _isValidInt(order.deltaNeutralShortSaleSlot):
        proto.deltaNeutralShortSaleSlot = order.deltaNeutralShortSaleSlot
    if order.deltaNeutralDesignatedLocation:
        proto.deltaNeutralDesignatedLocation = order.deltaNeutralDesignatedLocation

    # Scale family — all default to UNSET sentinels.
    if _isValidInt(order.scaleInitLevelSize):
        proto.scaleInitLevelSize = order.scaleInitLevelSize
    if _isValidInt(order.scaleSubsLevelSize):
        proto.scaleSubsLevelSize = order.scaleSubsLevelSize
    if _isValidFloat(order.scalePriceIncrement):
        proto.scalePriceIncrement = float(order.scalePriceIncrement)
    if _isValidFloat(order.scalePriceAdjustValue):
        proto.scalePriceAdjustValue = float(order.scalePriceAdjustValue)
    if _isValidInt(order.scalePriceAdjustInterval):
        proto.scalePriceAdjustInterval = order.scalePriceAdjustInterval
    if _isValidFloat(order.scaleProfitOffset):
        proto.scaleProfitOffset = float(order.scaleProfitOffset)
    if order.scaleAutoReset:
        proto.scaleAutoReset = order.scaleAutoReset
    if _isValidInt(order.scaleInitPosition):
        proto.scaleInitPosition = order.scaleInitPosition
    if _isValidInt(order.scaleInitFillQty):
        proto.scaleInitFillQty = order.scaleInitFillQty
    if order.scaleRandomPercent:
        proto.scaleRandomPercent = order.scaleRandomPercent
    if order.scaleTable:
        proto.scaleTable = order.scaleTable

    # Hedge
    if order.hedgeType:
        proto.hedgeType = order.hedgeType
    if order.hedgeParam:
        proto.hedgeParam = order.hedgeParam

    # Algo
    if order.algoStrategy:
        proto.algoStrategy = order.algoStrategy
    _fillTagValueMap(order.algoParams, proto.algoParams)
    if order.algoId:
        proto.algoId = order.algoId

    # Smart combo routing
    _fillTagValueMap(order.smartComboRoutingParams, proto.smartComboRoutingParams)

    # CRITICAL: ``transmit`` defaults to True in the domain. If we don't
    # write it through, the server treats absent==False and stages every
    # order without transmitting. The bool-truthy guard mirrors IBKR's
    # reference and lets users override to False (proto3 default-False
    # then leaves the field unset, which the server reads as not
    # transmitted — the desired behavior for staged-order workflows).
    if order.whatIf:
        proto.whatIf = order.whatIf
    if order.transmit:
        proto.transmit = order.transmit
    if order.overridePercentageConstraints:
        proto.overridePercentageConstraints = order.overridePercentageConstraints

    # Open / close + origin
    if order.openClose:
        proto.openClose = order.openClose
    if _isValidInt(order.origin):
        proto.origin = order.origin
    if _isValidInt(order.shortSaleSlot):
        proto.shortSaleSlot = order.shortSaleSlot
    if order.designatedLocation:
        proto.designatedLocation = order.designatedLocation
    # ``exemptCode`` defaults to ``-1`` in our domain (a real wire value
    # meaning "not exempt"). IBKR's reference uses ``isValidIntValue``;
    # since ``-1`` is not the UNSET_INTEGER sentinel the field is
    # always written, which matches IBKR's behavior.
    if _isValidInt(order.exemptCode):
        proto.exemptCode = order.exemptCode

    # Delta-neutral clearing
    if order.deltaNeutralSettlingFirm:
        proto.deltaNeutralSettlingFirm = order.deltaNeutralSettlingFirm
    if order.deltaNeutralClearingAccount:
        proto.deltaNeutralClearingAccount = order.deltaNeutralClearingAccount
    if order.deltaNeutralClearingIntent:
        proto.deltaNeutralClearingIntent = order.deltaNeutralClearingIntent

    # Discretionary + smart-routing opt-out
    if _isValidFloat(order.discretionaryAmt):
        proto.discretionaryAmt = order.discretionaryAmt
    if order.optOutSmartRouting:
        proto.optOutSmartRouting = order.optOutSmartRouting

    # Box / volatility-style auction extras (UNSET_DOUBLE defaults)
    if _isValidFloat(order.startingPrice):
        proto.startingPrice = float(order.startingPrice)
    if _isValidFloat(order.stockRefPrice):
        proto.stockRefPrice = float(order.stockRefPrice)
    if _isValidFloat(order.delta):
        proto.delta = float(order.delta)
    if _isValidFloat(order.stockRangeLower):
        proto.stockRangeLower = float(order.stockRangeLower)
    if _isValidFloat(order.stockRangeUpper):
        proto.stockRangeUpper = float(order.stockRangeUpper)

    if order.notHeld:
        proto.notHeld = order.notHeld

    # Misc options bag
    _fillTagValueMap(order.orderMiscOptions, proto.orderMiscOptions)

    if order.solicited:
        proto.solicited = order.solicited
    if order.randomizeSize:
        proto.randomizeSize = order.randomizeSize
    if order.randomizePrice:
        proto.randomizePrice = order.randomizePrice

    # Pegged-to-benchmark family
    if _isValidInt(order.referenceContractId):
        proto.referenceContractId = order.referenceContractId
    if _isValidFloat(order.peggedChangeAmount):
        proto.peggedChangeAmount = order.peggedChangeAmount
    if order.isPeggedChangeAmountDecrease:
        proto.isPeggedChangeAmountDecrease = order.isPeggedChangeAmountDecrease
    if _isValidFloat(order.referenceChangeAmount):
        proto.referenceChangeAmount = order.referenceChangeAmount
    if order.referenceExchangeId:
        proto.referenceExchangeId = order.referenceExchangeId

    # Adjustable orders
    if order.adjustedOrderType:
        proto.adjustedOrderType = order.adjustedOrderType
    if _isValidFloat(order.triggerPrice):
        proto.triggerPrice = float(order.triggerPrice)
    if _isValidFloat(order.adjustedStopPrice):
        proto.adjustedStopPrice = float(order.adjustedStopPrice)
    if _isValidFloat(order.adjustedStopLimitPrice):
        proto.adjustedStopLimitPrice = float(order.adjustedStopLimitPrice)
    if _isValidFloat(order.adjustedTrailingAmount):
        proto.adjustedTrailingAmount = float(order.adjustedTrailingAmount)
    if _isValidInt(order.adjustableTrailingUnit):
        proto.adjustableTrailingUnit = order.adjustableTrailingUnit
    if _isValidFloat(order.lmtPriceOffset):
        proto.lmtPriceOffset = float(order.lmtPriceOffset)

    # Conditions
    conditionProtos = _createConditionProtos(order.conditions)
    if conditionProtos:
        proto.conditions.extend(conditionProtos)
    if order.conditionsCancelOrder:
        proto.conditionsCancelOrder = order.conditionsCancelOrder
    if order.conditionsIgnoreRth:
        proto.conditionsIgnoreRth = order.conditionsIgnoreRth

    if order.modelCode:
        proto.modelCode = order.modelCode
    if order.extOperator:
        proto.extOperator = order.extOperator

    # Soft-dollar tier (composite). Only emit when the domain object
    # carries actual data — its ``__bool__`` is False on a default
    # instance.
    if order.softDollarTier:
        sdt = SoftDollarTier_pb2.SoftDollarTier()
        if order.softDollarTier.name:
            sdt.name = order.softDollarTier.name
        # Domain field is ``val`` (legacy spelling); proto field is ``value``.
        if order.softDollarTier.val:
            sdt.value = order.softDollarTier.val
        if order.softDollarTier.displayName:
            sdt.displayName = order.softDollarTier.displayName
        proto.softDollarTier.CopyFrom(sdt)

    # Cash-quantity orders
    if _isValidFloat(order.cashQty):
        proto.cashQty = float(order.cashQty)

    # MIFID II
    if order.mifid2DecisionMaker:
        proto.mifid2DecisionMaker = order.mifid2DecisionMaker
    if order.mifid2DecisionAlgo:
        proto.mifid2DecisionAlgo = order.mifid2DecisionAlgo
    if order.mifid2ExecutionTrader:
        proto.mifid2ExecutionTrader = order.mifid2ExecutionTrader
    if order.mifid2ExecutionAlgo:
        proto.mifid2ExecutionAlgo = order.mifid2ExecutionAlgo

    if order.dontUseAutoPriceForHedge:
        proto.dontUseAutoPriceForHedge = order.dontUseAutoPriceForHedge
    if order.isOmsContainer:
        proto.isOmsContainer = order.isOmsContainer
    if order.discretionaryUpToLimitPrice:
        proto.discretionaryUpToLimitPrice = order.discretionaryUpToLimitPrice

    # ``usePriceMgmtAlgo`` is wire-int (0/1/UNSET) but our domain types
    # it as ``bool``. Mirror IBKR's convention: write 1/0 when the bool
    # is set to a truthy/falsy value. Domain default ``False`` would
    # otherwise leave the field absent and mean "use server default".
    if order.usePriceMgmtAlgo:
        proto.usePriceMgmtAlgo = 1

    # ``duration`` and ``postToAts`` default to UNSET_INTEGER.
    if _isValidInt(order.duration):
        proto.duration = order.duration
    if _isValidInt(order.postToAts):
        proto.postToAts = order.postToAts

    if order.advancedErrorOverride:
        proto.advancedErrorOverride = order.advancedErrorOverride
    if order.manualOrderTime:
        proto.manualOrderTime = order.manualOrderTime
    if _isValidInt(order.manualOrderIndicator):
        proto.manualOrderIndicator = order.manualOrderIndicator

    # Mid-price competition family (UNSET sentinels)
    if _isValidInt(order.minTradeQty):
        proto.minTradeQty = order.minTradeQty
    if _isValidInt(order.minCompeteSize):
        proto.minCompeteSize = order.minCompeteSize
    if _isValidFloat(order.competeAgainstBestOffset):
        proto.competeAgainstBestOffset = float(order.competeAgainstBestOffset)
    if _isValidFloat(order.midOffsetAtWhole):
        proto.midOffsetAtWhole = float(order.midOffsetAtWhole)
    if _isValidFloat(order.midOffsetAtHalf):
        proto.midOffsetAtHalf = float(order.midOffsetAtHalf)

    # Auto-cancel + parent-perm wiring
    if order.autoCancelDate:
        proto.autoCancelDate = order.autoCancelDate
    if order.autoCancelParent:
        proto.autoCancelParent = order.autoCancelParent
    if order.parentPermId:
        proto.parentPermId = order.parentPermId

    # Misc bool / id extras
    if order.shareholder:
        proto.shareholder = order.shareholder
    if order.imbalanceOnly:
        proto.imbalanceOnly = order.imbalanceOnly
    # ``routeMarketableToBbo`` is wire-int (0/1) but domain-bool. Same
    # 1/0 mapping as ``usePriceMgmtAlgo``.
    if order.routeMarketableToBbo:
        proto.routeMarketableToBbo = 1
    if order.refFuturesConId:
        proto.refFuturesConId = order.refFuturesConId
    # ``filledQuantity`` is wire-string (Decimal). Encode same as
    # ``totalQuantity``.
    if order.filledQuantity is not None:
        proto.filledQuantity = _decimalToWireString(order.filledQuantity)

    return proto


def _createConditionProtos(
    conditions: list[OrderCondition] | None,
) -> list[OrderCondition_pb2.OrderCondition]:
    """Encode our domain ``OrderCondition`` subclasses into the wire
    proto's flat ``OrderCondition`` shape.

    The wire proto carries every possible condition field on a single
    flat message and uses ``type`` + ``isMore`` etc. to pick which
    fields are meaningful — mirrors how IBKR's reference
    ``createConditionsProto`` writes them. Subclass-specific fields
    that aren't on a given condition are simply not set.
    """
    if not conditions:
        return []
    out: list[OrderCondition_pb2.OrderCondition] = []
    for c in conditions:
        cp = OrderCondition_pb2.OrderCondition()
        # ``OrderCondition`` is the abstract base — subclass-specific
        # fields (``condType`` / ``isMore`` / ``price`` / ...) are read
        # via ``getattr`` so mypy doesn't complain about the base
        # missing them, and a hand-rolled subclass without one of these
        # attrs simply skips it instead of crashing.
        condType = getattr(c, "condType", 0)
        if condType:
            cp.type = condType
        # ``conjunction`` is "a" / "o" in the domain; wire is bool.
        cp.isConjunctionConnection = getattr(c, "conjunction", "a") == "a"
        isMore = getattr(c, "isMore", None)
        if isMore is not None:
            cp.isMore = isMore
        conId = getattr(c, "conId", 0)
        if conId:
            cp.conId = conId
        exch = getattr(c, "exch", "")
        if exch:
            cp.exchange = exch
        symbol = getattr(c, "symbol", "")
        if symbol:
            cp.symbol = symbol
        secType = getattr(c, "secType", "")
        if secType:
            cp.secType = secType
        percent = getattr(c, "percent", 0)
        if percent:
            cp.percent = percent
        changePercent = getattr(c, "changePercent", 0)
        if changePercent:
            cp.changePercent = changePercent
        price = getattr(c, "price", 0)
        if price:
            cp.price = price
        # ``triggerMethod`` value 0 means "Default" — a valid wire
        # value that IBKR's reference encoder writes via
        # ``isValidIntValue``. Only treat the UNSET_INTEGER sentinel as
        # "skip"; a 0 must still be written so the server doesn't fall
        # back to its own default unexpectedly.
        condTriggerMethod = getattr(c, "triggerMethod", UNSET_INTEGER)
        if _isValidInt(condTriggerMethod):
            cp.triggerMethod = condTriggerMethod
        time = getattr(c, "time", "")
        if time:
            cp.time = time
        volume = getattr(c, "volume", 0)
        if volume:
            cp.volume = volume
        out.append(cp)
    return out


_CONDITION_CLASSES: dict[int, type[OrderCondition]] = {
    1: PriceCondition,
    3: TimeCondition,
    4: MarginCondition,
    5: ExecutionCondition,
    6: VolumeCondition,
    7: PercentChangeCondition,
}


def _decodeConditions(
    proto: Order_pb2.Order,
) -> list[OrderCondition]:
    """Mirror IBKR's ``decodeConditions`` — a flat repeated proto with
    a ``type`` discriminator dispatches to the per-subclass field set.
    Unknown ``type`` values are silently skipped (matches the reference).
    """
    out: list[OrderCondition] = []
    for cp in proto.conditions:
        condType = cp.type if cp.HasField("type") else 0
        cls = _CONDITION_CLASSES.get(condType)
        if cls is None:
            continue
        c: OrderCondition = cls()
        # Domain ``conjunction`` is "a"/"o"; wire is bool. Default to "a"
        # when the wire didn't ship a value — matches the dataclass
        # default and keeps behavior stable across older proto payloads.
        if cp.HasField("isConjunctionConnection"):
            c.conjunction = "a" if cp.isConjunctionConnection else "o"  # type: ignore[attr-defined]
        if cp.HasField("isMore") and hasattr(c, "isMore"):
            c.isMore = cp.isMore  # type: ignore[attr-defined]
        if cp.HasField("conId") and hasattr(c, "conId"):
            c.conId = cp.conId  # type: ignore[attr-defined]
        # Wire field is ``exchange``; domain attribute is ``exch``.
        if cp.HasField("exchange") and hasattr(c, "exch"):
            c.exch = cp.exchange  # type: ignore[attr-defined]
        if cp.HasField("symbol") and hasattr(c, "symbol"):
            c.symbol = cp.symbol  # type: ignore[attr-defined]
        if cp.HasField("secType") and hasattr(c, "secType"):
            c.secType = cp.secType  # type: ignore[attr-defined]
        if cp.HasField("percent") and hasattr(c, "percent"):
            c.percent = cp.percent  # type: ignore[attr-defined]
        if cp.HasField("changePercent") and hasattr(c, "changePercent"):
            c.changePercent = cp.changePercent  # type: ignore[attr-defined]
        if cp.HasField("price") and hasattr(c, "price"):
            c.price = cp.price  # type: ignore[attr-defined]
        if cp.HasField("triggerMethod") and hasattr(c, "triggerMethod"):
            c.triggerMethod = cp.triggerMethod  # type: ignore[attr-defined]
        if cp.HasField("time") and hasattr(c, "time"):
            c.time = cp.time  # type: ignore[attr-defined]
        if cp.HasField("volume") and hasattr(c, "volume"):
            c.volume = cp.volume  # type: ignore[attr-defined]
        out.append(c)
    return out


def _decodeSoftDollarTier(proto: Order_pb2.Order) -> SoftDollarTier | None:
    """Mirror IBKR's ``decodeSoftDollarTierFromOrder``. Wire field is
    ``value``; domain attribute is the legacy spelling ``val``.
    Returns ``None`` when the embedded message carries no fields, so
    the caller leaves the dataclass default in place.
    """
    if not proto.HasField("softDollarTier"):
        return None
    sdt = proto.softDollarTier
    name = sdt.name if sdt.HasField("name") else ""
    val = sdt.value if sdt.HasField("value") else ""
    displayName = sdt.displayName if sdt.HasField("displayName") else ""
    if not (name or val or displayName):
        return None
    return SoftDollarTier(name=name, val=val, displayName=displayName)


def _decodeOrderComboLegs(
    contractProto: Contract_pb2.Contract | None,
) -> list[OrderComboLeg]:
    """Mirror IBKR's ``decodeOrderComboLegs`` — combo-leg per-leg prices
    live on the contract proto's ``comboLegs`` list, NOT the order
    proto. Returns an empty list when the contract proto is absent
    (e.g. the caller didn't propagate it).
    """
    if contractProto is None:
        return []
    out: list[OrderComboLeg] = []
    for legProto in contractProto.comboLegs:
        leg = OrderComboLeg()
        if legProto.HasField("perLegPrice"):
            leg.price = legProto.perLegPrice
        out.append(leg)
    return out


def createOrder(
    proto: Order_pb2.Order,
    contractProto: Contract_pb2.Contract | None = None,
    orderId: int | None = None,
) -> Order:
    """Decode a protobuf ``Order`` into our domain dataclass.

    Mirrors IBKR's ``decoder_utils.decodeOrder`` field-by-field. The
    ``contractProto`` arg carries the matching ``Contract`` message so
    we can mirror IBKR's ``decodeOrderComboLegs`` (per-leg prices live
    on the contract, not the order). The ``orderId`` arg lets the
    envelope-level decoder propagate the wrapping message's orderId
    when the inner order proto omits it.

    Compliance / origination fields IBKR added in the 195-198 gate
    window (``customerAccount``, ``professionalCustomer``,
    ``bondAccruedInterest``, ``includeOvernight``, ``manualOrderIndicator``,
    ``submitter``) land on the corresponding ``Order`` dataclass
    fields. Other reference fields not currently modelled on
    ``Order`` (``deactivate``, ``postOnly``, ``allowPreOpen``,
    ``ignoreOpenAuction``, ``seekPriceImprovement``, ``whatIfType``,
    ``hedgeMaxSize``) are not surfaced here because the dataclass
    has no slot for them — silently swallowing the wire data would
    just hide user-invisible state.
    """
    order = Order()

    # Order ids
    if orderId is not None:
        order.orderId = orderId
    if proto.HasField("orderId"):
        order.orderId = proto.orderId
    if proto.HasField("clientId"):
        order.clientId = proto.clientId
    if proto.HasField("permId"):
        order.permId = proto.permId
    if proto.HasField("parentId"):
        order.parentId = proto.parentId

    # Primary attributes
    if proto.HasField("action"):
        order.action = proto.action
    if proto.HasField("totalQuantity"):
        order.totalQuantity = safe_decimal(proto.totalQuantity)
    if proto.HasField("displaySize"):
        order.displaySize = proto.displaySize
    if proto.HasField("orderType"):
        order.orderType = proto.orderType
    if proto.HasField("lmtPrice"):
        # ``safe_decimal`` routes float input through str() internally
        # so binary-float imprecision does not contaminate user-set
        # fractional prices.
        order.lmtPrice = safe_decimal(proto.lmtPrice)
    if proto.HasField("auxPrice"):
        order.auxPrice = safe_decimal(proto.auxPrice)
    if proto.HasField("tif"):
        order.tif = proto.tif

    # Clearing / account info
    if proto.HasField("ocaGroup"):
        order.ocaGroup = proto.ocaGroup
    if proto.HasField("account"):
        order.account = proto.account
    if proto.HasField("openClose"):
        order.openClose = proto.openClose
    if proto.HasField("origin"):
        order.origin = proto.origin
    if proto.HasField("orderRef"):
        order.orderRef = proto.orderRef
    if proto.HasField("outsideRth"):
        order.outsideRth = proto.outsideRth
    if proto.HasField("hidden"):
        order.hidden = proto.hidden
    if proto.HasField("discretionaryAmt"):
        order.discretionaryAmt = proto.discretionaryAmt
    if proto.HasField("goodAfterTime"):
        order.goodAfterTime = proto.goodAfterTime

    # Advisor allocation
    if proto.HasField("faGroup"):
        order.faGroup = proto.faGroup
    if proto.HasField("faMethod"):
        order.faMethod = proto.faMethod
    if proto.HasField("faPercentage"):
        order.faPercentage = proto.faPercentage

    if proto.HasField("modelCode"):
        order.modelCode = proto.modelCode
    if proto.HasField("goodTillDate"):
        order.goodTillDate = proto.goodTillDate
    if proto.HasField("rule80A"):
        order.rule80A = proto.rule80A
    if proto.HasField("percentOffset"):
        order.percentOffset = safe_decimal(proto.percentOffset)
    if proto.HasField("settlingFirm"):
        order.settlingFirm = proto.settlingFirm
    if proto.HasField("shortSaleSlot"):
        order.shortSaleSlot = proto.shortSaleSlot
    if proto.HasField("designatedLocation"):
        order.designatedLocation = proto.designatedLocation
    if proto.HasField("exemptCode"):
        order.exemptCode = proto.exemptCode

    # Box / volatility-style auction extras
    if proto.HasField("startingPrice"):
        order.startingPrice = safe_decimal(proto.startingPrice)
    if proto.HasField("stockRefPrice"):
        order.stockRefPrice = safe_decimal(proto.stockRefPrice)
    if proto.HasField("delta"):
        order.delta = safe_decimal(proto.delta)
    if proto.HasField("stockRangeLower"):
        order.stockRangeLower = safe_decimal(proto.stockRangeLower)
    if proto.HasField("stockRangeUpper"):
        order.stockRangeUpper = safe_decimal(proto.stockRangeUpper)

    if proto.HasField("displaySize"):
        order.displaySize = proto.displaySize
    if proto.HasField("blockOrder"):
        order.blockOrder = proto.blockOrder
    if proto.HasField("sweepToFill"):
        order.sweepToFill = proto.sweepToFill
    if proto.HasField("allOrNone"):
        order.allOrNone = proto.allOrNone
    if proto.HasField("minQty"):
        order.minQty = proto.minQty
    if proto.HasField("ocaType"):
        order.ocaType = proto.ocaType
    if proto.HasField("triggerMethod"):
        order.triggerMethod = proto.triggerMethod

    # Volatility family
    if proto.HasField("volatility"):
        order.volatility = safe_decimal(proto.volatility)
    if proto.HasField("volatilityType"):
        order.volatilityType = proto.volatilityType
    if proto.HasField("deltaNeutralOrderType"):
        order.deltaNeutralOrderType = proto.deltaNeutralOrderType
    if proto.HasField("deltaNeutralAuxPrice"):
        order.deltaNeutralAuxPrice = safe_decimal(proto.deltaNeutralAuxPrice)
    if proto.HasField("deltaNeutralConId"):
        order.deltaNeutralConId = proto.deltaNeutralConId
    if proto.HasField("deltaNeutralSettlingFirm"):
        order.deltaNeutralSettlingFirm = proto.deltaNeutralSettlingFirm
    if proto.HasField("deltaNeutralClearingAccount"):
        order.deltaNeutralClearingAccount = proto.deltaNeutralClearingAccount
    if proto.HasField("deltaNeutralClearingIntent"):
        order.deltaNeutralClearingIntent = proto.deltaNeutralClearingIntent
    if proto.HasField("deltaNeutralOpenClose"):
        order.deltaNeutralOpenClose = proto.deltaNeutralOpenClose
    if proto.HasField("deltaNeutralShortSale"):
        order.deltaNeutralShortSale = proto.deltaNeutralShortSale
    if proto.HasField("deltaNeutralShortSaleSlot"):
        order.deltaNeutralShortSaleSlot = proto.deltaNeutralShortSaleSlot
    if proto.HasField("deltaNeutralDesignatedLocation"):
        order.deltaNeutralDesignatedLocation = proto.deltaNeutralDesignatedLocation
    if proto.HasField("continuousUpdate"):
        order.continuousUpdate = proto.continuousUpdate
    if proto.HasField("referencePriceType"):
        order.referencePriceType = proto.referencePriceType

    if proto.HasField("trailStopPrice"):
        order.trailStopPrice = safe_decimal(proto.trailStopPrice)
    if proto.HasField("trailingPercent"):
        order.trailingPercent = safe_decimal(proto.trailingPercent)

    # Order combo legs (per-leg prices) — sourced from the CONTRACT
    # proto, not the order proto. Caller must pass ``contractProto``
    # for these to populate; otherwise the field stays at its empty
    # default (matches IBKR's behavior when the contract proto is
    # absent).
    comboLegs = _decodeOrderComboLegs(contractProto)
    if comboLegs:
        order.orderComboLegs = comboLegs

    # Smart combo routing params (always read; absent map decodes to
    # an empty list and replaces the dataclass-default empty list).
    order.smartComboRoutingParams = _parseTagValueList(proto.smartComboRoutingParams)

    # Scale family
    if proto.HasField("scaleInitLevelSize"):
        order.scaleInitLevelSize = proto.scaleInitLevelSize
    if proto.HasField("scaleSubsLevelSize"):
        order.scaleSubsLevelSize = proto.scaleSubsLevelSize
    if proto.HasField("scalePriceIncrement"):
        order.scalePriceIncrement = safe_decimal(proto.scalePriceIncrement)
    if proto.HasField("scalePriceAdjustValue"):
        order.scalePriceAdjustValue = safe_decimal(proto.scalePriceAdjustValue)
    if proto.HasField("scalePriceAdjustInterval"):
        order.scalePriceAdjustInterval = proto.scalePriceAdjustInterval
    if proto.HasField("scaleProfitOffset"):
        order.scaleProfitOffset = safe_decimal(proto.scaleProfitOffset)
    if proto.HasField("scaleAutoReset"):
        order.scaleAutoReset = proto.scaleAutoReset
    if proto.HasField("scaleInitPosition"):
        order.scaleInitPosition = proto.scaleInitPosition
    if proto.HasField("scaleInitFillQty"):
        order.scaleInitFillQty = proto.scaleInitFillQty
    if proto.HasField("scaleRandomPercent"):
        order.scaleRandomPercent = proto.scaleRandomPercent

    # Hedge family — IBKR gates ``hedgeParam`` on the hedgeType being
    # set (some hedge types omit the param). Mirror that gating.
    if proto.HasField("hedgeType"):
        order.hedgeType = proto.hedgeType
        if proto.HasField("hedgeParam") and proto.hedgeType:
            order.hedgeParam = proto.hedgeParam
    # ``hedgeMaxSize`` is on the wire but NOT on the Order dataclass —
    # intentionally dropped here (see top-level docstring for the list).

    if proto.HasField("optOutSmartRouting"):
        order.optOutSmartRouting = proto.optOutSmartRouting
    if proto.HasField("clearingAccount"):
        order.clearingAccount = proto.clearingAccount
    if proto.HasField("clearingIntent"):
        order.clearingIntent = proto.clearingIntent
    if proto.HasField("notHeld"):
        order.notHeld = proto.notHeld

    # Algo family — paired read: only consume algoParams when
    # algoStrategy is present (the wire convention matches IBKR's
    # decoder so absent algoStrategy + present algoParams is a malformed
    # payload we ignore).
    if proto.HasField("algoStrategy"):
        order.algoStrategy = proto.algoStrategy
        order.algoParams = _parseTagValueList(proto.algoParams)
    if proto.HasField("algoId"):
        order.algoId = proto.algoId

    if proto.HasField("solicited"):
        order.solicited = proto.solicited
    if proto.HasField("whatIf"):
        order.whatIf = proto.whatIf
    if proto.HasField("randomizeSize"):
        order.randomizeSize = proto.randomizeSize
    if proto.HasField("randomizePrice"):
        order.randomizePrice = proto.randomizePrice

    # Pegged-to-benchmark family
    if proto.HasField("referenceContractId"):
        order.referenceContractId = proto.referenceContractId
    if proto.HasField("isPeggedChangeAmountDecrease"):
        order.isPeggedChangeAmountDecrease = proto.isPeggedChangeAmountDecrease
    if proto.HasField("peggedChangeAmount"):
        order.peggedChangeAmount = proto.peggedChangeAmount
    if proto.HasField("referenceChangeAmount"):
        order.referenceChangeAmount = proto.referenceChangeAmount
    if proto.HasField("referenceExchangeId"):
        order.referenceExchangeId = proto.referenceExchangeId

    # Conditions
    conditions = _decodeConditions(proto)
    if conditions:
        order.conditions = conditions
    if proto.HasField("conditionsIgnoreRth"):
        order.conditionsIgnoreRth = proto.conditionsIgnoreRth
    if proto.HasField("conditionsCancelOrder"):
        order.conditionsCancelOrder = proto.conditionsCancelOrder

    # Adjustable orders
    if proto.HasField("adjustedOrderType"):
        order.adjustedOrderType = proto.adjustedOrderType
    if proto.HasField("triggerPrice"):
        order.triggerPrice = safe_decimal(proto.triggerPrice)
    if proto.HasField("lmtPriceOffset"):
        order.lmtPriceOffset = safe_decimal(proto.lmtPriceOffset)
    if proto.HasField("adjustedStopPrice"):
        order.adjustedStopPrice = safe_decimal(proto.adjustedStopPrice)
    if proto.HasField("adjustedStopLimitPrice"):
        order.adjustedStopLimitPrice = safe_decimal(proto.adjustedStopLimitPrice)
    if proto.HasField("adjustedTrailingAmount"):
        order.adjustedTrailingAmount = safe_decimal(proto.adjustedTrailingAmount)
    if proto.HasField("adjustableTrailingUnit"):
        order.adjustableTrailingUnit = proto.adjustableTrailingUnit

    # Soft-dollar tier (composite)
    softDollarTier = _decodeSoftDollarTier(proto)
    if softDollarTier is not None:
        order.softDollarTier = softDollarTier

    if proto.HasField("cashQty"):
        order.cashQty = safe_decimal(proto.cashQty)
    if proto.HasField("dontUseAutoPriceForHedge"):
        order.dontUseAutoPriceForHedge = proto.dontUseAutoPriceForHedge
    if proto.HasField("isOmsContainer"):
        order.isOmsContainer = proto.isOmsContainer
    if proto.HasField("discretionaryUpToLimitPrice"):
        order.discretionaryUpToLimitPrice = proto.discretionaryUpToLimitPrice
    if proto.HasField("usePriceMgmtAlgo"):
        # Wire is int (0/1/UNSET); domain is bool. Map non-zero to True.
        order.usePriceMgmtAlgo = bool(proto.usePriceMgmtAlgo)
    if proto.HasField("duration"):
        order.duration = proto.duration
    if proto.HasField("postToAts"):
        order.postToAts = proto.postToAts
    if proto.HasField("autoCancelParent"):
        order.autoCancelParent = proto.autoCancelParent
    if proto.HasField("minTradeQty"):
        order.minTradeQty = proto.minTradeQty
    if proto.HasField("minCompeteSize"):
        order.minCompeteSize = proto.minCompeteSize
    if proto.HasField("competeAgainstBestOffset"):
        order.competeAgainstBestOffset = safe_decimal(proto.competeAgainstBestOffset)
    if proto.HasField("midOffsetAtWhole"):
        order.midOffsetAtWhole = safe_decimal(proto.midOffsetAtWhole)
    if proto.HasField("midOffsetAtHalf"):
        order.midOffsetAtHalf = safe_decimal(proto.midOffsetAtHalf)

    # Active start / stop time
    if proto.HasField("activeStartTime"):
        order.activeStartTime = proto.activeStartTime
    if proto.HasField("activeStopTime"):
        order.activeStopTime = proto.activeStopTime

    # ext / autoCancel / completedOrder fields
    if proto.HasField("extOperator"):
        order.extOperator = proto.extOperator
    if proto.HasField("autoCancelDate"):
        order.autoCancelDate = proto.autoCancelDate
    if proto.HasField("filledQuantity"):
        order.filledQuantity = safe_decimal(proto.filledQuantity)
    if proto.HasField("refFuturesConId"):
        order.refFuturesConId = proto.refFuturesConId
    if proto.HasField("shareholder"):
        order.shareholder = proto.shareholder
    if proto.HasField("routeMarketableToBbo"):
        # Wire is int (0/1); domain is bool.
        order.routeMarketableToBbo = bool(proto.routeMarketableToBbo)
    if proto.HasField("parentPermId"):
        order.parentPermId = proto.parentPermId
    if proto.HasField("imbalanceOnly"):
        order.imbalanceOnly = proto.imbalanceOnly

    # Order-misc + MIFID II + advancedErrorOverride + manualOrderTime —
    # IBKR's reference reads these in ``processOpenOrderMsg`` (the
    # binary path) but the proto schema places them on the Order
    # message and ``decodeOrder`` itself does NOT read them. We do,
    # because these are first-class domain fields and dropping them
    # silently would lose user-set order metadata on every wire round
    # trip.
    order.orderMiscOptions = _parseTagValueList(proto.orderMiscOptions)
    if proto.HasField("mifid2DecisionMaker"):
        order.mifid2DecisionMaker = proto.mifid2DecisionMaker
    if proto.HasField("mifid2DecisionAlgo"):
        order.mifid2DecisionAlgo = proto.mifid2DecisionAlgo
    if proto.HasField("mifid2ExecutionTrader"):
        order.mifid2ExecutionTrader = proto.mifid2ExecutionTrader
    if proto.HasField("mifid2ExecutionAlgo"):
        order.mifid2ExecutionAlgo = proto.mifid2ExecutionAlgo
    if proto.HasField("advancedErrorOverride"):
        order.advancedErrorOverride = proto.advancedErrorOverride
    if proto.HasField("manualOrderTime"):
        order.manualOrderTime = proto.manualOrderTime
    if proto.HasField("overridePercentageConstraints"):
        order.overridePercentageConstraints = proto.overridePercentageConstraints
    if proto.HasField("scaleTable"):
        order.scaleTable = proto.scaleTable
    if proto.HasField("transmit"):
        order.transmit = proto.transmit

    # Compliance / origination fields.
    if proto.HasField("customerAccount"):
        order.customerAccount = proto.customerAccount
    if proto.HasField("professionalCustomer"):
        order.professionalCustomer = proto.professionalCustomer
    if proto.HasField("bondAccruedInterest"):
        # Wire ships the value as a numeric string; the domain field is
        # ``Decimal | None`` so user code can compute against it directly.
        order.bondAccruedInterest = safe_decimal(proto.bondAccruedInterest)
    if proto.HasField("includeOvernight"):
        order.includeOvernight = proto.includeOvernight
    if proto.HasField("manualOrderIndicator"):
        order.manualOrderIndicator = proto.manualOrderIndicator
    if proto.HasField("submitter"):
        order.submitter = proto.submitter

    return order


# --- OrderStatus ---------------------------------------------------------


def createOrderStatus(proto: OrderStatus_pb2.OrderStatus) -> OrderStatus:
    status = OrderStatus()
    if proto.HasField("orderId"):
        status.orderId = proto.orderId
    if proto.HasField("status"):
        status.status = proto.status
    if proto.HasField("filled"):
        status.filled = safe_decimal(proto.filled)
    if proto.HasField("remaining"):
        status.remaining = safe_decimal(proto.remaining)
    if proto.HasField("avgFillPrice"):
        status.avgFillPrice = safe_decimal(proto.avgFillPrice)
    if proto.HasField("permId"):
        status.permId = proto.permId
    if proto.HasField("parentId"):
        status.parentId = proto.parentId
    if proto.HasField("lastFillPrice"):
        status.lastFillPrice = safe_decimal(proto.lastFillPrice)
    if proto.HasField("clientId"):
        status.clientId = proto.clientId
    if proto.HasField("whyHeld"):
        status.whyHeld = proto.whyHeld
    if proto.HasField("mktCapPrice"):
        status.mktCapPrice = safe_decimal(proto.mktCapPrice)
    return status


# --- OrderState ----------------------------------------------------------


def _decodeOrderAllocations(proto: OrderState_pb2.OrderState) -> list[OrderAllocation]:
    """Decode the repeated ``orderAllocations`` sub-messages on an
    OrderState into a list of frozen domain ``OrderAllocation`` records.
    Mirrors IBKR's ``decodeOrderAllocations``; absent / empty repeated
    field returns ``[]``.
    """
    out: list[OrderAllocation] = []
    for a in proto.orderAllocations:
        out.append(
            OrderAllocation(
                account=a.account if a.HasField("account") else "",
                position=safe_decimal(a.position) if a.HasField("position") else None,
                positionDesired=safe_decimal(a.positionDesired)
                if a.HasField("positionDesired")
                else None,
                positionAfter=safe_decimal(a.positionAfter)
                if a.HasField("positionAfter")
                else None,
                desiredAllocQty=safe_decimal(a.desiredAllocQty)
                if a.HasField("desiredAllocQty")
                else None,
                allowedAllocQty=safe_decimal(a.allowedAllocQty)
                if a.HasField("allowedAllocQty")
                else None,
                isMonetary=a.isMonetary if a.HasField("isMonetary") else False,
            )
        )
    return out


def createOrderState(proto: OrderState_pb2.OrderState) -> OrderState:
    """Decode an ``OrderState`` proto.

    The wire ``commissionAndFees`` field is the IBKR-aligned canonical
    name for the combined broker commission + exchange / regulatory
    fees number. v3.0's domain field matches the wire name; the legacy
    ``state.commission`` attribute is a deprecation alias.
    """
    state = OrderState()
    if proto.HasField("status"):
        state.status = proto.status
    if proto.HasField("initMarginBefore"):
        state.initMarginBefore = str(proto.initMarginBefore)
    if proto.HasField("maintMarginBefore"):
        state.maintMarginBefore = str(proto.maintMarginBefore)
    if proto.HasField("equityWithLoanBefore"):
        state.equityWithLoanBefore = str(proto.equityWithLoanBefore)
    if proto.HasField("initMarginChange"):
        state.initMarginChange = str(proto.initMarginChange)
    if proto.HasField("maintMarginChange"):
        state.maintMarginChange = str(proto.maintMarginChange)
    if proto.HasField("equityWithLoanChange"):
        state.equityWithLoanChange = str(proto.equityWithLoanChange)
    if proto.HasField("initMarginAfter"):
        state.initMarginAfter = str(proto.initMarginAfter)
    if proto.HasField("maintMarginAfter"):
        state.maintMarginAfter = str(proto.maintMarginAfter)
    if proto.HasField("equityWithLoanAfter"):
        state.equityWithLoanAfter = str(proto.equityWithLoanAfter)
    # Wire ``commissionAndFees`` is the IBKR-aligned canonical name
    # (broker commission + exchange + regulatory fees combined).
    if proto.HasField("commissionAndFees"):
        state.commissionAndFees = safe_decimal(proto.commissionAndFees)
    if proto.HasField("minCommissionAndFees"):
        state.minCommission = safe_decimal(proto.minCommissionAndFees)
    if proto.HasField("maxCommissionAndFees"):
        state.maxCommission = safe_decimal(proto.maxCommissionAndFees)
    if proto.HasField("commissionAndFeesCurrency"):
        state.commissionCurrency = proto.commissionAndFeesCurrency
    if proto.HasField("warningText"):
        state.warningText = proto.warningText
    if proto.HasField("marginCurrency"):
        state.marginCurrency = proto.marginCurrency
    # OutsideRTH margin variants — strings on the wire matching the
    # in-RTH shape; the binary path delivers them through the same
    # str-coerced field family.
    if proto.HasField("initMarginBeforeOutsideRTH"):
        state.initMarginBeforeOutsideRTH = str(proto.initMarginBeforeOutsideRTH)
    if proto.HasField("maintMarginBeforeOutsideRTH"):
        state.maintMarginBeforeOutsideRTH = str(proto.maintMarginBeforeOutsideRTH)
    if proto.HasField("equityWithLoanBeforeOutsideRTH"):
        state.equityWithLoanBeforeOutsideRTH = str(proto.equityWithLoanBeforeOutsideRTH)
    if proto.HasField("initMarginChangeOutsideRTH"):
        state.initMarginChangeOutsideRTH = str(proto.initMarginChangeOutsideRTH)
    if proto.HasField("maintMarginChangeOutsideRTH"):
        state.maintMarginChangeOutsideRTH = str(proto.maintMarginChangeOutsideRTH)
    if proto.HasField("equityWithLoanChangeOutsideRTH"):
        state.equityWithLoanChangeOutsideRTH = str(proto.equityWithLoanChangeOutsideRTH)
    if proto.HasField("initMarginAfterOutsideRTH"):
        state.initMarginAfterOutsideRTH = str(proto.initMarginAfterOutsideRTH)
    if proto.HasField("maintMarginAfterOutsideRTH"):
        state.maintMarginAfterOutsideRTH = str(proto.maintMarginAfterOutsideRTH)
    if proto.HasField("equityWithLoanAfterOutsideRTH"):
        state.equityWithLoanAfterOutsideRTH = str(proto.equityWithLoanAfterOutsideRTH)
    if proto.HasField("suggestedSize"):
        state.suggestedSize = safe_decimal(proto.suggestedSize)
    if proto.HasField("rejectReason"):
        state.rejectReason = proto.rejectReason
    state.orderAllocations = _decodeOrderAllocations(proto)
    if proto.HasField("completedTime"):
        state.completedTime = proto.completedTime
    if proto.HasField("completedStatus"):
        state.completedStatus = proto.completedStatus
    return state


# --- Execution -----------------------------------------------------------


def createExecution(proto: Execution_pb2.Execution) -> Execution:
    """Decode an ``Execution`` proto.

    Wire fields ``isLiquidation`` (bool) and ``isPriceRevisionPending``
    (bool) map to domain ``liquidation`` (int) and
    ``pendingPriceRevision`` (bool).
    """
    ex = Execution()
    if proto.HasField("orderId"):
        ex.orderId = proto.orderId
    if proto.HasField("execId"):
        ex.execId = proto.execId
    # ``time`` is a wire string in IBKR's "YYYYmmdd  HH:MM:SS [tz]"
    # format; the wrapper's existing tz-normalization code parses
    # this. The binary-path execDetails handler does the parsing
    # there, so we leave the raw string on the domain object for the
    # wrapper to normalize per its existing flow.
    # (See ``Wrapper.execDetails`` for the parse + tz application.)
    if proto.HasField("acctNumber"):
        ex.acctNumber = proto.acctNumber
    if proto.HasField("exchange"):
        ex.exchange = proto.exchange
    if proto.HasField("side"):
        ex.side = proto.side
    if proto.HasField("shares"):
        ex.shares = safe_decimal(proto.shares)
    if proto.HasField("price"):
        ex.price = safe_decimal(proto.price)
    if proto.HasField("permId"):
        ex.permId = proto.permId
    if proto.HasField("clientId"):
        ex.clientId = proto.clientId
    if proto.HasField("isLiquidation"):
        ex.liquidation = int(proto.isLiquidation)
    if proto.HasField("cumQty"):
        ex.cumQty = safe_decimal(proto.cumQty)
    if proto.HasField("avgPrice"):
        ex.avgPrice = safe_decimal(proto.avgPrice)
    if proto.HasField("orderRef"):
        ex.orderRef = proto.orderRef
    if proto.HasField("evRule"):
        ex.evRule = proto.evRule
    if proto.HasField("evMultiplier"):
        ex.evMultiplier = safe_decimal(proto.evMultiplier)
    if proto.HasField("modelCode"):
        ex.modelCode = proto.modelCode
    if proto.HasField("lastLiquidity"):
        ex.lastLiquidity = proto.lastLiquidity
    if proto.HasField("isPriceRevisionPending"):
        ex.pendingPriceRevision = proto.isPriceRevisionPending
    if proto.HasField("submitter"):
        ex.submitter = proto.submitter
    if proto.HasField("optExerciseOrLapseType"):
        ex.optExerciseOrLapseType = proto.optExerciseOrLapseType
    return ex


# --- CommissionAndFeesReport --------------------------------------------


def createCommissionReport(
    proto: CommissionAndFeesReport_pb2.CommissionAndFeesReport,
) -> CommissionReport:
    """Decode the wire ``CommissionAndFeesReport`` into our domain
    ``CommissionReport``. v3.0's domain field matches the wire name
    (``commissionAndFees``). The wire also renames ``yield`` to
    ``bondYield``; we map that back to the historic domain field name.
    ``yieldRedemptionDate`` is wire-string but our domain field is int —
    coerce.
    """
    report = CommissionReport()
    if proto.HasField("execId"):
        report.execId = proto.execId
    if proto.HasField("commissionAndFees"):
        report.commissionAndFees = safe_decimal(proto.commissionAndFees)
    if proto.HasField("currency"):
        report.currency = proto.currency
    if proto.HasField("realizedPNL"):
        report.realizedPNL = safe_decimal(proto.realizedPNL)
    if proto.HasField("bondYield"):
        report.yield_ = safe_decimal(proto.bondYield)
    if proto.HasField("yieldRedemptionDate"):
        # Historic int domain field; wire ships YYYYMMDD as string.
        try:
            report.yieldRedemptionDate = int(proto.yieldRedemptionDate)
        except ValueError:
            report.yieldRedemptionDate = 0
    return report


# --- Envelope: OpenOrder ------------------------------------------------


def createOpenOrder(
    proto: OpenOrder_pb2.OpenOrder,
) -> tuple[int, Contract, Order, OrderState]:
    """Decode an ``OpenOrder`` envelope.

    Returns ``(orderId, contract, order, orderState)`` so the receiving
    wrapper can route to the same merge path the binary ``openOrder``
    callback uses — no special-case routing for protobuf orders.
    """
    orderId = proto.orderId if proto.HasField("orderId") else 0
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    # Propagate the contract proto so ``createOrder`` can populate
    # ``orderComboLegs`` (per-leg prices live on the contract proto).
    order = (
        createOrder(
            proto.order,
            contractProto=proto.contract if proto.HasField("contract") else None,
            orderId=orderId,
        )
        if proto.HasField("order")
        else Order()
    )
    state = (
        createOrderState(proto.orderState)
        if proto.HasField("orderState")
        else OrderState()
    )
    return orderId, contract, order, state


# --- Envelope: CompletedOrder -------------------------------------------


def createCompletedOrder(
    proto: CompletedOrder_pb2.CompletedOrder,
) -> tuple[Contract, Order, OrderState] | None:
    """Decode a ``CompletedOrder`` envelope.

    Returns ``(contract, order, orderState)`` or ``None`` when the
    envelope is missing any of the three required sub-messages. The
    ``None`` signal mirrors ``_protoOpenOrder``'s drop-on-malformed
    behaviour: a half-formed completed order would poison the trade
    registry.

    Combo-leg-bearing orders read per-leg pricing off the contract
    proto, so the contract message is fed into ``createOrder`` for
    the ``orderComboLegs`` rehydration.
    """
    if not (
        proto.HasField("contract")
        and proto.HasField("order")
        and proto.HasField("orderState")
    ):
        return None
    contract = createContract(proto.contract)
    order = createOrder(proto.order, contractProto=proto.contract)
    state = createOrderState(proto.orderState)
    return contract, order, state


# --- Envelope: ExecutionDetails -----------------------------------------


def createExecutionDetails(
    proto: ExecutionDetails_pb2.ExecutionDetails,
) -> tuple[int, Contract, Execution]:
    """Decode an ``ExecutionDetails`` envelope.

    Returns ``(reqId, contract, execution)``. ``Execution.time`` is
    left in its IBKR wire-string form on the execution; the calling
    decoder applies the wrapper's tz normalization because that step
    needs access to ``Wrapper.ib.TimezoneTWS`` (decoder-instance
    state, not pure-converter input).
    """
    reqId = proto.reqId if proto.HasField("reqId") else -1
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    execution = (
        createExecution(proto.execution)
        if proto.HasField("execution")
        else Execution()
    )
    return reqId, contract, execution


# --- Envelope: PlaceOrderRequest ----------------------------------------


def _createAttachedOrdersProto(order: Order) -> AttachedOrders_pb2.AttachedOrders:
    """Build the AttachedOrders sub-message from the four cross-reference
    fields on the domain Order (``slOrderId`` / ``slOrderType`` /
    ``ptOrderId`` / ``ptOrderType``).

    Mirrors IBKR's ``client_utils.createAttachedOrdersProto``. The wire
    schema places these fields on a separate ``AttachedOrders`` message
    that the ``PlaceOrderRequest`` envelope embeds — they are NOT on
    ``Order_pb2.Order`` itself. Each field is gated by the standard
    ``isValidIntValue`` / non-empty-string discipline so unset domain
    defaults do not write sentinel values to the wire.
    """
    proto = AttachedOrders_pb2.AttachedOrders()
    if _isValidInt(order.slOrderId):
        proto.slOrderId = order.slOrderId
    if order.slOrderType:
        proto.slOrderType = order.slOrderType
    if _isValidInt(order.ptOrderId):
        proto.ptOrderId = order.ptOrderId
    if order.ptOrderType:
        proto.ptOrderType = order.ptOrderType
    return proto


def createPlaceOrderRequestProto(
    orderId: int, contract: Contract, order: Order
) -> PlaceOrderRequest_pb2.PlaceOrderRequest:
    """Encode a ``PlaceOrderRequest`` envelope for sending.

    The user-supplied ``orderId`` overrides ``order.orderId`` so the
    caller can place the order under a freshly-allocated id without
    having to mutate the source Order. ``order.clientId`` round-trips
    intact via ``createOrderProto``.

    Attached-order cross-references (``slOrderId`` / ``slOrderType`` /
    ``ptOrderId`` / ``ptOrderType``) ride on the ``attachedOrders``
    sub-message — IBKR's wire schema places them off ``Order`` rather
    than on it.
    """
    proto = PlaceOrderRequest_pb2.PlaceOrderRequest()
    if _isValidInt(orderId):
        proto.orderId = orderId
    # Pass the order so per-leg pricing (BAG-secType only) lands on the
    # ComboLeg proto's ``perLegPrice`` field. IBKR's reference signature
    # is ``createContractProto(contract, order)``.
    proto.contract.CopyFrom(createContractProto(contract, order))
    proto.order.CopyFrom(createOrderProto(order))
    proto.attachedOrders.CopyFrom(_createAttachedOrdersProto(order))
    return proto


# --- Envelope: CancelOrderRequest ---------------------------------------


def createCancelOrderRequestProto(
    orderId: int,
    manualOrderCancelTime: str = "",
    extOperator: str = "",
    manualOrderIndicator: int | None = None,
) -> CancelOrderRequest_pb2.CancelOrderRequest:
    """Encode a CancelOrderRequest including CME-tagging fields.

    ``extOperator`` / ``manualOrderIndicator`` skipped on ``None``;
    ``manualOrderCancelTime`` skipped on empty string.
    """
    proto = CancelOrderRequest_pb2.CancelOrderRequest()
    if _isValidInt(orderId):
        proto.orderId = orderId
    cancel = OrderCancel_pb2.OrderCancel()
    if manualOrderCancelTime:
        cancel.manualOrderCancelTime = manualOrderCancelTime
    if extOperator:
        cancel.extOperator = extOperator
    if manualOrderIndicator is not None:
        cancel.manualOrderIndicator = manualOrderIndicator
    proto.orderCancel.CopyFrom(cancel)
    return proto


# --- Empty / single-field request envelopes -----------------------------


def createOpenOrdersRequestProto() -> OpenOrdersRequest_pb2.OpenOrdersRequest:
    return OpenOrdersRequest_pb2.OpenOrdersRequest()


def createAllOpenOrdersRequestProto() -> AllOpenOrdersRequest_pb2.AllOpenOrdersRequest:
    return AllOpenOrdersRequest_pb2.AllOpenOrdersRequest()


def createAutoOpenOrdersRequestProto(
    autoBind: bool,
) -> AutoOpenOrdersRequest_pb2.AutoOpenOrdersRequest:
    proto = AutoOpenOrdersRequest_pb2.AutoOpenOrdersRequest()
    if autoBind:
        proto.autoBind = autoBind
    return proto


def createCompletedOrdersRequestProto(
    apiOnly: bool,
) -> CompletedOrdersRequest_pb2.CompletedOrdersRequest:
    proto = CompletedOrdersRequest_pb2.CompletedOrdersRequest()
    if apiOnly:
        proto.apiOnly = apiOnly
    return proto


def createGlobalCancelRequestProto(
    manualOrderCancelTime: str = "",
    extOperator: str = "",
    manualOrderIndicator: int | None = None,
) -> GlobalCancelRequest_pb2.GlobalCancelRequest:
    """Encode a GlobalCancelRequest. CME-tagging fields land on the
    nested ``orderCancel`` envelope, matching IBKR's reference shape."""
    proto = GlobalCancelRequest_pb2.GlobalCancelRequest()
    if manualOrderCancelTime:
        proto.orderCancel.manualOrderCancelTime = manualOrderCancelTime
    if extOperator:
        proto.orderCancel.extOperator = extOperator
    if manualOrderIndicator is not None:
        proto.orderCancel.manualOrderIndicator = manualOrderIndicator
    return proto


# --- ExecutionRequest ---------------------------------------------------


def createExecutionFilterProto(
    execFilter: ExecutionFilter,
) -> ExecutionFilter_pb2.ExecutionFilter:
    proto = ExecutionFilter_pb2.ExecutionFilter()
    # IBKR gates ``clientId`` on ``isValidIntValue`` — ``0`` is the
    # documented "no client filter" wire value and must flow through.
    if _isValidInt(execFilter.clientId):
        proto.clientId = execFilter.clientId
    if execFilter.acctCode:
        proto.acctCode = execFilter.acctCode
    if execFilter.time:
        proto.time = execFilter.time
    if execFilter.symbol:
        proto.symbol = execFilter.symbol
    if execFilter.secType:
        proto.secType = execFilter.secType
    if execFilter.exchange:
        proto.exchange = execFilter.exchange
    if execFilter.side:
        proto.side = execFilter.side
    # ``lastNDays`` / ``specificDates`` ship past
    # ``MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS`` (200). The
    # gating is the caller's responsibility (mirrors IBKR's reference);
    # the encoder unconditionally writes when the domain field carries
    # a non-sentinel value.
    if _isValidInt(execFilter.lastNDays):
        proto.lastNDays = execFilter.lastNDays
    if execFilter.specificDates:
        proto.specificDates.extend(execFilter.specificDates)
    return proto


def createExecutionRequestProto(
    reqId: int, execFilter: ExecutionFilter
) -> ExecutionRequest_pb2.ExecutionRequest:
    proto = ExecutionRequest_pb2.ExecutionRequest()
    if _isValidInt(reqId):
        proto.reqId = reqId
    proto.executionFilter.CopyFrom(createExecutionFilterProto(execFilter))
    return proto
