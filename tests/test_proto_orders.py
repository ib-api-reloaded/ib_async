"""Negative-path-first tests for the orders protobuf converter.

The headline regression is the ``clientId`` round-trip (the contributor's
upstream PR had a typo at ``trade_converters.py:94-95`` that silently
dropped ``clientId`` from every outbound order, sending fills to the
wrong client bucket — catastrophic for multi-client accounts). The
``test_clientId_round_trip_regression`` test exercises that exact
path; if the converter ever stops copying ``clientId`` the test fails
loudly.

Additional negative coverage:
* Empty / partial protos must produce ``Decimal | None``-shaped domain
  objects rather than crashing.
* Field-name mismatches between wire and domain (``isLiquidation`` vs
  ``liquidation``, ``commissionAndFees`` vs ``commission``,
  ``bondYield`` vs ``yield_``) must round-trip via the canonical
  domain spelling.
"""

from __future__ import annotations

from decimal import Decimal

from ib_async._pb import (
    AttachedOrders_pb2,
    CommissionAndFeesReport_pb2,
    Contract_pb2,
    Execution_pb2,
    ExecutionFilter_pb2,
    ExecutionRequest_pb2,
    OpenOrder_pb2,
    Order_pb2,
    OrderState_pb2,
    OrderStatus_pb2,
    PlaceOrderRequest_pb2,
)
from ib_async._proto.orders import (
    createCancelOrderRequestProto,
    createCommissionReport,
    createExecution,
    createExecutionFilterProto,
    createExecutionRequestProto,
    createOpenOrder,
    createOrder,
    createOrderProto,
    createOrderState,
    createOrderStatus,
    createPlaceOrderRequestProto,
)
from ib_async.contract import Stock
from ib_async.objects import ExecutionFilter
from ib_async.order import LimitOrder, MarketOrder, Order

# ---------------------------------------------------------------------------
# CRITICAL regression: clientId must round-trip
# ---------------------------------------------------------------------------


def test_clientId_round_trip_regression():
    """Guards the upstream-PR bug where ``createOrderProto`` had
    ``order.clientId = order.clientId`` (target self-assign) instead
    of writing the source value into the proto. If this test fails,
    every outbound order is silently going to the wrong client."""
    order = Order(orderId=1, clientId=42, permId=99, action="BUY")
    proto = createOrderProto(order)
    assert proto.clientId == 42
    # Round-trip must preserve clientId on decode too.
    decoded = createOrder(proto)
    assert decoded.clientId == 42


def test_clientId_zero_is_a_valid_value_not_unset():
    # IBKR treats clientId=0 as a real client id (the master client).
    # The converter must write zero through, not skip it.
    order = Order(orderId=1, clientId=0, action="BUY")
    proto = createOrderProto(order)
    assert proto.HasField("clientId")
    assert proto.clientId == 0


# ---------------------------------------------------------------------------
# Order — empty proto, partial proto, Decimal coercion
# ---------------------------------------------------------------------------


def test_create_order_handles_completely_empty_proto():
    proto = Order_pb2.Order()
    order = createOrder(proto)
    # Decimal-typed numeric fields are ``None`` so ``if order.lmtPrice:``
    # evaluates falsy on an unset proto.
    assert order.lmtPrice is None
    assert order.auxPrice is None
    assert order.totalQuantity is None
    assert not order.lmtPrice
    assert not order.totalQuantity


def test_create_order_total_quantity_string_to_decimal():
    proto = Order_pb2.Order()
    proto.totalQuantity = "100.5"  # fractional-share order
    order = createOrder(proto)
    assert order.totalQuantity == Decimal("100.5")


def test_create_order_total_quantity_garbage_lands_as_none():
    proto = Order_pb2.Order()
    proto.totalQuantity = "not-a-number"
    order = createOrder(proto)
    assert order.totalQuantity is None


def test_create_order_lmt_price_double_to_decimal_via_string():
    # Wire is ``double``; coercing via str avoids binary-float
    # imprecision contaminating user-set fractional prices.
    proto = Order_pb2.Order()
    proto.lmtPrice = 100.5
    order = createOrder(proto)
    assert order.lmtPrice == Decimal("100.5")


def test_create_order_round_trip_all_primary_fields():
    src = Order(
        orderId=7,
        clientId=11,
        permId=999,
        action="BUY",
        totalQuantity=Decimal("100"),
        orderType="LMT",
        lmtPrice=Decimal("50.5"),
        auxPrice=Decimal("0.10"),
        tif="DAY",
        ocaGroup="grp",
        orderRef="my-ref",
        outsideRth=True,
        hidden=True,
    )
    proto = createOrderProto(src)
    decoded = createOrder(proto)
    assert decoded.orderId == 7
    assert decoded.clientId == 11
    assert decoded.permId == 999
    assert decoded.action == "BUY"
    assert decoded.totalQuantity == Decimal("100")
    assert decoded.orderType == "LMT"
    assert decoded.lmtPrice == Decimal("50.5")
    assert decoded.auxPrice == Decimal("0.10")
    assert decoded.tif == "DAY"
    assert decoded.ocaGroup == "grp"
    assert decoded.orderRef == "my-ref"
    assert decoded.outsideRth is True
    assert decoded.hidden is True


def test_create_order_proto_skips_unset_decimal_fields():
    # ``None`` totalQuantity stays unset on the proto so server
    # "field not set" semantics distinguish from "field set to default".
    order = Order(orderId=1, clientId=0, action="BUY")
    # Don't set totalQuantity / lmtPrice / auxPrice.
    proto = createOrderProto(order)
    assert not proto.HasField("totalQuantity")
    assert not proto.HasField("lmtPrice")
    assert not proto.HasField("auxPrice")


def test_create_order_proto_writes_decimal_quantity_via_canonical_string():
    # Decimal('100') round-trips as "100" not "100.0" — IBKR's wire
    # convention is the unsuffixed form for whole numbers.
    order = Order(orderId=1, clientId=0, totalQuantity=Decimal("100"))
    proto = createOrderProto(order)
    assert proto.totalQuantity == "100"


