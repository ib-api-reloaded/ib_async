"""Orders attached to another: adjustable stops and FX hedges.

An adjustment changes a stop, stop limit or trailing stop order once, into
another type, when the price penetrates its trigger price: pass it as
``adjust=`` to the order type (usually an order attached to a parent with
``parentId``). Brackets are ``IB.bracketOrder``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..order import Order
from .generated import MarketOrder
from .spec import Adjustment, FieldValue, OrderTypeError

__all__ = ["AdjustToStop", "AdjustToStopLimit", "AdjustToTrail", "FxHedgeOrder"]

# adjustableTrailingUnit: the trailing amount is a price, or a percentage.
TRAIL_BY_AMOUNT = 0
TRAIL_BY_PERCENT = 100

Price = Decimal | float | str


def _adjustment(
    title: str,
    adjustedOrderType: str,
    prices: dict[str, Price | None],
    *fields: FieldValue,
) -> Adjustment:
    """An adjustment to ``adjustedOrderType``: ``prices`` (by parameter name,
    in the order of the Order fields they set) must all be given."""
    missing = [name for name, price in prices.items() if price is None]
    if missing:
        raise OrderTypeError(f"{title} needs {', '.join(missing)}")
    return Adjustment(
        title, (FieldValue("adjustedOrderType", adjustedOrderType), *fields)
    )


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
        {"triggerPrice": triggerPrice, "stopPrice": stopPrice},
        FieldValue("triggerPrice", triggerPrice),
        FieldValue("adjustedStopPrice", stopPrice),
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
        {
            "triggerPrice": triggerPrice,
            "stopPrice": stopPrice,
            "limitPrice": limitPrice,
        },
        FieldValue("triggerPrice", triggerPrice),
        FieldValue("adjustedStopPrice", stopPrice),
        FieldValue("adjustedStopLimitPrice", limitPrice),
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
    byAmount = trailingAmount is not None
    return _adjustment(
        "Adjust to trailing stop",
        "TRAIL",
        {"triggerPrice": triggerPrice, "stopPrice": stopPrice},
        FieldValue("triggerPrice", triggerPrice),
        FieldValue("adjustedStopPrice", stopPrice),
        FieldValue(
            "adjustedTrailingAmount", trailingAmount if byAmount else trailingPercent
        ),
        FieldValue(
            "adjustableTrailingUnit", TRAIL_BY_AMOUNT if byAmount else TRAIL_BY_PERCENT
        ),
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
