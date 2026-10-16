"""Orders attached to another: adjustable stops and FX hedges.

An adjustment changes a stop, stop limit or trailing stop order once, into
another type, when the price penetrates its trigger price: pass it as
``adjust=`` to the order type (usually an order attached to a parent with
``parentId``). Brackets are ``IB.bracketOrder``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..order import Order
from .generated import MarketOrder
from .spec import Adjustment, FieldValue, OrderTypeError, checkedDecimal

__all__ = ["AdjustToStop", "AdjustToStopLimit", "AdjustToTrail", "FxHedgeOrder"]

# adjustableTrailingUnit: the trailing amount is a price, or a percentage.
TRAIL_BY_AMOUNT = 0
TRAIL_BY_PERCENT = 100

Price = Decimal | float | str


@dataclass(frozen=True, slots=True)
class _Price:
    """A price an adjustment takes: its parameter, the Order field it
    sets, and the value given."""

    name: str
    field: str
    value: Price | None


def _adjustment(
    title: str, adjustedOrderType: str, *prices: _Price, unit: int | None = None
) -> Adjustment:
    """An adjustment to ``adjustedOrderType`` setting ``prices``, every one
    of which must be given as a finite number, and the trailing ``unit``
    when it has one."""
    missing = [p.name for p in prices if p.value is None]
    if missing:
        raise OrderTypeError(f"{title} needs {', '.join(missing)}")
    fields = [FieldValue("adjustedOrderType", adjustedOrderType)]
    fields += [
        FieldValue(p.field, checkedDecimal(title, p.name, p.value)) for p in prices
    ]
    if unit is not None:
        fields.append(FieldValue("adjustableTrailingUnit", unit))
    return Adjustment(title, tuple(fields))


def AdjustToStop(triggerPrice: Price, stopPrice: Price) -> Adjustment:
    """Once the price penetrates ``triggerPrice``, become a stop at
    ``stopPrice`` (to move a stop to break-even, say).

    Example::

        StopOrder("SELL", 100, 45.00, parentId=parent.orderId,
                  adjust=AdjustToStop(triggerPrice=55.00, stopPrice=50.00))
    """
    return _adjustment(
        "Adjust to stop",
        "STP",
        _Price("triggerPrice", "triggerPrice", triggerPrice),
        _Price("stopPrice", "adjustedStopPrice", stopPrice),
    )


def AdjustToStopLimit(
    triggerPrice: Price, stopPrice: Price, limitPrice: Price
) -> Adjustment:
    """Once the price penetrates ``triggerPrice``, become a stop limit at
    ``stopPrice`` with limit price ``limitPrice``.

    Example::

        StopOrder("SELL", 100, 45.00, parentId=parent.orderId,
                  adjust=AdjustToStopLimit(55.00, 50.00, 49.50))
    """
    return _adjustment(
        "Adjust to stop limit",
        "STP LMT",
        _Price("triggerPrice", "triggerPrice", triggerPrice),
        _Price("stopPrice", "adjustedStopPrice", stopPrice),
        _Price("limitPrice", "adjustedStopLimitPrice", limitPrice),
    )


def AdjustToTrail(
    triggerPrice: Price,
    stopPrice: Price,
    *,
    trailingAmount: Price | None = None,
    trailingPercent: Price | None = None,
) -> Adjustment:
    """Once the price penetrates ``triggerPrice``, become a trailing stop
    with stop price ``stopPrice``, trailing by exactly one of
    ``trailingAmount`` (a price) or ``trailingPercent``.

    Example::

        StopOrder("SELL", 100, 45.00, parentId=parent.orderId,
                  adjust=AdjustToTrail(55.00, 50.00, trailingAmount=1.00))
    """
    if (trailingAmount is None) == (trailingPercent is None):
        raise OrderTypeError(
            "AdjustToTrail needs exactly one of trailingAmount, trailingPercent"
        )
    trailing = (
        _Price("trailingAmount", "adjustedTrailingAmount", trailingAmount)
        if trailingAmount is not None
        else _Price("trailingPercent", "adjustedTrailingAmount", trailingPercent)
    )
    return _adjustment(
        "Adjust to trailing stop",
        "TRAIL",
        _Price("triggerPrice", "triggerPrice", triggerPrice),
        _Price("stopPrice", "adjustedStopPrice", stopPrice),
        trailing,
        unit=TRAIL_BY_AMOUNT if trailingAmount is not None else TRAIL_BY_PERCENT,
    )


# The fields an FX hedge sets itself.
_FX_HEDGE_FIELDS = frozenset({"parentId", "hedgeType"})


def FxHedgeOrder(parent: Order, action: str, **kwargs: Any) -> Order:
    """A market order attached to ``parent`` that hedges its currency
    exposure: an FX hedge (hedgeType "F"), whose quantity is always 0.

    Place it on the currency pair's contract, after the parent, which is
    sent with transmit=False; ``parent`` needs its orderId.

    Example::

        parent = LimitOrder("BUY", 100, 50.00, orderId=ib.client.getReqId(),
                            transmit=False)
        ib.placeOrder(stockInEur, parent)
        ib.placeOrder(eurUsd, FxHedgeOrder(parent, "BUY"))
    """
    if not parent.orderId:
        raise OrderTypeError("FxHedgeOrder needs the parent's orderId set")
    clash = sorted(_FX_HEDGE_FIELDS & set(kwargs))
    if clash:
        raise OrderTypeError(f"FxHedgeOrder sets {', '.join(clash)} itself")
    return MarketOrder(action, 0, parentId=parent.orderId, hedgeType="F", **kwargs)