def test_limit_order_constructor_coerces_user_floats_to_decimal():
    # User-friendly ``LimitOrder("BUY", 100, 50.5)`` round-trips through
    # ``_toDecimal`` so the wire-side gets a clean Decimal even though
    # the user passed floats.
    order = LimitOrder("BUY", 100, 50.5)
    assert isinstance(order.totalQuantity, Decimal)
    assert isinstance(order.lmtPrice, Decimal)
    assert order.lmtPrice == Decimal("50.5")


def test_market_order_does_not_coerce_unset_fields_to_zero():
    # MarketOrder doesn't take a price. lmtPrice / auxPrice should stay
    # ``None`` so user code's ``if order.lmtPrice:`` correctly skips.
    order = MarketOrder("BUY", 100)
    assert order.lmtPrice is None
    assert order.auxPrice is None
    assert not order.lmtPrice


# ---------------------------------------------------------------------------
# CRITICAL safety regressions — order-payload field coverage
#
# Earlier ``createOrderProto`` only wrote ~30 of ~140 IBKR ``Order.proto``
# fields. The most catastrophic gap was ``transmit`` (domain default
# ``True``): every protobuf-path order landed on the broker as a staged,
# non-transmitted order. These tests pin every previously-missing field
# we now write, so a future refactor can't silently drop them again.
# ---------------------------------------------------------------------------


def test_transmit_round_trips_true_correctly():
    """Critical safety: ``order.transmit=True`` (the domain default) must
    cause ``proto.transmit=True`` so the server actually transmits the
    order. proto3 default-False on absent transmit would leave every
    protobuf-path order as a non-transmitted staged order."""
    order = LimitOrder("BUY", 100, 50.5)  # transmit defaults to True
    assert order.transmit is True
    proto = createOrderProto(order)
    assert proto.transmit is True
    assert proto.HasField("transmit")


def test_transmit_explicit_false_round_trips():
    """User explicitly setting transmit=False must round-trip too —
    this is how staged-order workflows work in some clients. proto3
    default-False on absent transmit also reads as not-transmitted on
    the server, so HasField False is fine for this case."""
    order = LimitOrder("BUY", 100, 50.5)
    order.transmit = False
    proto = createOrderProto(order)
    assert proto.transmit is False


def test_whatIf_round_trips_when_set():
    order = LimitOrder("BUY", 100, 50.5)
    order.whatIf = True
    proto = createOrderProto(order)
    assert proto.HasField("whatIf")
    assert proto.whatIf is True


def test_whatIf_unset_stays_off_the_wire():
    # Default ``whatIf=False`` must NOT be written — the server reads
    # absence as "real order, not a what-if margin check".
    order = LimitOrder("BUY", 100, 50.5)
    proto = createOrderProto(order)
    assert not proto.HasField("whatIf")


def test_algo_strategy_and_params_round_trip():
    from ib_async.contract import TagValue

    order = LimitOrder("BUY", 100, 50.5)
    order.algoStrategy = "Adaptive"
    order.algoParams = [TagValue("adaptivePriority", "Normal")]
    order.algoId = "algo-123"
    proto = createOrderProto(order)
    assert proto.HasField("algoStrategy")
    assert proto.algoStrategy == "Adaptive"
    assert proto.HasField("algoId")
    assert proto.algoId == "algo-123"
    assert dict(proto.algoParams) == {"adaptivePriority": "Normal"}


def test_cashQty_round_trips():
    order = LimitOrder("BUY", 100, 50.5)
    order.cashQty = 5000.0
    proto = createOrderProto(order)
    assert proto.HasField("cashQty")
    assert proto.cashQty == 5000.0


def test_cashQty_unset_sentinel_stays_off_the_wire():
    # Default is UNSET_DOUBLE; must NOT be written or the server sees
    # a garbage giant cash amount.
    order = LimitOrder("BUY", 100, 50.5)
    proto = createOrderProto(order)
    assert not proto.HasField("cashQty")


def test_manualOrderTime_round_trips():
    order = LimitOrder("BUY", 100, 50.5)
    order.manualOrderTime = "20300101 09:30:00"
    proto = createOrderProto(order)
    assert proto.HasField("manualOrderTime")
    assert proto.manualOrderTime == "20300101 09:30:00"


def test_triggerPrice_round_trips_via_decimal():
    order = LimitOrder("BUY", 100, 50.5)
    order.triggerPrice = Decimal("49.50")
    proto = createOrderProto(order)
    assert proto.HasField("triggerPrice")
    assert proto.triggerPrice == 49.5


def test_adjustedStopPrice_round_trips_via_decimal():
    order = LimitOrder("BUY", 100, 50.5)
    order.adjustedStopPrice = Decimal("48.25")
    proto = createOrderProto(order)
    assert proto.HasField("adjustedStopPrice")
    assert proto.adjustedStopPrice == 48.25


def test_lmtPriceOffset_round_trips_via_decimal():
    order = LimitOrder("BUY", 100, 50.5)
    order.lmtPriceOffset = Decimal("0.05")
    proto = createOrderProto(order)
    assert proto.HasField("lmtPriceOffset")
    assert proto.lmtPriceOffset == 0.05


def test_volatility_round_trips():
    order = LimitOrder("BUY", 100, 50.5)
    order.volatility = 0.25
    order.volatilityType = 1
    proto = createOrderProto(order)
    assert proto.HasField("volatility")
    assert proto.volatility == 0.25
    assert proto.HasField("volatilityType")
    assert proto.volatilityType == 1


def test_minQty_unset_sentinel_stays_off_the_wire():
    """Domain ``minQty`` defaults to ``UNSET_INTEGER`` — a previously
    truthy-guard would write the sentinel value (~2.1B) to the wire."""
    order = LimitOrder("BUY", 100, 50.5)
    proto = createOrderProto(order)
    assert not proto.HasField("minQty")


