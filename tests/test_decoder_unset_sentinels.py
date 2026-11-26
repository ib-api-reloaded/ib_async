"""IBKR UNSET sentinels normalize to dataclass defaults on decode.

TWS can send ``1.7976931348623157E308`` (UNSET_DOUBLE) for a field the
broker did not set. In the v3 None-dialect an unset field is its dataclass
default, so the decoder must never put a sentinel into a user-visible
object. An openOrder echo once stamped ``volatility=1.7976931348623157e+308``
onto every plain LMT order.
"""

from __future__ import annotations

import sys
from decimal import Decimal

from ib_async import IB
from ib_async._pb import OpenOrder_pb2
from ib_async.contract import Future
from ib_async.ordertypes import LimitOrder
from ib_async.util import UNSET_DOUBLE

OPEN_ORDER = 5


def test_open_order_unset_double_volatility_becomes_the_none_default() -> None:
    ib = IB()
    ib.wrapper.clientId = 0
    message = OpenOrder_pb2.OpenOrder(orderId=42)
    message.contract.symbol = "MNQ"
    message.contract.secType = "FUT"
    message.order.orderId = 42
    message.order.clientId = 0
    message.order.permId = 999
    message.order.orderType = "LMT"
    message.order.lmtPrice = 29825.50
    message.order.volatility = sys.float_info.max
    message.orderState.status = "Submitted"

    ib.client.decoder.processProtoBuf(OPEN_ORDER, message.SerializeToString())

    order = ib.wrapper.trades[(0, 42)].order
    assert order.volatility is None
    assert order.lmtPrice == Decimal("29825.5")


def test_place_order_never_stamps_a_sentinel_onto_the_callers_order() -> None:
    """client.placeOrder resets non-VOL volatility to None (the v3 unset),
    never to the UNSET_DOUBLE float. The caller's Order object must not
    carry wire sentinels."""

    ib = IB()
    client = ib.client
    client.connState = client.CONNECTED
    client.conn.sendMsg = lambda msg: None  # skip the wire

    contract = Future(symbol="MNQ", exchange="CME", currency="USD")
    order = LimitOrder("BUY", 1, 100.0)
    order.volatility = UNSET_DOUBLE  # a TWS-populated cached order
    client.placeOrder(9999, contract, order)
    assert order.volatility is None
