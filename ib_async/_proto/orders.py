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
    CancelOrderRequest_pb2,
    CommissionAndFeesReport_pb2,
    Execution_pb2,
    OpenOrder_pb2,
    Order_pb2,
    OrderCancel_pb2,
    OrderState_pb2,
    OrderStatus_pb2,
    PlaceOrderRequest_pb2,
)
from ..contract import Contract
from ..objects import CommissionReport, Execution
from ..order import Order, OrderState, OrderStatus
from .contracts import createContract, createContractProto
from .safe import safe_decimal


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


def createOrderProto(order: Order) -> Order_pb2.Order:
    """Encode a domain ``Order`` into its protobuf representation.

    Reads every field from the SOURCE order — never from the
    freshly-empty target proto. Empty / zero / ``None`` source values
    are skipped so the wire message stays sparse and the server's
    "field not set" semantics distinguish from "field set to default".
    """
    proto = Order_pb2.Order()

    # Order ids — set even at zero where IBKR treats zero as a valid
    # identifier. ``clientId`` MUST round-trip; the contributor's PR
    # had a typo here that silently dropped it from every outbound
    # order, sending fills to the wrong client bucket.
    if order.clientId or order.clientId == 0:
        proto.clientId = order.clientId
    if order.orderId:
        proto.orderId = order.orderId
    if order.permId:
        proto.permId = order.permId
    if order.parentId:
        proto.parentId = order.parentId

    # Primary attributes
    if order.action:
        proto.action = order.action
    if order.totalQuantity is not None:
        proto.totalQuantity = _decimalToWireString(order.totalQuantity)
    if order.displaySize:
        proto.displaySize = order.displaySize
    if order.orderType:
        proto.orderType = order.orderType
    if order.lmtPrice is not None:
        proto.lmtPrice = float(order.lmtPrice)
    if order.auxPrice is not None:
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
    if order.trailingPercent is not None:
        proto.trailingPercent = float(order.trailingPercent)
    if order.trailStopPrice is not None:
        proto.trailStopPrice = float(order.trailStopPrice)
    if order.minQty:
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
    if order.ocaType:
        proto.ocaType = order.ocaType
    if order.triggerMethod:
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

    return proto


def createOrder(proto: Order_pb2.Order) -> Order:
    """Decode a protobuf ``Order`` into our domain dataclass."""
    order = Order()
    if proto.HasField("clientId"):
        order.clientId = proto.clientId
    if proto.HasField("orderId"):
        order.orderId = proto.orderId
    if proto.HasField("permId"):
        order.permId = proto.permId
    if proto.HasField("parentId"):
        order.parentId = proto.parentId

    if proto.HasField("action"):
        order.action = proto.action
    if proto.HasField("totalQuantity"):
        order.totalQuantity = safe_decimal(proto.totalQuantity)
    if proto.HasField("displaySize"):
        order.displaySize = proto.displaySize
    if proto.HasField("orderType"):
        order.orderType = proto.orderType
    if proto.HasField("lmtPrice"):
        # Wire is ``double``; route through ``str`` to avoid binary-float
        # imprecision contaminating user-set fractional prices.
        order.lmtPrice = safe_decimal(str(proto.lmtPrice))
    if proto.HasField("auxPrice"):
        order.auxPrice = safe_decimal(str(proto.auxPrice))
    if proto.HasField("tif"):
        order.tif = proto.tif

    if proto.HasField("account"):
        order.account = proto.account
    if proto.HasField("settlingFirm"):
        order.settlingFirm = proto.settlingFirm
    if proto.HasField("clearingAccount"):
        order.clearingAccount = proto.clearingAccount
    if proto.HasField("clearingIntent"):
        order.clearingIntent = proto.clearingIntent

    if proto.HasField("allOrNone"):
        order.allOrNone = proto.allOrNone
    if proto.HasField("blockOrder"):
        order.blockOrder = proto.blockOrder
    if proto.HasField("hidden"):
        order.hidden = proto.hidden
    if proto.HasField("outsideRth"):
        order.outsideRth = proto.outsideRth
    if proto.HasField("sweepToFill"):
        order.sweepToFill = proto.sweepToFill
    if proto.HasField("trailingPercent"):
        order.trailingPercent = safe_decimal(str(proto.trailingPercent))
    if proto.HasField("trailStopPrice"):
        order.trailStopPrice = safe_decimal(str(proto.trailStopPrice))
    if proto.HasField("minQty"):
        order.minQty = proto.minQty
    if proto.HasField("goodAfterTime"):
        order.goodAfterTime = proto.goodAfterTime
    if proto.HasField("goodTillDate"):
        order.goodTillDate = proto.goodTillDate
    if proto.HasField("ocaGroup"):
        order.ocaGroup = proto.ocaGroup
    if proto.HasField("orderRef"):
        order.orderRef = proto.orderRef
    if proto.HasField("rule80A"):
        order.rule80A = proto.rule80A
    if proto.HasField("ocaType"):
        order.ocaType = proto.ocaType
    if proto.HasField("triggerMethod"):
        order.triggerMethod = proto.triggerMethod

    if proto.HasField("activeStartTime"):
        order.activeStartTime = proto.activeStartTime
    if proto.HasField("activeStopTime"):
        order.activeStopTime = proto.activeStopTime

    if proto.HasField("faGroup"):
        order.faGroup = proto.faGroup
    if proto.HasField("faMethod"):
        order.faMethod = proto.faMethod
    if proto.HasField("faPercentage"):
        order.faPercentage = proto.faPercentage

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
        status.avgFillPrice = safe_decimal(str(proto.avgFillPrice))
    if proto.HasField("permId"):
        status.permId = proto.permId
    if proto.HasField("parentId"):
        status.parentId = proto.parentId
    if proto.HasField("lastFillPrice"):
        status.lastFillPrice = safe_decimal(str(proto.lastFillPrice))
    if proto.HasField("clientId"):
        status.clientId = proto.clientId
    if proto.HasField("whyHeld"):
        status.whyHeld = proto.whyHeld
    if proto.HasField("mktCapPrice"):
        status.mktCapPrice = safe_decimal(str(proto.mktCapPrice))
    return status