def test_minQty_real_value_round_trips():
    order = LimitOrder("BUY", 100, 50.5)
    order.minQty = 50
    proto = createOrderProto(order)
    assert proto.HasField("minQty")
    assert proto.minQty == 50


# ---------------------------------------------------------------------------
# OrderStatus — Decimal | None coercion + falsy-unset semantics
# ---------------------------------------------------------------------------


def test_create_order_status_handles_empty_proto():
    proto = OrderStatus_pb2.OrderStatus()
    status = createOrderStatus(proto)
    assert status.filled is None
    assert status.remaining is None
    assert status.avgFillPrice is None
    assert not status.filled
    assert not status.avgFillPrice


def test_create_order_status_round_trip():
    proto = OrderStatus_pb2.OrderStatus()
    proto.orderId = 1
    proto.status = "Filled"
    proto.filled = "100"
    proto.remaining = "0"
    proto.avgFillPrice = 50.5
    proto.permId = 99
    proto.lastFillPrice = 50.6
    proto.clientId = 42
    proto.whyHeld = ""
    status = createOrderStatus(proto)
    assert status.orderId == 1
    assert status.status == "Filled"
    assert status.filled == Decimal("100")
    assert status.remaining == Decimal("0")
    assert status.avgFillPrice == Decimal("50.5")
    assert status.lastFillPrice == Decimal("50.6")
    assert status.clientId == 42


def test_order_status_total_property_handles_none_safely():
    # The historic helper ``total = filled + remaining`` would raise on
    # mixed-with-None operands; the new property returns ``None``.
    proto = OrderStatus_pb2.OrderStatus()
    proto.filled = "30"
    # remaining stays unset
    status = createOrderStatus(proto)
    assert status.total is None


def test_order_status_total_property_sums_when_both_set():
    proto = OrderStatus_pb2.OrderStatus()
    proto.filled = "30"
    proto.remaining = "70"
    status = createOrderStatus(proto)
    assert status.total == Decimal("100")


# ---------------------------------------------------------------------------
# OrderState — wire commissionAndFees → domain commission
# ---------------------------------------------------------------------------


def test_create_order_state_renames_commission_and_fees_to_commission():
    proto = OrderState_pb2.OrderState()
    proto.status = "PreSubmitted"
    proto.commissionAndFees = 1.25
    proto.commissionAndFeesCurrency = "USD"
    state = createOrderState(proto)
    assert state.status == "PreSubmitted"
    assert state.commission == 1.25
    assert state.commissionCurrency == "USD"


def test_create_order_state_handles_empty_proto():
    proto = OrderState_pb2.OrderState()
    state = createOrderState(proto)
    assert state.status == ""


def test_create_order_state_reads_outside_rth_margins():
    proto = OrderState_pb2.OrderState()
    proto.initMarginBeforeOutsideRTH = 100.5
    proto.maintMarginAfterOutsideRTH = 200.75
    proto.equityWithLoanChangeOutsideRTH = -50.25
    proto.marginCurrency = "USD"
    state = createOrderState(proto)
    assert state.initMarginBeforeOutsideRTH == "100.5"
    assert state.maintMarginAfterOutsideRTH == "200.75"
    assert state.equityWithLoanChangeOutsideRTH == "-50.25"
    assert state.marginCurrency == "USD"


def test_create_order_state_reads_what_if_diagnostic_fields():
    """``suggestedSize`` + ``rejectReason`` show up on what-if responses."""
    proto = OrderState_pb2.OrderState()
    proto.suggestedSize = "50"
    proto.rejectReason = "Insufficient margin"
    state = createOrderState(proto)
    assert state.suggestedSize == Decimal("50")
    assert state.rejectReason == "Insufficient margin"


def test_create_order_state_reads_order_allocations():
    """FA / model orders deliver per-account allocation snapshots."""
    proto = OrderState_pb2.OrderState()
    a1 = proto.orderAllocations.add()
    a1.account = "U1234"
    a1.position = "100"
    a1.positionDesired = "150"
    a1.positionAfter = "100"
    a1.desiredAllocQty = "50"
    a1.allowedAllocQty = "25"
    a1.isMonetary = False
    a2 = proto.orderAllocations.add()
    a2.account = "U5678"
    a2.position = "200"

    state = createOrderState(proto)
    assert len(state.orderAllocations) == 2
    assert state.orderAllocations[0].account == "U1234"
    assert state.orderAllocations[0].position == Decimal("100")
    assert state.orderAllocations[0].desiredAllocQty == Decimal("50")
    assert state.orderAllocations[0].isMonetary is False
    assert state.orderAllocations[1].account == "U5678"
    # Unset fields stay None on the frozen domain record.
    assert state.orderAllocations[1].positionDesired is None


# ---------------------------------------------------------------------------
# Execution — wire isLiquidation/isPriceRevisionPending field renames
# ---------------------------------------------------------------------------


def test_create_execution_handles_empty_proto():
    proto = Execution_pb2.Execution()
    ex = createExecution(proto)
    assert ex.shares is None
    assert ex.price is None
    assert ex.cumQty is None
    assert not ex.shares
    assert not ex.price


def test_create_execution_round_trip():
    proto = Execution_pb2.Execution()
    proto.execId = "exec-1"
    proto.shares = "100"
    proto.price = 50.5
    proto.cumQty = "100"
    proto.avgPrice = 50.5
    proto.permId = 99
    proto.clientId = 42
    proto.isLiquidation = True
    proto.isPriceRevisionPending = True
    ex = createExecution(proto)
    assert ex.execId == "exec-1"
    assert ex.shares == Decimal("100")
    assert ex.price == Decimal("50.5")
    assert ex.cumQty == Decimal("100")
    assert ex.avgPrice == Decimal("50.5")
    assert ex.permId == 99
    assert ex.clientId == 42
    # Wire ``isLiquidation: bool`` maps to domain ``liquidation: int``.
    assert ex.liquidation == 1
    # Wire ``isPriceRevisionPending`` maps to domain ``pendingPriceRevision``.
    assert ex.pendingPriceRevision is True


