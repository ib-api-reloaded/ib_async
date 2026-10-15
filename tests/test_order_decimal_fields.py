"""Every Decimal field of Order is coerced on construction, not a hand-kept subset."""

from __future__ import annotations

import dataclasses
import math
from decimal import Decimal

from ib_async import Order
from ib_async.order import COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID


def test_every_decimal_field_coerces_floats_and_strings():
    decimalFields = [
        f.name for f in dataclasses.fields(Order) if f.type == "Decimal | None"
    ]
    assert len(decimalFields) > 11
    order = Order(**dict.fromkeys(decimalFields, 1.25))
    for name in decimalFields:
        assert getattr(order, name) == Decimal("1.25"), name


def test_pegged_to_stock_fields_from_floats():
    order = Order(startingPrice=1.5, stockRefPrice=99.2, delta=0.5, cashQty="100.25")
    assert (order.startingPrice, order.stockRefPrice, order.delta, order.cashQty) == (
        Decimal("1.5"),
        Decimal("99.2"),
        Decimal("0.5"),
        Decimal("100.25"),
    )


def test_compete_up_to_mid_survives_construction():
    """IBKR's COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID is +Infinity: the one
    field where it is a value, not garbage to unset."""
    for value in (math.inf, Decimal("Infinity"), "Infinity"):
        order = Order(competeAgainstBestOffset=value)
        assert order.competeAgainstBestOffset == COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID
    assert Order(competeAgainstBestOffset=0.01).competeAgainstBestOffset == (
        Decimal("0.01")
    )
    assert Order(lmtPrice=math.inf).lmtPrice is None