# --- OrderState ----------------------------------------------------------


def createOrderState(proto: OrderState_pb2.OrderState) -> OrderState:
    """Decode an ``OrderState`` proto.

    Handles the wire's ``commissionAndFees`` family rebadged from the
    binary path's ``commission`` (the wire field includes IBKR fees;
    the domain field name kept ``commission`` for backwards compat).
    Margin / equity ``*OutsideRTH`` variants and ``orderAllocations``
    are wire-only — our domain dataclass does not yet model them, so
    those fields are intentionally dropped.
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
    # Wire ``commissionAndFees`` carries a single combined number;
    # domain ``commission`` historically meant the same thing.
    if proto.HasField("commissionAndFees"):
        state.commission = proto.commissionAndFees
    if proto.HasField("minCommissionAndFees"):
        state.minCommission = proto.minCommissionAndFees
    if proto.HasField("maxCommissionAndFees"):
        state.maxCommission = proto.maxCommissionAndFees
    if proto.HasField("commissionAndFeesCurrency"):
        state.commissionCurrency = proto.commissionAndFeesCurrency
    if proto.HasField("warningText"):
        state.warningText = proto.warningText
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
    ``pendingPriceRevision`` (bool). New wire fields ``submitter`` and
    ``optExerciseOrLapseType`` aren't on the domain dataclass yet and
    are intentionally dropped here; user code reading those will
    notice they're missing rather than getting silent garbage.
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
        ex.price = safe_decimal(str(proto.price))
    if proto.HasField("permId"):
        ex.permId = proto.permId
    if proto.HasField("clientId"):
        ex.clientId = proto.clientId
    if proto.HasField("isLiquidation"):
        ex.liquidation = int(proto.isLiquidation)
    if proto.HasField("cumQty"):
        ex.cumQty = safe_decimal(proto.cumQty)
    if proto.HasField("avgPrice"):
        ex.avgPrice = safe_decimal(str(proto.avgPrice))
    if proto.HasField("orderRef"):
        ex.orderRef = proto.orderRef
    if proto.HasField("evRule"):
        ex.evRule = proto.evRule
    if proto.HasField("evMultiplier"):
        ex.evMultiplier = safe_decimal(str(proto.evMultiplier))
    if proto.HasField("modelCode"):
        ex.modelCode = proto.modelCode
    if proto.HasField("lastLiquidity"):
        ex.lastLiquidity = proto.lastLiquidity
    if proto.HasField("isPriceRevisionPending"):
        ex.pendingPriceRevision = proto.isPriceRevisionPending
    return ex


# --- CommissionAndFeesReport --------------------------------------------


def createCommissionReport(
    proto: CommissionAndFeesReport_pb2.CommissionAndFeesReport,
) -> CommissionReport:
    """Decode the wire ``CommissionAndFeesReport`` into our domain
    ``CommissionReport``. The wire renamed ``commission`` to
    ``commissionAndFees`` and ``yield`` to ``bondYield``; we map
    those back to the historic domain field names. ``yieldRedemptionDate``
    was an int in 2.x but is wire-string here — coerce.
    """
    report = CommissionReport()
    if proto.HasField("execId"):
        report.execId = proto.execId
    if proto.HasField("commissionAndFees"):
        report.commission = safe_decimal(str(proto.commissionAndFees))
    if proto.HasField("currency"):
        report.currency = proto.currency
    if proto.HasField("realizedPNL"):
        report.realizedPNL = safe_decimal(str(proto.realizedPNL))
    if proto.HasField("bondYield"):
        report.yield_ = safe_decimal(str(proto.bondYield))
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
    order = createOrder(proto.order) if proto.HasField("order") else Order()
    state = (
        createOrderState(proto.orderState)
        if proto.HasField("orderState")
        else OrderState()
    )
    return orderId, contract, order, state


# --- Envelope: PlaceOrderRequest ----------------------------------------


def createPlaceOrderRequestProto(
    orderId: int, contract: Contract, order: Order
) -> PlaceOrderRequest_pb2.PlaceOrderRequest:
    """Encode a ``PlaceOrderRequest`` envelope for sending.

    The user-supplied ``orderId`` overrides ``order.orderId`` so the
    caller can place the order under a freshly-allocated id without
    having to mutate the source Order. ``order.clientId`` round-trips
    intact via ``createOrderProto``.
    """
    proto = PlaceOrderRequest_pb2.PlaceOrderRequest()
    proto.orderId = orderId
    proto.contract.CopyFrom(createContractProto(contract))
    proto.order.CopyFrom(createOrderProto(order))
    return proto


# --- Envelope: CancelOrderRequest ---------------------------------------


def createCancelOrderRequestProto(
    orderId: int,
    manualCancelOrderTime: str = "",
    extOperator: str = "",
    manualOrderIndicator: int = 0,
) -> CancelOrderRequest_pb2.CancelOrderRequest:
    proto = CancelOrderRequest_pb2.CancelOrderRequest()
    proto.orderId = orderId
    cancel = OrderCancel_pb2.OrderCancel()
    if manualCancelOrderTime:
        cancel.manualOrderCancelTime = manualCancelOrderTime
    if extOperator:
        cancel.extOperator = extOperator
    if manualOrderIndicator:
        cancel.manualOrderIndicator = manualOrderIndicator
    proto.orderCancel.CopyFrom(cancel)
    return proto