def test_create_execution_garbage_decimal_lands_as_none():
    proto = Execution_pb2.Execution()
    proto.shares = "not-a-number"  # malformed wire data
    ex = createExecution(proto)
    assert ex.shares is None


def test_create_execution_reads_submitter_and_opt_exercise_type():
    """v3.0 wire fields ``submitter`` (str) and
    ``optExerciseOrLapseType`` (int) flow through to user code.
    """
    proto = Execution_pb2.Execution()
    proto.execId = "exec-2"
    proto.submitter = "Trader42"
    proto.optExerciseOrLapseType = 2
    ex = createExecution(proto)
    assert ex.submitter == "Trader42"
    assert ex.optExerciseOrLapseType == 2


# ---------------------------------------------------------------------------
# CommissionAndFeesReport — wire renames commission/yield
# ---------------------------------------------------------------------------


def test_create_commission_report_renames_fields():
    proto = CommissionAndFeesReport_pb2.CommissionAndFeesReport()
    proto.execId = "exec-1"
    proto.commissionAndFees = 1.25
    proto.currency = "USD"
    proto.realizedPNL = 10.5
    proto.bondYield = 0.05
    proto.yieldRedemptionDate = "20300101"
    report = createCommissionReport(proto)
    assert report.execId == "exec-1"
    assert report.commission == Decimal("1.25")
    assert report.currency == "USD"
    assert report.realizedPNL == Decimal("10.5")
    assert report.yield_ == Decimal("0.05")
    assert report.yieldRedemptionDate == 20300101


def test_create_commission_report_unparseable_redemption_date_safe():
    # If TWS ever sends a malformed yieldRedemptionDate, the converter
    # must not raise — we'd lose the entire commission report.
    proto = CommissionAndFeesReport_pb2.CommissionAndFeesReport()
    proto.execId = "exec-1"
    proto.commissionAndFees = 1.25
    proto.yieldRedemptionDate = "garbage"
    report = createCommissionReport(proto)
    assert report.yieldRedemptionDate == 0
    assert report.commission == Decimal("1.25")


def test_create_commission_report_handles_empty_proto():
    proto = CommissionAndFeesReport_pb2.CommissionAndFeesReport()
    report = createCommissionReport(proto)
    assert report.commission is None
    assert report.realizedPNL is None
    assert report.yield_ is None


# ---------------------------------------------------------------------------
# Envelopes — PlaceOrderRequest, OpenOrder, CancelOrderRequest
# ---------------------------------------------------------------------------


def test_place_order_request_round_trip_carries_clientId():
    """End-to-end clientId regression: build a complete
    PlaceOrderRequest with a non-zero clientId and assert the wire
    bytes carry it. This exercises the full encoder chain."""
    contract = Stock("AAPL", "SMART", "USD")
    order = LimitOrder("BUY", 100, 50.5)
    order.clientId = 7
    proto = createPlaceOrderRequestProto(orderId=42, contract=contract, order=order)
    assert proto.orderId == 42
    assert proto.order.clientId == 7
    # Round-trip through serialization to confirm the wire bytes carry
    # clientId (this is what TWS would actually receive).
    wire = proto.SerializeToString()
    decoded = PlaceOrderRequest_pb2.PlaceOrderRequest()
    decoded.ParseFromString(wire)
    assert decoded.order.clientId == 7
    assert decoded.order.totalQuantity == "100"
    assert decoded.order.lmtPrice == 50.5


def test_open_order_envelope_decodes_all_three_inner_messages():
    proto = OpenOrder_pb2.OpenOrder()
    proto.orderId = 1
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    proto.order.clientId = 11
    proto.order.action = "BUY"
    proto.order.totalQuantity = "100"
    proto.orderState.status = "Submitted"
    orderId, contract, order, state = createOpenOrder(proto)
    assert orderId == 1
    assert contract.symbol == "AAPL"
    assert order.clientId == 11
    assert order.totalQuantity == Decimal("100")
    assert state.status == "Submitted"


def test_open_order_envelope_handles_missing_inner_messages():
    # If TWS sends a partial OpenOrder (only orderId), the decoder
    # must still produce a usable shape with default-constructed
    # contract / order / state — never raise.
    proto = OpenOrder_pb2.OpenOrder()
    proto.orderId = 1
    orderId, contract, order, state = createOpenOrder(proto)
    assert orderId == 1
    assert contract.symbol == ""
    assert order.clientId == 0
    assert state.status == ""


def test_cancel_order_request_carries_manual_cancel_time():
    proto = createCancelOrderRequestProto(
        orderId=42, manualOrderCancelTime="20300101 09:30:00"
    )
    assert proto.orderId == 42
    assert proto.orderCancel.manualOrderCancelTime == "20300101 09:30:00"


def test_cancel_order_request_skips_unset_optional_fields():
    proto = createCancelOrderRequestProto(orderId=42)
    assert proto.orderId == 42
    # Empty optionals stay unset on the wire.
    assert not proto.orderCancel.HasField("manualOrderCancelTime")
    assert not proto.orderCancel.HasField("extOperator")


# ---------------------------------------------------------------------------
# Parity with IBKR's ``decoder_utils.decodeOrder`` — every field IBKR
# reads, we read.
#
# Wire fields IBKR's reference reads that our domain ``Order`` dataclass
# does NOT carry (and therefore the converter intentionally drops):
# ``customerAccount``, ``professionalCustomer``, ``bondAccruedInterest``,
# ``includeOvernight``, ``manualOrderIndicator``, ``submitter``,
# ``deactivate``, ``postOnly``, ``allowPreOpen``, ``ignoreOpenAuction``,
# ``seekPriceImprovement``, ``whatIfType``, ``hedgeMaxSize``. Adding
# those to the converter without dataclass support would silently
# swallow the wire data; instead we drop the wire field intentionally
# until the dataclass grows the matching attribute.
# ---------------------------------------------------------------------------


