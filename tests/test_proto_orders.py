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
    CommissionAndFeesReport_pb2,
    Execution_pb2,
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
    createOpenOrder,
    createOrder,
    createOrderProto,
    createOrderState,
    createOrderStatus,
    createPlaceOrderRequestProto,
)
from ib_async.contract import Stock
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
        orderId=42, manualCancelOrderTime="20300101 09:30:00"
    )
    assert proto.orderId == 42
    assert proto.orderCancel.manualOrderCancelTime == "20300101 09:30:00"


def test_cancel_order_request_skips_unset_optional_fields():
    proto = createCancelOrderRequestProto(orderId=42)
    assert proto.orderId == 42
    # Empty optionals stay unset on the wire.
    assert not proto.orderCancel.HasField("manualOrderCancelTime")
    assert not proto.orderCancel.HasField("extOperator")
