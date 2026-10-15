"""The order type and algo constructors, generated from ``catalog.py``
by ``scripts/generate_ordertypes.py``. Do not edit: change the catalog and
regenerate.

Each order type returns a plain ``Order``, so ``dataclasses.replace``,
copying and pickling work as for any order, and ``specOf`` tells its type.
Each algo returns an ``Algo``, for the ``algo=`` of the order types it
works."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal

from ..order import Order
from .catalog import ALGO_SPECS, COMBO_ROUTING, SPECS
from .spec import Adjustment, Algo, Routing, build, buildAlgo, buildRouting

__all__ = [
    "AccumulateDistribute",
    "Adaptive",
    "ArrivalPrice",
    "AtAuctionOrder",
    "AuctionLimitOrder",
    "BalanceImpactRisk",
    "BlockOrder",
    "BoxTopOrder",
    "ClosePrice",
    "ComboLegPricesOrder",
    "ComboRouting",
    "DarkIce",
    "DiscretionaryOrder",
    "IbkrAtsLimitOrder",
    "LimitIfTouchedOrder",
    "LimitOnCloseOrder",
    "LimitOnOpenOrder",
    "LimitOrder",
    "MarketIfTouchedOrder",
    "MarketOnCloseOrder",
    "MarketOnOpenOrder",
    "MarketOrder",
    "MarketToLimitOrder",
    "MarketWithProtectionOrder",
    "MidpriceOrder",
    "MinimiseImpact",
    "PassiveRelativeOrder",
    "PegBestOrder",
    "PegBestUpToMidOrder",
    "PegMidOrder",
    "PeggedToBenchmarkOrder",
    "PeggedToMarketOrder",
    "PeggedToMidpointOrder",
    "PeggedToStockOrder",
    "PercentOfVolume",
    "PriceVariantPercentOfVolume",
    "RelativeLimitComboOrder",
    "RelativeMarketComboOrder",
    "RelativeOrder",
    "SizeVariantPercentOfVolume",
    "SnapToMarketOrder",
    "SnapToMidpointOrder",
    "SnapToPrimaryOrder",
    "StopLimitOrder",
    "StopOrder",
    "StopWithProtectionOrder",
    "SweepToFillOrder",
    "TimeVariantPercentOfVolume",
    "TrailingStopLimitOrder",
    "TrailingStopOrder",
    "Twap",
    "VolatilityOrder",
    "Vwap",
]


def MarketOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Market (``MKT``): Buys or sells at the market bid or offer price.

    Likely to fill, and quickly, but with no price protection: it may fill far
    from the displayed bid or ask.

    Products: BOND, CFD, EFP, CASH, FUND, FUT, FOP, OPT, STK, WAR. Stability:
    stable.

    Example::

        MarketOrder("BUY", 100)
    """
    return Order(
        **build(
            SPECS["MarketOrder"],
            action,
            totalQuantity,
            {},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def LimitOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Limit (``LMT``): Buys at the limit price or lower, or sells at it or higher.

    Never fills at a worse price than the limit; it may not fill.

    Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR. Stability: stable.

    Args:
        lmtPrice: The limit price.

    Example::

        LimitOrder("BUY", 100, 50.25)
    """
    return Order(
        **build(
            SPECS["LimitOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def StopOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    stopPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Stop (``STP``): Becomes a market order once the stop price is reached.

    A sell stop below the market limits a loss or protects a profit on a long
    position; a buy stop above it does so on a short sale. Once triggered it may
    fill well away from the stop price.

    Products: CFD, BAG, CASH, FUT, FOP, OPT, STK, WAR. Stability: stable.

    Args:
        stopPrice: The price that triggers the order.

    Example::

        StopOrder("SELL", 100, 45.00)
    """
    return Order(
        **build(
            SPECS["StopOrder"],
            action,
            totalQuantity,
            {"stopPrice": stopPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def StopLimitOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    stopPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Stop Limit (``STP LMT``): Becomes a limit order once the stop price is
    reached.

    Like a stop order, but once triggered it fills only at the limit price or
    better.

    Products: CFD, CASH, FUT, FOP, OPT, STK, WAR. Stability: stable.

    Args:
        lmtPrice: The limit price.
        stopPrice: The price that triggers the order.

    Example::

        StopLimitOrder("SELL", 100, 44.50, 45.00)
    """
    return Order(
        **build(
            SPECS["StopLimitOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "stopPrice": stopPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def MarketOnCloseOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Market on Close (``MOC``): A market order executed as close to the closing
    price as possible.

    Products: CFD, FUT, STK, WAR. Stability: stable.

    Example::

        MarketOnCloseOrder("SELL", 100)
    """
    return Order(
        **build(
            SPECS["MarketOnCloseOrder"],
            action,
            totalQuantity,
            {},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def LimitOnCloseOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Limit on Close (``LOC``): A limit order executed at the close if the closing
    price is at or better than the limit.

    Set imbalanceOnly=True to offer it only against the closing auction's
    imbalance.

    Products: CFD, FUT, STK, WAR. Stability: stable.

    Args:
        lmtPrice: The limit price.

    Example::

        LimitOnCloseOrder("SELL", 100, 50.00)
    """
    return Order(
        **build(
            SPECS["LimitOnCloseOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def MarketOnOpenOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Market on Open (``MKT``): A market order executed at the opening price.

    A market order with time in force OPG.

    Sets tif='OPG'. Products: CFD, FUT, STK, OPT, WAR. Stability: stable.

    Example::

        MarketOnOpenOrder("BUY", 100)
    """
    return Order(
        **build(
            SPECS["MarketOnOpenOrder"],
            action,
            totalQuantity,
            {},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def LimitOnOpenOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Limit on Open (``LMT``): A limit order executed at the open if the opening
    price is at or better than the limit.

    A limit order with time in force OPG.

    Sets tif='OPG'. Products: CFD, STK, OPT, WAR. Stability: stable.

    Args:
        lmtPrice: The limit price.

    Example::

        LimitOnOpenOrder("BUY", 100, 50.00)
    """
    return Order(
        **build(
            SPECS["LimitOnOpenOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def AtAuctionOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    At Auction (``MTL``): Entered in the pre-market auction to execute at the
    calculated opening price; if not filled on the open, it is resubmitted as a
    limit order at that price or the best bid or ask after the open.

    Sets tif='AUC'. Products: FUT, STK. Stability: stable.

    Args:
        lmtPrice: The limit price.

    Example::

        AtAuctionOrder("BUY", 100, 50.00)
    """
    return Order(
        **build(
            SPECS["AtAuctionOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def MarketIfTouchedOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    touchPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Market if Touched (``MIT``): Becomes a market order once the touch price is
    reached.

    The mirror of a stop: a buy below the market or a sell above it, to act on a
    price level being reached.

    Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR. Stability: stable.

    Args:
        touchPrice: The price that, once touched, triggers the order.

    Example::

        MarketIfTouchedOrder("BUY", 100, 48.00)
    """
    return Order(
        **build(
            SPECS["MarketIfTouchedOrder"],
            action,
            totalQuantity,
            {"touchPrice": touchPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def LimitIfTouchedOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    touchPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Limit if Touched (``LIT``): Becomes a limit order once the touch price is
    reached.

    Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR. Stability: stable.

    Args:
        lmtPrice: The limit price.
        touchPrice: The price that, once touched, triggers the order.

    Example::

        LimitIfTouchedOrder("BUY", 100, 48.10, 48.00)
    """
    return Order(
        **build(
            SPECS["LimitIfTouchedOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "touchPrice": touchPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def TrailingStopOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    trailingAmount: Decimal | float | str | None = None,
    trailingPercent: Decimal | float | str | None = None,
    trailStopPrice: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Trailing Stop (``TRAIL``): A stop that follows the market: its stop price
    moves with the price by a fixed amount or percent, and never back.

    Give trailingAmount or trailingPercent.

    Products: CFD, CASH, FOP, FUT, OPT, STK, WAR. Stability: stable.

    Args:
        trailingAmount: How far the stop trails, in price. Optional.
        trailingPercent: How far the stop trails, in percent. Optional.
        trailStopPrice: The trailing stop price. Optional.

    Example::

        TrailingStopOrder("SELL", 100, trailingPercent=2.0)
    """
    return Order(
        **build(
            SPECS["TrailingStopOrder"],
            action,
            totalQuantity,
            {
                "trailingAmount": trailingAmount,
                "trailingPercent": trailingPercent,
                "trailStopPrice": trailStopPrice,
            },
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def TrailingStopLimitOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    lmtPriceOffset: Decimal | float | str | None = None,
    lmtPrice: Decimal | float | str | None = None,
    trailingAmount: Decimal | float | str | None = None,
    trailingPercent: Decimal | float | str | None = None,
    trailStopPrice: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Trailing Stop Limit (``TRAIL LIMIT``): A trailing stop that, once triggered,
    becomes a limit order at the limit price, or at lmtPriceOffset from the stop
    price as it trails.

    Give trailingAmount or trailingPercent, and lmtPrice or lmtPriceOffset.

    Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR. Stability: stable.

    Args:
        lmtPriceOffset: The limit price's distance from the stop price. Optional.
        lmtPrice: The limit price. Optional.
        trailingAmount: How far the stop trails, in price. Optional.
        trailingPercent: How far the stop trails, in percent. Optional.
        trailStopPrice: The trailing stop price. Optional.

    Example::

        TrailingStopLimitOrder("SELL", 100, lmtPriceOffset=0.10, trailingAmount=1.00)
    """
    return Order(
        **build(
            SPECS["TrailingStopLimitOrder"],
            action,
            totalQuantity,
            {
                "lmtPriceOffset": lmtPriceOffset,
                "lmtPrice": lmtPrice,
                "trailingAmount": trailingAmount,
                "trailingPercent": trailingPercent,
                "trailStopPrice": trailStopPrice,
            },
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def MarketToLimitOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Market to Limit (``MTL``): A market order whose unfilled part becomes a
    limit order at the price of its first fill.

    Products: CFD, FUT, FOP, OPT, STK, WAR. Stability: stable.

    Example::

        MarketToLimitOrder("BUY", 100)
    """
    return Order(
        **build(
            SPECS["MarketToLimitOrder"],
            action,
            totalQuantity,
            {},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def MarketWithProtectionOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Market with Protection (``MKT PRT``): A market order that, if it does not
    execute in full at once, is canceled and resubmitted as a limit order at a
    price the exchange sets close to the market.

    IBKR lists it for futures and futures options; an application trading live
    also sends it for SPXW index options.

    Products: FUT, FOP. Stability: stable.

    Example::

        MarketWithProtectionOrder("BUY", 1)
    """
    return Order(
        **build(
            SPECS["MarketWithProtectionOrder"],
            action,
            totalQuantity,
            {},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def StopWithProtectionOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    stopPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Stop with Protection (``STP PRT``): A stop that becomes a market order with
    protection once triggered.

    Products: FUT. Stability: stable.

    Args:
        stopPrice: The price that triggers the order.

    Example::

        StopWithProtectionOrder("SELL", 1, 4500.00)
    """
    return Order(
        **build(
            SPECS["StopWithProtectionOrder"],
            action,
            totalQuantity,
            {"stopPrice": stopPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def RelativeOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    offset: Decimal | float | str,
    priceCap: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Relative (Pegged to Primary) (``REL``): Pegged to the national best bid
    (buy) or offer (sell), more aggressive by offset. It follows the quote
    toward the market (a buy rises with the bid) but not away from it.

    IBKR describes priceCap as optional, but rejects the order without it in
    live trading. Not available on paper trading accounts.

    Products: CFD, STK, OPT, FUT. Stability: stable.

    Args:
        offset: How much more aggressive than the NBBO.
        priceCap: The worst price accepted, like a limit price.

    Example::

        RelativeOrder("BUY", 100, 0.01, 50.00)
    """
    return Order(
        **build(
            SPECS["RelativeOrder"],
            action,
            totalQuantity,
            {"offset": offset, "priceCap": priceCap},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PassiveRelativeOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    offset: Decimal | float | str,
    *,
    priceCap: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Passive Relative (``PASSV REL``): Pegged to the national best bid (buy) or
    offer (sell), less aggressive by offset: a buy subtracts the offset from the
    bid.

    Products: STK, WAR. Stability: stable.

    Args:
        offset: How much less aggressive than the NBBO.
        priceCap: The worst price accepted, like a limit price. Optional.

    Example::

        PassiveRelativeOrder("BUY", 100, 0.01)
    """
    return Order(
        **build(
            SPECS["PassiveRelativeOrder"],
            action,
            totalQuantity,
            {"offset": offset, "priceCap": priceCap},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PeggedToMarketOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    offset: Decimal | float | str,
    *,
    priceCap: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Pegged to Market (``PEG MKT``): Pegged to the national best offer (buy) or
    bid (sell): a buy is priced at the offer less offset, a sell at the bid plus
    offset.

    Products: STK. Stability: stable.

    Args:
        offset: The amount away from the NBBO.
        priceCap: The worst price accepted, like a limit price. Optional.

    Example::

        PeggedToMarketOrder("BUY", 100, 0.01)
    """
    return Order(
        **build(
            SPECS["PeggedToMarketOrder"],
            action,
            totalQuantity,
            {"offset": offset, "priceCap": priceCap},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PeggedToMidpointOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    offset: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Pegged to Midpoint (``PEG MID``): Pegged to the NBBO midpoint, adjusted by
    offset, never beyond the limit price.

    Products: STK. Stability: stable.

    Args:
        lmtPrice: The limit price.
        offset: The amount away from the reference price. Optional.

    Example::

        PeggedToMidpointOrder("BUY", 100, 50.00, offset=0.01)
    """
    return Order(
        **build(
            SPECS["PeggedToMidpointOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "offset": offset},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def MidpriceOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    priceCap: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Midprice (``MIDPRICE``): Fills at the NBBO midpoint or better.

    IBKR describes priceCap as optional, but rejects the order without it in
    live trading, and refuses it outside regular trading hours. SMART-routed US
    stocks only.

    Products: STK. Requires TWS 975+. Stability: stable.

    Args:
        priceCap: The worst price accepted, like a limit price.

    Example::

        MidpriceOrder("BUY", 100, 50.00)
    """
    return Order(
        **build(
            SPECS["MidpriceOrder"],
            action,
            totalQuantity,
            {"priceCap": priceCap},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def SnapToMidpointOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    offset: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Snap to Midpoint (``SNAP MID``): Priced once, when placed, at the NBBO
    midpoint: a buy less offset, a sell plus offset. It does not move
    afterwards.

    Stability: stable.

    Args:
        lmtPrice: The limit price.
        offset: The amount away from the reference price. Optional.

    Example::

        SnapToMidpointOrder("BUY", 100, 50.00, offset=0.01)
    """
    return Order(
        **build(
            SPECS["SnapToMidpointOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "offset": offset},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def SnapToPrimaryOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    offset: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Snap to Primary (``SNAP PRIM``): Priced once, when placed, at the national
    best bid plus offset (buy) or offer less offset (sell). It does not move
    afterwards.

    Stability: stable.

    Args:
        lmtPrice: The limit price.
        offset: The amount away from the reference price. Optional.

    Example::

        SnapToPrimaryOrder("BUY", 100, 50.00, offset=0.01)
    """
    return Order(
        **build(
            SPECS["SnapToPrimaryOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "offset": offset},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def SnapToMarketOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    offset: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Snap to Market (``SNAP MKT``): Priced once, when placed, at the national
    best offer less offset (buy) or bid plus offset (sell). It does not move
    afterwards.

    Stability: stable.

    Args:
        lmtPrice: The limit price.
        offset: The amount away from the reference price. Optional.

    Example::

        SnapToMarketOrder("BUY", 100, 50.00, offset=0.01)
    """
    return Order(
        **build(
            SPECS["SnapToMarketOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "offset": offset},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def DiscretionaryOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    discretionaryAmt: float,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Discretionary (``LMT``): A limit order with a hidden discretionary amount:
    the market sees only the limit price, but it may execute up to that far
    beyond.

    Products: STK. Stability: stable.

    Args:
        lmtPrice: The limit price.
        discretionaryAmt: How far beyond the limit price it may execute.

    Example::

        DiscretionaryOrder("BUY", 100, 50.00, 0.05)
    """
    return Order(
        **build(
            SPECS["DiscretionaryOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "discretionaryAmt": discretionaryAmt},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def SweepToFillOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Sweep to Fill (``LMT``): A limit order that takes the best price and, at
    once, the next best prices, for speed of execution over price.

    SMART-routed only.

    Sets sweepToFill=True. Products: CFD, STK, WAR. Stability: stable.

    Args:
        lmtPrice: The limit price.

    Example::

        SweepToFillOrder("BUY", 100, 50.00)
    """
    return Order(
        **build(
            SPECS["SweepToFillOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def BlockOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Block (``LMT``): A limit order for 50 or more option contracts, executed as
    a block on ISE.

    Sets blockOrder=True. Products: OPT. Exchanges: ISE. Stability: venue.

    Args:
        lmtPrice: The limit price.

    Example::

        BlockOrder("BUY", 50, 2.50)
    """
    return Order(
        **build(
            SPECS["BlockOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def BoxTopOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Box Top (``BOX TOP``): A market order at the best price on BOX; any unfilled
    part becomes a limit order at the price of its fill.

    Products: OPT. Exchanges: BOX. Stability: venue.

    Example::

        BoxTopOrder("BUY", 10)
    """
    return Order(
        **build(
            SPECS["BoxTopOrder"],
            action,
            totalQuantity,
            {},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def AuctionLimitOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    auctionStrategy: int,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Auction Limit (``LMT``): A limit order in a BOX price improvement auction.

    Products: OPT. Exchanges: BOX. Stability: venue.

    Args:
        lmtPrice: The limit price.
        auctionStrategy: 1 match, 2 improvement, 3 transparent.

    Example::

        AuctionLimitOrder("BUY", 10, 2.50, 2)
    """
    return Order(
        **build(
            SPECS["AuctionLimitOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice, "auctionStrategy": auctionStrategy},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PeggedToStockOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    delta: Decimal | float | str,
    startingPrice: Decimal | float | str,
    *,
    stockRefPrice: Decimal | float | str | None = None,
    stockRangeLower: Decimal | float | str | None = None,
    stockRangeUpper: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Pegged to Stock (``PEG STK``): An option order whose price moves by delta
    times the underlying's change from the stock reference price.

    delta is entered as an absolute value, taken as positive for calls and
    negative for puts. Without stockRefPrice IBKR uses the underlying's NBBO
    midpoint at placement; stockRangeLower and stockRangeUpper cancel the order
    when the underlying leaves the range. On BOX this is the Auction Pegged to
    Stock order.

    Products: OPT. Stability: venue.

    Args:
        delta: The option's price change per underlying move.
        startingPrice: The option price to start from.
        stockRefPrice: The underlying price the change is measured from. Optional.
        stockRangeLower: Cancel below this underlying price. Optional.
        stockRangeUpper: Cancel above this underlying price. Optional.

    Example::

        PeggedToStockOrder("BUY", 1, 0.5, 2.50, stockRefPrice=100.00)
    """
    return Order(
        **build(
            SPECS["PeggedToStockOrder"],
            action,
            totalQuantity,
            {
                "delta": delta,
                "startingPrice": startingPrice,
                "stockRefPrice": stockRefPrice,
                "stockRangeLower": stockRangeLower,
                "stockRangeUpper": stockRangeUpper,
            },
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PegBestOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    minTradeQty: int,
    minCompeteSize: int,
    competeAgainstBestOffset: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Pegged to Best (IBKR ATS) (``PEG BEST``): Pegged to the best price on IBKR's
    ATS.

    Sets notHeld=True. Products: STK. Exchanges: IBKRATS. Stability: venue.

    Args:
        lmtPrice: The limit price.
        minTradeQty: The smallest fill accepted.
        minCompeteSize: The minimum size to compete.
        competeAgainstBestOffset: The offset off the midpoint.

    Example::

        PegBestOrder("BUY", 100, 50.00, 100, 100, 0.01)
    """
    return Order(
        **build(
            SPECS["PegBestOrder"],
            action,
            totalQuantity,
            {
                "lmtPrice": lmtPrice,
                "minTradeQty": minTradeQty,
                "minCompeteSize": minCompeteSize,
                "competeAgainstBestOffset": competeAgainstBestOffset,
            },
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PegBestUpToMidOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    minTradeQty: int,
    minCompeteSize: int,
    midOffsetAtWhole: Decimal | float | str,
    midOffsetAtHalf: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Pegged to Best up to Midpoint (IBKR ATS) (``PEG BEST``): Pegged to the best
    price on IBKR's ATS, competing up to the midpoint, offset by
    midOffsetAtWhole or midOffsetAtHalf depending on the spread.

    Sets notHeld=True, competeAgainstBestOffset=Decimal('Infinity'). Products:
    STK. Exchanges: IBKRATS. Stability: venue.

    Args:
        lmtPrice: The limit price.
        minTradeQty: The smallest fill accepted.
        minCompeteSize: The minimum size to compete.
        midOffsetAtWhole: The offset when the spread is an even number of cents wide.
        midOffsetAtHalf: The offset when the spread is an odd number of cents wide.

    Example::

        PegBestUpToMidOrder("BUY", 100, 50.00, 100, 100, 0.01, 0.005)
    """
    return Order(
        **build(
            SPECS["PegBestUpToMidOrder"],
            action,
            totalQuantity,
            {
                "lmtPrice": lmtPrice,
                "minTradeQty": minTradeQty,
                "minCompeteSize": minCompeteSize,
                "midOffsetAtWhole": midOffsetAtWhole,
                "midOffsetAtHalf": midOffsetAtHalf,
            },
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def IbkrAtsLimitOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Limit (IBKR ATS) (``LMT``): A not-held limit order on IBKR's ATS.

    For non-marketable US stock orders; route the contract to IBKRATS.

    Sets notHeld=True. Products: STK. Exchanges: IBKRATS. Stability: venue.

    Args:
        lmtPrice: The limit price.

    Example::

        IbkrAtsLimitOrder("BUY", 100, 50.00)
    """
    return Order(
        **build(
            SPECS["IbkrAtsLimitOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PegMidOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    minTradeQty: int | None = None,
    midOffsetAtWhole: Decimal | float | str | None = None,
    midOffsetAtHalf: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Pegged to Midpoint (IBKR ATS) (``PEG MID``): Pegged to the midpoint on
    IBKR's own venue, offset by midOffsetAtWhole or midOffsetAtHalf depending on
    the spread.

    Route stocks to IBKRATS and options to IBUSOPT. Live trading sends it
    without the offsets or a minimum fill.

    Sets notHeld=True. Products: STK, OPT. Exchanges: IBKRATS, IBUSOPT.
    Stability: venue.

    Args:
        lmtPrice: The limit price.
        minTradeQty: The smallest fill accepted. Optional.
        midOffsetAtWhole: The offset when the spread is an even number of cents wide. Optional.
        midOffsetAtHalf: The offset when the spread is an odd number of cents wide. Optional.

    Example::

        PegMidOrder("BUY", 100, 50.00)
    """
    return Order(
        **build(
            SPECS["PegMidOrder"],
            action,
            totalQuantity,
            {
                "lmtPrice": lmtPrice,
                "minTradeQty": minTradeQty,
                "midOffsetAtWhole": midOffsetAtWhole,
                "midOffsetAtHalf": midOffsetAtHalf,
            },
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def ComboLegPricesOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    legPrices: Sequence[Decimal | float | str],
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Combo with Leg Prices (``LMT``): A limit order for a combo (BAG) contract
    with a limit price for each leg instead of one for the combo.

    One price per leg, in the order of the contract's legs. For one price for
    the whole combo, use LimitOrder.

    Products: BAG. Stability: stable.

    Args:
        legPrices: The limit price of each leg, in leg order.

    Example::

        ComboLegPricesOrder("BUY", 1, [2.50, 1.20])
    """
    return Order(
        **build(
            SPECS["ComboLegPricesOrder"],
            action,
            totalQuantity,
            {"legPrices": legPrices},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def RelativeLimitComboOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    lmtPrice: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Relative + Limit (combo) (``REL + LMT``): IBKR's relative plus limit combo
    order, with the combo's limit price. IBKR does not document how it works the
    legs.

    Products: BAG. Stability: advanced.

    Args:
        lmtPrice: The limit price.

    Example::

        RelativeLimitComboOrder("BUY", 1, 2.50)
    """
    return Order(
        **build(
            SPECS["RelativeLimitComboOrder"],
            action,
            totalQuantity,
            {"lmtPrice": lmtPrice},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def RelativeMarketComboOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Relative + Market (combo) (``REL + MKT``): A combo order whose legs start as
    relative orders, pegged to the bid (buy) or ask (sell); once a leg fills,
    the remaining legs are sent at market.

    Products: BAG. Stability: advanced.

    Example::

        RelativeMarketComboOrder("BUY", 1)
    """
    return Order(
        **build(
            SPECS["RelativeMarketComboOrder"],
            action,
            totalQuantity,
            {},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def VolatilityOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    volatility: Decimal | float | str,
    volatilityType: int,
    *,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Volatility (``VOL``): An option order priced from an implied volatility.

    volatilityType: 1 daily, 2 annual. With continuousUpdate, TWS updates the
    price as the underlying moves. Delta-neutral hedging is set with the
    deltaNeutral* fields.

    Products: FOP, OPT. Stability: advanced.

    Args:
        volatility: The implied volatility, in percent.
        volatilityType: 1 daily, 2 annual.

    Example::

        VolatilityOrder("BUY", 1, 25.0, 2)
    """
    return Order(
        **build(
            SPECS["VolatilityOrder"],
            action,
            totalQuantity,
            {"volatility": volatility, "volatilityType": volatilityType},
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def PeggedToBenchmarkOrder(
    action: str,
    totalQuantity: Decimal | float | str,
    startingPrice: Decimal | float | str,
    referenceContractId: int,
    referenceExchangeId: str,
    peggedChangeAmount: float,
    referenceChangeAmount: float,
    *,
    isPeggedChangeAmountDecrease: bool | None = None,
    stockRefPrice: Decimal | float | str | None = None,
    stockRangeLower: Decimal | float | str | None = None,
    stockRangeUpper: Decimal | float | str | None = None,
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
    **kwargs: Any,
) -> Order:
    """
    Pegged to Benchmark (``PEG BENCH``): Pegged to another contract: its price
    moves by peggedChangeAmount each time the reference contract moves by
    referenceChangeAmount.

    Both contracts must use the same currency.

    Products: STK, OPT. Stability: advanced.

    Args:
        startingPrice: The price to start from.
        referenceContractId: The conId of the contract it is pegged to.
        referenceExchangeId: The reference contract's exchange.
        peggedChangeAmount: How much the order price changes per step.
        referenceChangeAmount: How much the reference contract moves per step.
        isPeggedChangeAmountDecrease: Whether the pegged price decreases rather than increases. Optional.
        stockRefPrice: The reference price the change is measured from. Optional.
        stockRangeLower: Cancel below this reference price. Optional.
        stockRangeUpper: Cancel above this reference price. Optional.

    Example::

        PeggedToBenchmarkOrder("BUY", 100, 50.00, 12345, "ISLAND", 0.02, 0.01)
    """
    return Order(
        **build(
            SPECS["PeggedToBenchmarkOrder"],
            action,
            totalQuantity,
            {
                "startingPrice": startingPrice,
                "referenceContractId": referenceContractId,
                "referenceExchangeId": referenceExchangeId,
                "peggedChangeAmount": peggedChangeAmount,
                "referenceChangeAmount": referenceChangeAmount,
                "isPeggedChangeAmountDecrease": isPeggedChangeAmountDecrease,
                "stockRefPrice": stockRefPrice,
                "stockRangeLower": stockRangeLower,
                "stockRangeUpper": stockRangeUpper,
            },
            kwargs,
            algo,
            routing,
            adjust,
        )
    )


def Adaptive(
    *,
    priority: Literal["Urgent", "Normal", "Patient"] | None = None,
) -> Algo:
    """
    Adaptive: Works a market or limit order between the bid and ask, trading
    speed against price by priority.

    Day orders only. Live trading found it refused outside regular trading
    hours, and for CME futures options and SPXW index options.

    Works LMT, MKT orders. Stability: stable.

    Args:
        priority: Urgent fills fastest, Patient seeks the best price. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=Adaptive(priority="Urgent"))
    """
    return buildAlgo(ALGO_SPECS["Adaptive"], {"priority": priority})


def ArrivalPrice(
    *,
    maxPctVol: float | None = None,
    riskAversion: Literal["Get Done", "Aggressive", "Neutral", "Passive"] | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    forceCompletion: bool | None = None,
    allowPastEndTime: bool | None = None,
) -> Algo:
    """
    Arrival Price (``ArrivalPx``): Aims for the bid/ask midpoint at the time the
    order is submitted, trading off market impact against the risk of the price
    moving.

    Works LMT orders. Stability: advanced.

    Args:
        maxPctVol: The largest share of the market's volume, 0.1 (10%) to 0.5 (50%). Optional.
        riskAversion: How urgently to complete. Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        forceCompletion: Attempt completion by the end of the day. Optional.
        allowPastEndTime: Keep working after endTime if not done. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=ArrivalPrice(maxPctVol=0.1, riskAversion="Neutral"))
    """
    return buildAlgo(
        ALGO_SPECS["ArrivalPrice"],
        {
            "maxPctVol": maxPctVol,
            "riskAversion": riskAversion,
            "startTime": startTime,
            "endTime": endTime,
            "forceCompletion": forceCompletion,
            "allowPastEndTime": allowPastEndTime,
        },
    )


def DarkIce(
    *,
    displaySize: int | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    allowPastEndTime: bool | None = None,
) -> Algo:
    """
    Dark Ice (``DarkIce``): Shows only displaySize of a limit order, randomizing
    the size shown and keeping the rest hidden.

    Day orders only.

    Works LMT orders. Stability: advanced.

    Args:
        displaySize: The size to show. Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        allowPastEndTime: Keep working after endTime if not done. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=DarkIce(displaySize=100))
    """
    return buildAlgo(
        ALGO_SPECS["DarkIce"],
        {
            "displaySize": displaySize,
            "startTime": startTime,
            "endTime": endTime,
            "allowPastEndTime": allowPastEndTime,
        },
    )


def PercentOfVolume(
    *,
    pctVol: float | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    noTakeLiq: bool | None = None,
) -> Algo:
    """
    Percentage of Volume (``PctVol``): Trades a fixed share of the market's
    volume.

    Works LMT orders. Stability: advanced.

    Args:
        pctVol: The share of the market's volume, 0.1 (10%) to 0.5 (50%). Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        noTakeLiq: Attempt never to take liquidity. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=PercentOfVolume(pctVol=0.1))
    """
    return buildAlgo(
        ALGO_SPECS["PercentOfVolume"],
        {
            "pctVol": pctVol,
            "startTime": startTime,
            "endTime": endTime,
            "noTakeLiq": noTakeLiq,
        },
    )


def PriceVariantPercentOfVolume(
    *,
    pctVol: float | None = None,
    deltaPctVol: float | None = None,
    minPctVol4Px: float | None = None,
    maxPctVol4Px: float | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    noTakeLiq: bool | None = None,
) -> Algo:
    """
    Price Variant Percentage of Volume (``PctVolPx``): Trades a share of volume
    that changes with the price: by deltaPctVol per move, between minPctVol4Px
    and maxPctVol4Px.

    Works LMT orders. Stability: advanced.

    Args:
        pctVol: The share of the market's volume, 0.1 (10%) to 0.5 (50%). Optional.
        deltaPctVol: The change in share per price move, 0.1 (10%) to 0.5 (50%). Optional.
        minPctVol4Px: The lowest share, 0.1 (10%) to 0.5 (50%). Optional.
        maxPctVol4Px: The highest share, 0.1 (10%) to 0.5 (50%). Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        noTakeLiq: Attempt never to take liquidity. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=PriceVariantPercentOfVolume(pctVol=0.1, deltaPctVol=0.1))
    """
    return buildAlgo(
        ALGO_SPECS["PriceVariantPercentOfVolume"],
        {
            "pctVol": pctVol,
            "deltaPctVol": deltaPctVol,
            "minPctVol4Px": minPctVol4Px,
            "maxPctVol4Px": maxPctVol4Px,
            "startTime": startTime,
            "endTime": endTime,
            "noTakeLiq": noTakeLiq,
        },
    )


def SizeVariantPercentOfVolume(
    *,
    startPctVol: float | None = None,
    endPctVol: float | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    noTakeLiq: bool | None = None,
) -> Algo:
    """
    Size Variant Percentage of Volume (``PctVolSz``): Trades a share of volume
    that moves from startPctVol to endPctVol as the order fills.

    Works LMT orders. Stability: advanced.

    Args:
        startPctVol: The share of volume at the start, 0.1 (10%) to 0.5 (50%). Optional.
        endPctVol: The share of volume at the end, 0.1 (10%) to 0.5 (50%). Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        noTakeLiq: Attempt never to take liquidity. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=SizeVariantPercentOfVolume(startPctVol=0.2, endPctVol=0.4))
    """
    return buildAlgo(
        ALGO_SPECS["SizeVariantPercentOfVolume"],
        {
            "startPctVol": startPctVol,
            "endPctVol": endPctVol,
            "startTime": startTime,
            "endTime": endTime,
            "noTakeLiq": noTakeLiq,
        },
    )


def TimeVariantPercentOfVolume(
    *,
    startPctVol: float | None = None,
    endPctVol: float | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    noTakeLiq: bool | None = None,
) -> Algo:
    """
    Time Variant Percentage of Volume (``PctVolTm``): Trades a share of volume
    that moves from startPctVol to endPctVol between startTime and endTime.

    Works LMT orders. Stability: advanced.

    Args:
        startPctVol: The share of volume at the start, 0.1 (10%) to 0.5 (50%). Optional.
        endPctVol: The share of volume at the end, 0.1 (10%) to 0.5 (50%). Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        noTakeLiq: Attempt never to take liquidity. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=TimeVariantPercentOfVolume(startPctVol=0.2, endPctVol=0.4))
    """
    return buildAlgo(
        ALGO_SPECS["TimeVariantPercentOfVolume"],
        {
            "startPctVol": startPctVol,
            "endPctVol": endPctVol,
            "startTime": startTime,
            "endTime": endTime,
            "noTakeLiq": noTakeLiq,
        },
    )


def Twap(
    *,
    strategyType: Literal[
        "Marketable", "Matching", "Midpoint", "Matching Same Side", "Matching Last"
    ]
    | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    allowPastEndTime: bool | None = None,
    catchUp: bool | None = None,
) -> Algo:
    """
    TWAP (``Twap``): Aims for the time-weighted average price from when the
    order is submitted to when it completes.

    Works LMT orders. Products: STK. Stability: advanced.

    Args:
        strategyType: Which trades count toward the price. Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        allowPastEndTime: Keep working after endTime if not done. Optional.
        catchUp: Catch up in time. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=Twap(strategyType="Marketable", startTime="09:30:00 US/Eastern"))
    """
    return buildAlgo(
        ALGO_SPECS["Twap"],
        {
            "strategyType": strategyType,
            "startTime": startTime,
            "endTime": endTime,
            "allowPastEndTime": allowPastEndTime,
            "catchUp": catchUp,
        },
    )


def Vwap(
    *,
    maxPctVol: float | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
    allowPastEndTime: bool | None = None,
    noTakeLiq: bool | None = None,
    speedUp: bool | None = None,
) -> Algo:
    """
    VWAP (``Vwap``): Aims for the volume-weighted average price, on a best-
    efforts basis.

    Works LMT orders. Products: STK. Stability: advanced.

    Args:
        maxPctVol: The largest share of the market's volume, 0.1 (10%) to 0.5 (50%). Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        allowPastEndTime: Keep working after endTime if not done. Optional.
        noTakeLiq: Attempt never to take liquidity. Optional.
        speedUp: Compensate for the lower fill rate a limit price causes. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=Vwap(maxPctVol=0.1))
    """
    return buildAlgo(
        ALGO_SPECS["Vwap"],
        {
            "maxPctVol": maxPctVol,
            "startTime": startTime,
            "endTime": endTime,
            "allowPastEndTime": allowPastEndTime,
            "noTakeLiq": noTakeLiq,
            "speedUp": speedUp,
        },
    )


def BalanceImpactRisk(
    *,
    maxPctVol: float | None = None,
    riskAversion: Literal["Get Done", "Aggressive", "Neutral", "Passive"] | None = None,
    forceCompletion: bool | None = None,
) -> Algo:
    """
    Balance Impact and Risk (``BalanceImpactRisk``): For options: balances the
    market impact of trading against the risk of the price moving.

    Works LMT orders. Products: OPT. Stability: advanced.

    Args:
        maxPctVol: The largest share of the market's volume, 0.1 (10%) to 0.5 (50%). Optional.
        riskAversion: How urgently to complete. Optional.
        forceCompletion: Attempt completion by the end of the day. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=BalanceImpactRisk(maxPctVol=0.1, riskAversion="Neutral"))
    """
    return buildAlgo(
        ALGO_SPECS["BalanceImpactRisk"],
        {
            "maxPctVol": maxPctVol,
            "riskAversion": riskAversion,
            "forceCompletion": forceCompletion,
        },
    )


def MinimiseImpact(
    *,
    maxPctVol: float | None = None,
) -> Algo:
    """
    Minimise Impact (``MinImpact``): For options: minimizes market impact.

    Works LMT orders. Products: OPT. Stability: advanced.

    Args:
        maxPctVol: The largest share of the market's volume, 0.1 (10%) to 0.5 (50%). Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=MinimiseImpact(maxPctVol=0.1))
    """
    return buildAlgo(ALGO_SPECS["MinimiseImpact"], {"maxPctVol": maxPctVol})


def ClosePrice(
    *,
    maxPctVol: float | None = None,
    riskAversion: Literal["Get Done", "Aggressive", "Neutral", "Passive"] | None = None,
    startTime: str | None = None,
    forceCompletion: bool | None = None,
) -> Algo:
    """
    Close Price (``ClosePx``): Aims for the closing price: breaks a large order
    down and times its entry.

    Works LMT orders. Stability: advanced.

    Args:
        maxPctVol: The largest share of the market's volume, 0.1 (10%) to 0.5 (50%). Optional.
        riskAversion: How urgently to complete. Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        forceCompletion: Attempt completion by the end of the day. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=ClosePrice(maxPctVol=0.1, riskAversion="Neutral"))
    """
    return buildAlgo(
        ALGO_SPECS["ClosePrice"],
        {
            "maxPctVol": maxPctVol,
            "riskAversion": riskAversion,
            "startTime": startTime,
            "forceCompletion": forceCompletion,
        },
    )


def AccumulateDistribute(
    *,
    componentSize: int | None = None,
    timeBetweenOrders: int | None = None,
    randomizeTime20: bool | None = None,
    randomizeSize55: bool | None = None,
    giveUp: int | None = None,
    catchUp: bool | None = None,
    waitForFill: bool | None = None,
    startTime: str | None = None,
    endTime: str | None = None,
) -> Algo:
    """
    Accumulate/Distribute (``AD``): Splits a large order into componentSize
    pieces sent timeBetweenOrders seconds apart, optionally randomized.

    Works LMT, MKT, REL orders. Stability: advanced.

    Args:
        componentSize: The size of each piece; at most the order's size. Optional.
        timeBetweenOrders: Seconds between pieces. Optional.
        randomizeTime20: Vary the time between pieces by +/- 20%. Optional.
        randomizeSize55: Vary the piece size by +/- 55%. Optional.
        giveUp: A number associated with the clearing. Optional.
        catchUp: Catch up in time. Optional.
        waitForFill: Wait for each piece to fill before the next. Optional.
        startTime: When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.
        endTime: When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'. Optional.

    Example::

        LimitOrder("BUY", 100, 50.00, algo=AccumulateDistribute(componentSize=100, timeBetweenOrders=60))
    """
    return buildAlgo(
        ALGO_SPECS["AccumulateDistribute"],
        {
            "componentSize": componentSize,
            "timeBetweenOrders": timeBetweenOrders,
            "randomizeTime20": randomizeTime20,
            "randomizeSize55": randomizeSize55,
            "giveUp": giveUp,
            "catchUp": catchUp,
            "waitForFill": waitForFill,
            "startTime": startTime,
            "endTime": endTime,
        },
    )


def ComboRouting(
    *,
    nonGuaranteed: bool | None = None,
    legInPriority: int | None = None,
    dontLegInNext: bool | None = None,
) -> Routing:
    """
    How SMART routes a combo (BAG) order: ``routing=`` of any order type
    placed for a combo contract. Each tag left as None is not sent.

    Args:
        nonGuaranteed: Let SMART execute each leg separately for the best execution; the combo is then not guaranteed to fill in proportion.
        legInPriority: IBKR's LeginPrio tag (live trading sends 0).
        dontLegInNext: IBKR's DontLeginNext tag (live trading sends 1).

    Example::

        LimitOrder("BUY", 1, 2.50, routing=ComboRouting(nonGuaranteed=True))
    """
    return buildRouting(
        COMBO_ROUTING,
        {
            "nonGuaranteed": nonGuaranteed,
            "legInPriority": legInPriority,
            "dontLegInNext": dontLegInNext,
        },
    )