def test_create_order_reads_every_field_decoder_utils_reads():
    """Mirror IBKR's ``decoder_utils.decodeOrder`` field list.

    Every wire field IBKR's reference reads (and that maps to a real
    domain attribute) MUST round-trip here. If this test fails because
    a field IBKR newly reads landed unread, the converter is silently
    losing wire state — fail loud.
    """
    from ib_async._pb import OrderCondition_pb2

    proto = Order_pb2.Order()
    proto.orderId = 11
    proto.action = "BUY"
    proto.totalQuantity = "100"
    proto.orderType = "LMT"
    proto.lmtPrice = 50.5
    proto.auxPrice = 0.10
    proto.tif = "GTC"
    proto.ocaGroup = "grp-1"
    proto.account = "DU111"
    proto.openClose = "O"
    proto.origin = 1
    proto.orderRef = "ref-1"
    proto.clientId = 7
    proto.permId = 9999
    proto.outsideRth = True
    proto.hidden = True
    proto.discretionaryAmt = 0.5
    proto.goodAfterTime = "20300101 09:30:00"
    proto.faGroup = "fa-grp"
    proto.faMethod = "PctChange"
    proto.faPercentage = "10"
    proto.modelCode = "model"
    proto.goodTillDate = "20301231 16:00:00"
    proto.rule80A = "I"
    proto.percentOffset = 0.25
    proto.settlingFirm = "sf"
    proto.shortSaleSlot = 1
    proto.designatedLocation = "loc"
    proto.exemptCode = -1
    proto.startingPrice = 49.0
    proto.stockRefPrice = 50.0
    proto.delta = 0.6
    proto.stockRangeLower = 48.0
    proto.stockRangeUpper = 52.0
    proto.displaySize = 10
    proto.blockOrder = True
    proto.sweepToFill = True
    proto.allOrNone = True
    proto.minQty = 5
    proto.ocaType = 2
    proto.parentId = 12345
    proto.triggerMethod = 1
    proto.volatility = 0.3
    proto.volatilityType = 1
    proto.deltaNeutralOrderType = "MKT"
    proto.deltaNeutralAuxPrice = 0.05
    proto.deltaNeutralConId = 99
    proto.deltaNeutralSettlingFirm = "dnsf"
    proto.deltaNeutralClearingAccount = "dnca"
    proto.deltaNeutralClearingIntent = "dnci"
    proto.deltaNeutralOpenClose = "C"
    proto.deltaNeutralShortSale = True
    proto.deltaNeutralShortSaleSlot = 2
    proto.deltaNeutralDesignatedLocation = "dnloc"
    proto.continuousUpdate = True
    proto.referencePriceType = 1
    proto.trailStopPrice = 49.5
    proto.trailingPercent = 0.05
    proto.smartComboRoutingParams["leg"] = "1"
    proto.scaleInitLevelSize = 100
    proto.scaleSubsLevelSize = 200
    proto.scalePriceIncrement = 0.5
    proto.scalePriceAdjustValue = 0.1
    proto.scalePriceAdjustInterval = 60
    proto.scaleProfitOffset = 1.0
    proto.scaleAutoReset = True
    proto.scaleInitPosition = 0
    proto.scaleInitFillQty = 10
    proto.scaleRandomPercent = True
    proto.hedgeType = "D"
    proto.hedgeParam = "0.5"
    proto.optOutSmartRouting = True
    proto.clearingAccount = "ca"
    proto.clearingIntent = "ci"
    proto.notHeld = True
    proto.algoStrategy = "Adaptive"
    proto.algoParams["adaptivePriority"] = "Normal"
    proto.solicited = True
    proto.whatIf = True
    proto.randomizeSize = True
    proto.randomizePrice = True
    proto.referenceContractId = 7
    proto.isPeggedChangeAmountDecrease = True
    proto.peggedChangeAmount = 0.05
    proto.referenceChangeAmount = 0.1
    proto.referenceExchangeId = "NASDAQ"
    # Conditions: one PriceCondition (type=1).
    cond = OrderCondition_pb2.OrderCondition()
    cond.type = 1
    cond.isConjunctionConnection = True
    cond.isMore = True
    cond.conId = 12345
    cond.exchange = "SMART"
    cond.price = 99.5
    cond.triggerMethod = 0
    proto.conditions.append(cond)
    proto.conditionsIgnoreRth = True
    proto.conditionsCancelOrder = True
    proto.adjustedOrderType = "STP"
    proto.triggerPrice = 48.0
    proto.lmtPriceOffset = 0.05
    proto.adjustedStopPrice = 47.5
    proto.adjustedStopLimitPrice = 47.0
    proto.adjustedTrailingAmount = 0.10
    proto.adjustableTrailingUnit = 1
    proto.softDollarTier.name = "tier-name"
    proto.softDollarTier.value = "tier-value"
    proto.softDollarTier.displayName = "Tier Display"
    proto.cashQty = 5000.0
    proto.dontUseAutoPriceForHedge = True
    proto.isOmsContainer = True
    proto.discretionaryUpToLimitPrice = True
    proto.usePriceMgmtAlgo = 1
    proto.duration = 86400
    proto.postToAts = 30
    proto.autoCancelParent = True
    proto.minTradeQty = 10
    proto.minCompeteSize = 100
    proto.competeAgainstBestOffset = 0.01
    proto.midOffsetAtWhole = 0.005
    proto.midOffsetAtHalf = 0.0025
    proto.autoCancelDate = "20301231"
    proto.filledQuantity = "50"
    proto.refFuturesConId = 8888
    proto.shareholder = "Shareholder"
    proto.routeMarketableToBbo = 1
    proto.parentPermId = 1234567890
    proto.imbalanceOnly = True
    proto.activeStartTime = "20300101 09:30:00 US/Eastern"
    proto.activeStopTime = "20300101 16:00:00 US/Eastern"

    order = createOrder(proto)

    # Identifiers
    assert order.orderId == 11
    assert order.clientId == 7
    assert order.permId == 9999
    assert order.parentId == 12345
    # Primary
    assert order.action == "BUY"
    assert order.totalQuantity == Decimal("100")
    assert order.orderType == "LMT"
    assert order.lmtPrice == Decimal("50.5")
    assert order.auxPrice == Decimal("0.1")
    assert order.tif == "GTC"
    # Routing / clearing
    assert order.ocaGroup == "grp-1"
    assert order.account == "DU111"
    assert order.openClose == "O"
    assert order.origin == 1
    assert order.orderRef == "ref-1"
    assert order.outsideRth is True
    assert order.hidden is True
    assert order.discretionaryAmt == 0.5
    assert order.goodAfterTime == "20300101 09:30:00"
    # FA
    assert order.faGroup == "fa-grp"
    assert order.faMethod == "PctChange"
    assert order.faPercentage == "10"
    assert order.modelCode == "model"
    assert order.goodTillDate == "20301231 16:00:00"
    assert order.rule80A == "I"
    assert order.percentOffset == 0.25
    assert order.settlingFirm == "sf"
    assert order.shortSaleSlot == 1
    assert order.designatedLocation == "loc"
    assert order.exemptCode == -1
    # Box / vol auction
    assert order.startingPrice == 49.0
    assert order.stockRefPrice == 50.0
    assert order.delta == Decimal("0.6")
    assert order.stockRangeLower == 48.0
    assert order.stockRangeUpper == 52.0
    assert order.displaySize == 10
    assert order.blockOrder is True
    assert order.sweepToFill is True
    assert order.allOrNone is True
    assert order.minQty == 5
    assert order.ocaType == 2
    assert order.triggerMethod == 1
    # Volatility / delta-neutral
    assert order.volatility == Decimal("0.3")
    assert order.volatilityType == 1
    assert order.deltaNeutralOrderType == "MKT"
    assert order.deltaNeutralAuxPrice == Decimal("0.05")
    assert order.deltaNeutralConId == 99
    assert order.deltaNeutralSettlingFirm == "dnsf"
    assert order.deltaNeutralClearingAccount == "dnca"
    assert order.deltaNeutralClearingIntent == "dnci"
    assert order.deltaNeutralOpenClose == "C"
    assert order.deltaNeutralShortSale is True
    assert order.deltaNeutralShortSaleSlot == 2
    assert order.deltaNeutralDesignatedLocation == "dnloc"
    assert order.continuousUpdate is True
    assert order.referencePriceType == 1
    # Trail
    assert order.trailStopPrice == Decimal("49.5")
    assert order.trailingPercent == Decimal("0.05")
    # Smart combo routing
    assert len(order.smartComboRoutingParams) == 1
    assert order.smartComboRoutingParams[0].tag == "leg"
    assert order.smartComboRoutingParams[0].value == "1"
    # Scale
    assert order.scaleInitLevelSize == 100
    assert order.scaleSubsLevelSize == 200
    assert order.scalePriceIncrement == Decimal("0.5")
    assert order.scalePriceAdjustValue == Decimal("0.1")
    assert order.scalePriceAdjustInterval == 60
    assert order.scaleProfitOffset == Decimal("1.0")
    assert order.scaleAutoReset is True
    assert order.scaleInitPosition == 0
    assert order.scaleInitFillQty == 10
    assert order.scaleRandomPercent is True
    # Hedge
    assert order.hedgeType == "D"
    assert order.hedgeParam == "0.5"
    # Misc
    assert order.optOutSmartRouting is True
    assert order.clearingAccount == "ca"
    assert order.clearingIntent == "ci"
    assert order.notHeld is True
    # Algo
    assert order.algoStrategy == "Adaptive"
    assert len(order.algoParams) == 1
    assert order.algoParams[0].tag == "adaptivePriority"
    assert order.algoParams[0].value == "Normal"
    # Booleans
    assert order.solicited is True
    assert order.whatIf is True
    assert order.randomizeSize is True
    assert order.randomizePrice is True
    # Pegged-to-benchmark
    assert order.referenceContractId == 7
    assert order.isPeggedChangeAmountDecrease is True
    assert order.peggedChangeAmount == 0.05
    assert order.referenceChangeAmount == 0.1
    assert order.referenceExchangeId == "NASDAQ"
    # Conditions
    assert len(order.conditions) == 1
    pc = order.conditions[0]
    from ib_async.order import PriceCondition

    assert isinstance(pc, PriceCondition)
    assert pc.conjunction == "a"
    assert pc.isMore is True
    assert pc.conId == 12345
    assert pc.exch == "SMART"
    assert pc.price == 99.5
    assert order.conditionsIgnoreRth is True
    assert order.conditionsCancelOrder is True
    # Adjustable
    assert order.adjustedOrderType == "STP"
    assert order.triggerPrice == Decimal("48")
    assert order.lmtPriceOffset == Decimal("0.05")
    assert order.adjustedStopPrice == Decimal("47.5")
    assert order.adjustedStopLimitPrice == Decimal("47")
    assert order.adjustedTrailingAmount == Decimal("0.1")
    assert order.adjustableTrailingUnit == 1
    # Soft-dollar tier
    assert order.softDollarTier.name == "tier-name"
    assert order.softDollarTier.val == "tier-value"
    assert order.softDollarTier.displayName == "Tier Display"
    # Cash + bool extras
    assert order.cashQty == 5000.0
    assert order.dontUseAutoPriceForHedge is True
    assert order.isOmsContainer is True
    assert order.discretionaryUpToLimitPrice is True
    # Wire is int(1); domain is bool.
    assert order.usePriceMgmtAlgo is True
    assert order.duration == 86400
    assert order.postToAts == 30
    assert order.autoCancelParent is True
    # Mid-price competition
    assert order.minTradeQty == 10
    assert order.minCompeteSize == 100
    assert order.competeAgainstBestOffset == Decimal("0.01")
    assert order.midOffsetAtWhole == Decimal("0.005")
    assert order.midOffsetAtHalf == Decimal("0.0025")
    # Completed-order
    assert order.autoCancelDate == "20301231"
    assert order.filledQuantity == Decimal("50")
    assert order.refFuturesConId == 8888
    assert order.shareholder == "Shareholder"
    # Wire int(1) -> domain bool True.
    assert order.routeMarketableToBbo is True
    assert order.parentPermId == 1234567890
    assert order.imbalanceOnly is True
    # Active start / stop time
    assert order.activeStartTime == "20300101 09:30:00 US/Eastern"
    assert order.activeStopTime == "20300101 16:00:00 US/Eastern"


