"""IBKR UNSET sentinels normalize to dataclass defaults on decode.

The wire ships ``1.7976931348623157E308`` (UNSET_DOUBLE) and ``2147483647``
(UNSET_INTEGER) for fields the broker did not set. In the v3 None-dialect an
unset field IS its dataclass default, so ``Decoder.parse`` must never leak a
sentinel into user-visible objects — an openOrder echo previously stamped
``volatility=1.7976931348623157e+308`` onto every plain LMT order.
"""

from decimal import Decimal

from ib_async import IB
from ib_async.decoder import Decoder
from ib_async.order import Order
from ib_async.util import UNSET_DOUBLE, UNSET_INTEGER


def _parse(order: Order) -> Order:
    ib = IB()
    decoder = Decoder(ib.wrapper, serverVersion=176)
    decoder.parse(order)
    return order


def test_unset_double_sentinel_becomes_the_none_default() -> None:
    order = Order()
    order.volatility = f"{UNSET_DOUBLE!r}"
    _parse(order)
    assert order.volatility is None


def test_wire_uppercase_sentinel_form_also_normalizes() -> None:
    order = Order()
    order.volatility = "1.7976931348623157E308"
    _parse(order)
    assert order.volatility is None


def test_real_values_survive_untouched() -> None:
    order = Order()
    order.volatility = "0.42"
    order.lmtPrice = "29825.50"
    _parse(order)
    assert order.volatility == Decimal("0.42")
    assert order.lmtPrice == Decimal("29825.50")


def test_unset_integer_sentinel_becomes_the_field_default() -> None:
    order = Order()
    order.volatilityType = str(UNSET_INTEGER)
    _parse(order)
    assert order.volatilityType is None


def test_place_order_never_stamps_a_sentinel_onto_the_callers_order() -> None:
    """client.placeOrder resets non-VOL volatility to None (the v3 unset),
    never to the UNSET_DOUBLE float — the operator-visible Order object must
    not carry wire sentinels."""

    ib = IB()
    client = ib.client
    sent: list[tuple] = []
    client._tryProto = lambda msg_id, thunk: True  # capture-side: skip the wire
    from ib_async.contract import Future
    from ib_async.order import LimitOrder

    contract = Future(symbol="MNQ", exchange="CME", currency="USD")
    order = LimitOrder("BUY", 1, 100.0)
    order.volatility = UNSET_DOUBLE  # a TWS-populated cached order
    client.placeOrder(9999, contract, order)
    assert order.volatility is None
    del sent
