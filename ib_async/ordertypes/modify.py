"""An order read back from TWS, made ready to send again as a modification.

TWS fills in fields of a live order that it then refuses on a modification,
and reports an order worked by an algo with orderType "IBALGO", which it
refuses too. :func:`modifiedOrder` does what an application modifying live
orders through IBKR does, rule for rule; it is the evidence of what IBKR
accepts, so do not change a rule here without a source that IBKR accepts
the change.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from ..order import Order
from .spec import ORDER_DEFAULTS, OrderTypeError, baseOrderType

# Fields TWS fills in on a live order and refuses back on a modification;
# reset unless a change sets them. A read-back order shows them filled in,
# such as adjustedOrderType='None', clearingIntent='IB' and a displaySize of
# 2112345647 on a plain trailing stop limit. They are reset to Order's
# defaults: what every newly built order sends, and IBKR accepts.
SERVER_FILLED = (
    "adjustedOrderType",
    "clearingIntent",
    "deltaNeutralOrderType",
    "displaySize",
    "dontUseAutoPriceForHedge",
    "trailStopPrice",
    "volatilityType",
)


def modifiedOrder(
    order: Order, *, preserveParentId: bool = False, **changes: Any
) -> Order:
    """A copy of ``order`` (as TWS reports it, from ``trade.order`` or
    ``ib.openOrders()``) with ``changes``, ready for ``ib.placeOrder`` to
    modify the live order:

    - an "IBALGO" orderType is sent as "LMT";
    - volatility is cleared unless the order type contains "VOL";
    - parentId is cleared, unless ``preserveParentId`` (keep it for a
      bracket's child, so a reprice cannot detach an exit from its entry);
    - transmit is set;
    - the fields TWS fills in (``SERVER_FILLED``) are reset unless
      ``changes`` sets them.

    Refuses a totalQuantity below the quantity already filled, which IBKR
    rejects.

    Example::

        trade = ib.openTrades()[0]
        ib.placeOrder(trade.contract, modifiedOrder(trade.order, lmtPrice=50.10))
    """
    updated = dataclasses.replace(
        order, **{"orderType": baseOrderType(order), **changes}
    )
    if "VOL" not in updated.orderType:
        updated.volatility = None
    if updated.parentId and not preserveParentId:
        updated.parentId = ORDER_DEFAULTS["parentId"]
    updated.transmit = True
    for name in SERVER_FILLED:
        if name not in changes:
            setattr(updated, name, ORDER_DEFAULTS[name])
    filled = updated.filledQuantity
    if filled and updated.totalQuantity is not None and updated.totalQuantity < filled:
        raise OrderTypeError(
            f"totalQuantity {updated.totalQuantity} is below the "
            f"{filled} already filled"
        )
    return updated