def test_create_order_minimal_proto_leaves_unset_fields_at_defaults():
    """A proto with ONLY commonly-set fields produces an Order whose
    other fields stay at the dataclass defaults — ``None`` for
    ``Decimal | None``, ``False``/``0``/``""`` for primitives,
    ``[]`` for repeated fields. If a converter ever spuriously
    populates an unset field with a sentinel value, this test fails.
    """
    proto = Order_pb2.Order()
    proto.action = "BUY"
    proto.totalQuantity = "100"
    proto.lmtPrice = 50.5
    proto.orderType = "LMT"

    order = createOrder(proto)
    # Set fields land
    assert order.action == "BUY"
    assert order.totalQuantity == Decimal("100")
    assert order.lmtPrice == Decimal("50.5")
    assert order.orderType == "LMT"
    # Decimal | None unset stays None
    assert order.auxPrice is None
    assert order.trailStopPrice is None
    assert order.trailingPercent is None
    assert order.triggerPrice is None
    assert order.lmtPriceOffset is None
    assert order.adjustedStopPrice is None
    assert order.adjustedStopLimitPrice is None
    assert order.adjustedTrailingAmount is None
    assert order.filledQuantity is None
    # Primitives stay at their dataclass defaults
    assert order.tif == ""
    assert order.account == ""
    assert order.outsideRth is False
    assert order.hidden is False
    assert order.allOrNone is False
    assert order.transmit is True  # dataclass default
    assert order.whatIf is False
    assert order.solicited is False
    assert order.usePriceMgmtAlgo is False
    assert order.routeMarketableToBbo is False
    # Repeated fields stay empty
    assert order.algoStrategy == ""
    assert order.algoParams == []
    assert order.smartComboRoutingParams == []
    assert order.orderMiscOptions == []
    assert order.conditions == []
    assert order.orderComboLegs == []
    # Soft-dollar tier stays at default-empty (falsy)
    assert not order.softDollarTier


