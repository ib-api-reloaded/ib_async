"""What TWS / IB Gateway 10.53 added: server version 227's combo implied
bid and ask ticks, server version 228's early pre-session order fields,
and the order's working state on OrderState."""

from __future__ import annotations

import struct
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._pb import Order_pb2, OrderState_pb2, PlaceOrderRequest_pb2
from ib_async._pb_msgids import PROTOBUF_MSG_ID
from ib_async._proto.orders import createOrder, createOrderProto, createOrderState

EARLY_FIELDS = ["includeEarly", "conditionsIncludeEarly"]
PLACE_ORDER = 3


def _connectedIB(serverVersion: int) -> ibi.IB:
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.connState = ib.client.CONNECTED
    ib.client._apiReady = True
    ib.client._reqIdSeq = 1
    ib.client.sendMsg = MagicMock()
    return ib


def _sentOrder(ib: ibi.IB) -> Order_pb2.Order:
    """The Order of the one placeOrder request the client sent."""
    (body,) = ib.client.sendMsg.call_args.args
    (wireMsgId,) = struct.unpack(">I", body[:4])
    assert wireMsgId == PLACE_ORDER + PROTOBUF_MSG_ID
    request = PlaceOrderRequest_pb2.PlaceOrderRequest()
    request.ParseFromString(body[4:])
    return request.order


def _contract() -> ibi.Contract:
    return ibi.Stock("AAPL", "SMART", "USD", conId=265598)


@pytest.mark.parametrize("field", EARLY_FIELDS)
def test_early_session_field_round_trips(field: str):
    proto = createOrderProto(ibi.LimitOrder("BUY", 100, 50, **{field: True}))

    assert getattr(proto, field) is True
    assert getattr(createOrder(proto), field) is True
    assert not createOrderProto(ibi.LimitOrder("BUY", 100, 50)).HasField(field)


@pytest.mark.parametrize("field", EARLY_FIELDS)
def test_server_228_sends_an_early_session_order(field: str):
    ib = _connectedIB(228)

    ib.placeOrder(_contract(), ibi.LimitOrder("BUY", 100, 50, **{field: True}))

    assert getattr(_sentOrder(ib), field) is True


@pytest.mark.parametrize("field", EARLY_FIELDS)
def test_older_server_refuses_an_early_session_order_and_sends_nothing(field: str):
    ib = _connectedIB(226)

    with pytest.raises(ValueError, match=f"no field for {field}"):
        ib.placeOrder(_contract(), ibi.LimitOrder("BUY", 100, 50, **{field: True}))

    ib.client.sendMsg.assert_not_called()
    assert ib.wrapper.trades == {}


def test_older_server_still_takes_an_overnight_order():
    ib = _connectedIB(226)

    ib.placeOrder(_contract(), ibi.LimitOrder("BUY", 100, 50, includeOvernight=True))

    assert _sentOrder(ib).includeOvernight is True


def test_combo_implied_bid_and_ask_reach_the_ticker():
    ib = ibi.IB()
    contract = _contract()
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    ib.wrapper.subscriptions._ticker_by_reqid[7] = ticker

    ib.wrapper.priceSizeTick(7, 112, 1.25, 0.0)
    ib.wrapper.priceSizeTick(7, 113, 1.40, 0.0)

    assert (ticker.comboImpliedBid, ticker.comboImpliedAsk) == (1.25, 1.40)


def test_order_state_reads_the_working_state():
    proto = OrderState_pb2.OrderState(
        averagePrice=101.5,
        submittedQuantity="300",
        currentPrice=101.75,
        brokerToClientAssignedNumber="B2C-1",
        exchangeToFund="NYSE",
        recentSubmitModifyTime="20261127 10:00:01",
        submitTime="20261127 09:59:59",
        routingStrategy="SMART",
        assignedTo="desk",
        trailingKey="T1",
        crossType="X",
        ticketOwnerSession="S1",
        scaleProgress=2,
    )

    state = createOrderState(proto)

    assert (state.averagePrice, state.submittedQuantity, state.currentPrice) == (
        Decimal("101.5"),
        Decimal(300),
        Decimal("101.75"),
    )
    assert (
        state.brokerToClientAssignedNumber,
        state.exchangeToFund,
        state.recentSubmitModifyTime,
        state.submitTime,
        state.routingStrategy,
        state.assignedTo,
        state.trailingKey,
        state.crossType,
        state.ticketOwnerSession,
        state.scaleProgress,
    ) == (
        "B2C-1",
        "NYSE",
        "20261127 10:00:01",
        "20261127 09:59:59",
        "SMART",
        "desk",
        "T1",
        "X",
        "S1",
        2,
    )


def test_order_state_without_the_working_state_leaves_it_unset():
    state = createOrderState(OrderState_pb2.OrderState())

    assert (state.averagePrice, state.submittedQuantity, state.scaleProgress) == (
        None,
        None,
        None,
    )
    assert state.routingStrategy == ""