def test_create_order_combo_legs_sourced_from_contract_proto():
    """``orderComboLegs`` per-leg prices live on the CONTRACT proto, not
    the order proto. ``createOrder`` must read them from the contract
    proto when supplied."""
    from ib_async._pb import ComboLeg_pb2

    contractProto = Contract_pb2.Contract()
    leg = ComboLeg_pb2.ComboLeg()
    leg.perLegPrice = 1.25
    contractProto.comboLegs.append(leg)

    orderProto = Order_pb2.Order()
    orderProto.action = "BUY"

    order = createOrder(orderProto, contractProto=contractProto)
    assert len(order.orderComboLegs) == 1
    assert order.orderComboLegs[0].price == 1.25


def test_create_order_combo_legs_default_empty_when_no_contract_proto():
    """Without a contract proto, ``orderComboLegs`` stays at its
    dataclass default empty list — the order proto alone does NOT
    carry per-leg prices."""
    proto = Order_pb2.Order()
    proto.action = "BUY"
    order = createOrder(proto)
    assert order.orderComboLegs == []


def test_open_order_envelope_propagates_combo_legs_to_order():
    """End-to-end: an OpenOrder envelope with combo legs on its
    contract message must surface those legs on the decoded
    ``Order.orderComboLegs``."""
    from ib_async._pb import ComboLeg_pb2

    proto = OpenOrder_pb2.OpenOrder()
    proto.orderId = 1
    proto.contract.symbol = "AAPL"
    leg = ComboLeg_pb2.ComboLeg()
    leg.perLegPrice = 2.5
    proto.contract.comboLegs.append(leg)
    proto.order.action = "BUY"

    _orderId, _contract, order, _state = createOpenOrder(proto)
    assert len(order.orderComboLegs) == 1
    assert order.orderComboLegs[0].price == 2.5


def test_create_order_conditions_decode_each_subclass():
    """Each OrderCondition subclass (price/time/margin/exec/volume/pct)
    must round-trip the subclass-specific fields. IBKR's reference
    dispatches on ``type``; we mirror that table."""
    from ib_async._pb import OrderCondition_pb2
    from ib_async.order import (
        ExecutionCondition,
        MarginCondition,
        PercentChangeCondition,
        PriceCondition,
        TimeCondition,
        VolumeCondition,
    )

    proto = Order_pb2.Order()

    # type=1 PriceCondition
    c1 = OrderCondition_pb2.OrderCondition()
    c1.type = 1
    c1.price = 100.0
    c1.conId = 1
    c1.exchange = "SMART"
    c1.triggerMethod = 1
    c1.isMore = True
    proto.conditions.append(c1)
    # type=3 TimeCondition
    c3 = OrderCondition_pb2.OrderCondition()
    c3.type = 3
    c3.time = "20300101 09:30:00"
    c3.isMore = False
    proto.conditions.append(c3)
    # type=4 MarginCondition
    c4 = OrderCondition_pb2.OrderCondition()
    c4.type = 4
    c4.percent = 25
    c4.isMore = True
    proto.conditions.append(c4)
    # type=5 ExecutionCondition
    c5 = OrderCondition_pb2.OrderCondition()
    c5.type = 5
    c5.secType = "STK"
    c5.exchange = "NYSE"
    c5.symbol = "AAPL"
    proto.conditions.append(c5)
    # type=6 VolumeCondition
    c6 = OrderCondition_pb2.OrderCondition()
    c6.type = 6
    c6.volume = 1000
    c6.conId = 7
    c6.exchange = "NASDAQ"
    proto.conditions.append(c6)
    # type=7 PercentChangeCondition
    c7 = OrderCondition_pb2.OrderCondition()
    c7.type = 7
    c7.changePercent = 5.5
    c7.conId = 11
    c7.exchange = "ARCA"
    proto.conditions.append(c7)

    order = createOrder(proto)
    assert len(order.conditions) == 6
    assert isinstance(order.conditions[0], PriceCondition)
    assert order.conditions[0].price == 100.0
    assert order.conditions[0].conId == 1
    assert order.conditions[0].exch == "SMART"
    assert order.conditions[0].triggerMethod == 1
    assert isinstance(order.conditions[1], TimeCondition)
    assert order.conditions[1].time == "20300101 09:30:00"
    assert order.conditions[1].isMore is False
    assert isinstance(order.conditions[2], MarginCondition)
    assert order.conditions[2].percent == 25
    assert isinstance(order.conditions[3], ExecutionCondition)
    assert order.conditions[3].secType == "STK"
    assert order.conditions[3].exch == "NYSE"
    assert order.conditions[3].symbol == "AAPL"
    assert isinstance(order.conditions[4], VolumeCondition)
    assert order.conditions[4].volume == 1000
    assert order.conditions[4].conId == 7
    assert order.conditions[4].exch == "NASDAQ"
    assert isinstance(order.conditions[5], PercentChangeCondition)
    assert order.conditions[5].changePercent == 5.5
    assert order.conditions[5].conId == 11
    assert order.conditions[5].exch == "ARCA"


# ---------------------------------------------------------------------------
# Attached-order cross-references — slOrderId / slOrderType / ptOrderId /
# ptOrderType ride on PlaceOrderRequest.attachedOrders, not on Order
# itself. The fields default to UNSET_INTEGER / "" so unset domain
# instances must NOT write sentinel values to the wire.
# ---------------------------------------------------------------------------


def test_attached_orders_round_trip_through_place_order_request():
    order = LimitOrder(
        "BUY",
        100,
        50.0,
        slOrderId=11,
        slOrderType="STP",
        ptOrderId=22,
        ptOrderType="LMT",
    )
    proto = createPlaceOrderRequestProto(7, Stock("AAPL", "SMART", "USD"), order)
    raw = proto.SerializeToString()
    parsed = PlaceOrderRequest_pb2.PlaceOrderRequest()
    parsed.ParseFromString(raw)
    assert parsed.HasField("attachedOrders")
    ao = parsed.attachedOrders
    assert ao.slOrderId == 11
    assert ao.slOrderType == "STP"
    assert ao.ptOrderId == 22
    assert ao.ptOrderType == "LMT"


def test_attached_orders_unset_fields_stay_unset_on_wire():
    order = LimitOrder("BUY", 100, 50.0)
    proto = createPlaceOrderRequestProto(7, Stock("AAPL", "SMART", "USD"), order)
    ao = proto.attachedOrders
    # UNSET_INTEGER / empty-string defaults must NOT bleed through —
    # otherwise the broker sees bogus order ids.
    assert not ao.HasField("slOrderId")
    assert not ao.HasField("slOrderType")
    assert not ao.HasField("ptOrderId")
    assert not ao.HasField("ptOrderType")


def test_attached_orders_pb_message_round_trips_independently():
    proto = AttachedOrders_pb2.AttachedOrders()
    proto.slOrderId = 5
    proto.slOrderType = "STP"
    proto.ptOrderId = 6
    proto.ptOrderType = "LMT"
    raw = proto.SerializeToString()
    parsed = AttachedOrders_pb2.AttachedOrders()
    parsed.ParseFromString(raw)
    assert parsed.slOrderId == 5
    assert parsed.ptOrderType == "LMT"


# ---------------------------------------------------------------------------
# ExecutionFilter — lastNDays + specificDates ship past
# MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS (200).
# ---------------------------------------------------------------------------


def test_execution_filter_carries_last_n_days_and_specific_dates():
    f = ExecutionFilter(lastNDays=5, specificDates=[20260101, 20260102])
    assert f.lastNDays == 5
    assert f.specificDates == [20260101, 20260102]


def test_execution_filter_proto_round_trips_last_n_days_and_specific_dates():
    f = ExecutionFilter(lastNDays=7, specificDates=[20260301, 20260302])
    proto = createExecutionFilterProto(f)
    raw = proto.SerializeToString()
    parsed = ExecutionFilter_pb2.ExecutionFilter()
    parsed.ParseFromString(raw)
    assert parsed.lastNDays == 7
    assert list(parsed.specificDates) == [20260301, 20260302]


def test_execution_filter_proto_skips_unset_last_n_days():
    f = ExecutionFilter()
    proto = createExecutionFilterProto(f)
    # UNSET_INTEGER must NOT write through — otherwise the server
    # sees a sentinel-valued day count.
    assert not proto.HasField("lastNDays")
    assert len(proto.specificDates) == 0


def test_execution_request_proto_carries_filter_with_new_fields():
    f = ExecutionFilter(clientId=3, lastNDays=2, specificDates=[20260101])
    proto = createExecutionRequestProto(99, f)
    raw = proto.SerializeToString()
    parsed = ExecutionRequest_pb2.ExecutionRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 99
    assert parsed.executionFilter.clientId == 3
    assert parsed.executionFilter.lastNDays == 2
    assert list(parsed.executionFilter.specificDates) == [20260101]
