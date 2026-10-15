"""The order types ib_async builds: the single source of truth.

The order type constructors (``generated.py``) and their documentation
(``docs/ordertypes.rst``) are generated from this catalog by
``scripts/generate_ordertypes.py``; tests fail when either is out of date.

Each entry records the fields IBKR expects for the order type and the
products and exchanges IBKR lists it for. Order fields that any order can
carry (cashQty, outsideRth, includeOvernight, ...) are not order types:
they are keyword arguments of every order type constructor, described in
``OPTIONS``.
"""

from __future__ import annotations

import dataclasses

from ..order import COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID
from .spec import (
    AlgoSpec,
    FieldIn,
    FieldValue,
    Kind,
    OptionSpec,
    OrderTypeSpec,
    Param,
    Stability,
)

STABLE, VENUE, ADVANCED = Stability.STABLE, Stability.VENUE, Stability.ADVANCED

LMT_PRICE = Param("lmtPrice", "lmtPrice", "The limit price.")
OPTIONAL_LMT_PRICE = dataclasses.replace(LMT_PRICE, required=False)
LMT_PRICE_OFFSET = Param(
    "lmtPriceOffset",
    "lmtPriceOffset",
    "The limit price's distance from the stop price.",
    required=False,
)
STOP_PRICE = Param("stopPrice", "auxPrice", "The price that triggers the order.")
TOUCH_PRICE = Param(
    "touchPrice", "auxPrice", "The price that, once touched, triggers the order."
)
OFFSET = Param(
    "offset", "auxPrice", "The amount away from the reference price.", required=False
)

PRICE_CAP = Param(
    "priceCap", "lmtPrice", "The worst price accepted, like a limit price."
)
TRAILING_AMOUNT = Param(
    "trailingAmount", "auxPrice", "How far the stop trails, in price.", required=False
)
TRAILING_PERCENT = Param(
    "trailingPercent",
    "trailingPercent",
    "How far the stop trails, in percent.",
    required=False,
)
TRAILING = (TRAILING_AMOUNT.name, TRAILING_PERCENT.name)
TRAIL_STOP_PRICE = Param(
    "trailStopPrice", "trailStopPrice", "The trailing stop price.", required=False
)
MIN_TRADE_QTY = Param("minTradeQty", "minTradeQty", "The smallest fill accepted.")
MIN_COMPETE_SIZE = Param(
    "minCompeteSize", "minCompeteSize", "The minimum size to compete."
)
# The offset off the midpoint when the spread is an even number of cents wide
# (in whole pennies) and an odd number (in half pennies).
MID_OFFSET_AT_WHOLE = Param(
    "midOffsetAtWhole",
    "midOffsetAtWhole",
    "The offset when the spread is an even number of cents wide.",
)
MID_OFFSET_AT_HALF = Param(
    "midOffsetAtHalf",
    "midOffsetAtHalf",
    "The offset when the spread is an odd number of cents wide.",
)

CATALOG: tuple[OrderTypeSpec, ...] = (
    # --- the basics --------------------------------------------------------
    OrderTypeSpec(
        className="MarketOrder",
        title="Market",
        orderType="MKT",
        summary="Buys or sells at the market bid or offer price.",
        usage="Likely to fill, and quickly, but with no price protection: it "
        "may fill far from the displayed bid or ask.",
        stability=STABLE,
        products=(
            "BOND",
            "CFD",
            "EFP",
            "CASH",
            "FUND",
            "FUT",
            "FOP",
            "OPT",
            "STK",
            "WAR",
        ),
        example='"BUY", 100',
    ),
    OrderTypeSpec(
        className="LimitOrder",
        title="Limit",
        orderType="LMT",
        summary="Buys at the limit price or lower, or sells at it or higher.",
        usage="Never fills at a worse price than the limit; it may not fill.",
        stability=STABLE,
        params=(LMT_PRICE,),
        products=("BOND", "CFD", "CASH", "FUT", "FOP", "OPT", "STK", "WAR"),
        example='"BUY", 100, 50.25',
    ),
    OrderTypeSpec(
        className="StopOrder",
        title="Stop",
        orderType="STP",
        summary="Becomes a market order once the stop price is reached.",
        usage="A sell stop below the market limits a loss or protects a "
        "profit on a long position; a buy stop above it does so on a short "
        "sale. Once triggered it may fill well away from the stop price.",
        stability=STABLE,
        params=(STOP_PRICE,),
        products=("CFD", "BAG", "CASH", "FUT", "FOP", "OPT", "STK", "WAR"),
        example='"SELL", 100, 45.00',
    ),
    OrderTypeSpec(
        className="StopLimitOrder",
        title="Stop Limit",
        orderType="STP LMT",
        summary="Becomes a limit order once the stop price is reached.",
        usage="Like a stop order, but once triggered it fills only at the "
        "limit price or better.",
        stability=STABLE,
        params=(LMT_PRICE, STOP_PRICE),
        products=("CFD", "CASH", "FUT", "FOP", "OPT", "STK", "WAR"),
        example='"SELL", 100, 44.50, 45.00',
    ),
    # --- the open and the close ------------------------------------------------
    OrderTypeSpec(
        className="MarketOnCloseOrder",
        title="Market on Close",
        orderType="MOC",
        summary="A market order executed as close to the closing price as possible.",
        stability=STABLE,
        products=("CFD", "FUT", "STK", "WAR"),
        example='"SELL", 100',
    ),
    OrderTypeSpec(
        className="LimitOnCloseOrder",
        title="Limit on Close",
        orderType="LOC",
        summary="A limit order executed at the close if the closing price is "
        "at or better than the limit.",
        usage="Set imbalanceOnly=True to offer it only against the closing "
        "auction's imbalance.",
        stability=STABLE,
        params=(LMT_PRICE,),
        products=("CFD", "FUT", "STK", "WAR"),
        example='"SELL", 100, 50.00',
    ),
    OrderTypeSpec(
        className="MarketOnOpenOrder",
        title="Market on Open",
        orderType="MKT",
        defining=(FieldValue("tif", "OPG"),),
        summary="A market order executed at the opening price.",
        usage="A market order with time in force OPG.",
        stability=STABLE,
        # IBKR lists OPT in one place and FUT in another: both.
        products=("CFD", "FUT", "STK", "OPT", "WAR"),
        example='"BUY", 100',
    ),
    OrderTypeSpec(
        className="LimitOnOpenOrder",
        title="Limit on Open",
        orderType="LMT",
        defining=(FieldValue("tif", "OPG"),),
        summary="A limit order executed at the open if the opening price is "
        "at or better than the limit.",
        usage="A limit order with time in force OPG.",
        stability=STABLE,
        params=(LMT_PRICE,),
        products=("CFD", "STK", "OPT", "WAR"),
        example='"BUY", 100, 50.00',
    ),
    OrderTypeSpec(
        className="AtAuctionOrder",
        title="At Auction",
        orderType="MTL",
        defining=(FieldValue("tif", "AUC"),),
        summary="Entered in the pre-market auction to execute at the "
        "calculated opening price; if not filled on the open, it is "
        "resubmitted as a limit order at that price or the best bid or ask "
        "after the open.",
        stability=STABLE,
        params=(LMT_PRICE,),
        products=("FUT", "STK"),
        example='"BUY", 100, 50.00',
    ),
    # --- triggered by a price --------------------------------------------------
    OrderTypeSpec(
        className="MarketIfTouchedOrder",
        title="Market if Touched",
        orderType="MIT",
        summary="Becomes a market order once the touch price is reached.",
        usage="The mirror of a stop: a buy below the market or a sell above it, "
        "to act on a price level being reached.",
        stability=STABLE,
        params=(TOUCH_PRICE,),
        products=("BOND", "CFD", "CASH", "FUT", "FOP", "OPT", "STK", "WAR"),
        example='"BUY", 100, 48.00',
    ),
    OrderTypeSpec(
        className="LimitIfTouchedOrder",
        title="Limit if Touched",
        orderType="LIT",
        summary="Becomes a limit order once the touch price is reached.",
        stability=STABLE,
        params=(LMT_PRICE, TOUCH_PRICE),
        products=("BOND", "CFD", "CASH", "FUT", "FOP", "OPT", "STK", "WAR"),
        example='"BUY", 100, 48.10, 48.00',
    ),
    OrderTypeSpec(
        className="TrailingStopOrder",
        title="Trailing Stop",
        orderType="TRAIL",
        summary="A stop that follows the market: its stop price moves with "
        "the price by a fixed amount or percent, and never back.",
        usage="Give trailingAmount or trailingPercent.",
        stability=STABLE,
        params=(TRAILING_AMOUNT, TRAILING_PERCENT, TRAIL_STOP_PRICE),
        exactlyOne=(TRAILING,),
        products=("CFD", "CASH", "FOP", "FUT", "OPT", "STK", "WAR"),
        example='"SELL", 100, trailingPercent=2.0',
    ),
    OrderTypeSpec(
        className="TrailingStopLimitOrder",
        title="Trailing Stop Limit",
        orderType="TRAIL LIMIT",
        summary="A trailing stop that, once triggered, becomes a limit order "
        "at the limit price, or at lmtPriceOffset from the stop price as it "
        "trails.",
        usage="Give trailingAmount or trailingPercent, and lmtPrice or lmtPriceOffset.",
        stability=STABLE,
        params=(
            LMT_PRICE_OFFSET,
            OPTIONAL_LMT_PRICE,
            TRAILING_AMOUNT,
            TRAILING_PERCENT,
            TRAIL_STOP_PRICE,
        ),
        exactlyOne=(TRAILING, (LMT_PRICE_OFFSET.name, OPTIONAL_LMT_PRICE.name)),
        products=("BOND", "CFD", "CASH", "FUT", "FOP", "OPT", "STK", "WAR"),
        example='"SELL", 100, lmtPriceOffset=0.10, trailingAmount=1.00',
    ),
    # --- protection and conversion ------------------------------------------
    OrderTypeSpec(
        className="MarketToLimitOrder",
        title="Market to Limit",
        orderType="MTL",
        summary="A market order whose unfilled part becomes a limit order at "
        "the price of its first fill.",
        stability=STABLE,
        products=("CFD", "FUT", "FOP", "OPT", "STK", "WAR"),
        example='"BUY", 100',
    ),
    OrderTypeSpec(
        className="MarketWithProtectionOrder",
        title="Market with Protection",
        orderType="MKT PRT",
        summary="A market order that, if it does not execute in full at once, "
        "is canceled and resubmitted as a limit order at a price the "
        "exchange sets close to the market.",
        usage="IBKR lists it for futures and futures options; an application "
        "trading live also sends it for SPXW index options.",
        stability=STABLE,
        products=("FUT", "FOP"),
        example='"BUY", 1',
    ),
    OrderTypeSpec(
        className="StopWithProtectionOrder",
        title="Stop with Protection",
        orderType="STP PRT",
        summary="A stop that becomes a market order with protection once triggered.",
        stability=STABLE,
        params=(STOP_PRICE,),
        products=("FUT",),
        example='"SELL", 1, 4500.00',
    ),
    # --- pegged and relative ----------------------------------------------------
    OrderTypeSpec(
        className="RelativeOrder",
        title="Relative (Pegged to Primary)",
        orderType="REL",
        summary="Pegged to the national best bid (buy) or offer (sell), more "
        "aggressive by offset. It follows the quote toward the market (a buy "
        "rises with the bid) but not away from it.",
        usage="IBKR describes priceCap as optional, but rejects "
        "the order without it in live trading. Not available on paper "
        "trading accounts.",
        stability=STABLE,
        params=(
            Param("offset", "auxPrice", "How much more aggressive than the NBBO."),
            PRICE_CAP,
        ),
        products=("CFD", "STK", "OPT", "FUT"),
        example='"BUY", 100, 0.01, 50.00',
    ),
    OrderTypeSpec(
        className="PassiveRelativeOrder",
        title="Passive Relative",
        orderType="PASSV REL",
        summary="Pegged to the national best bid (buy) or offer (sell), less "
        "aggressive by offset: a buy subtracts the offset from the bid.",
        stability=STABLE,
        params=(
            Param("offset", "auxPrice", "How much less aggressive than the NBBO."),
            dataclasses.replace(PRICE_CAP, required=False),
        ),
        products=("STK", "WAR"),
        example='"BUY", 100, 0.01',
    ),
    OrderTypeSpec(
        className="PeggedToMarketOrder",
        title="Pegged to Market",
        orderType="PEG MKT",
        summary="Pegged to the national best offer (buy) or bid (sell): a "
        "buy is priced at the offer less offset, a sell at the bid plus "
        "offset.",
        stability=STABLE,
        params=(
            Param("offset", "auxPrice", "The amount away from the NBBO."),
            dataclasses.replace(PRICE_CAP, required=False),
        ),
        products=("STK",),
        example='"BUY", 100, 0.01',
    ),
    OrderTypeSpec(
        className="PeggedToMidpointOrder",
        title="Pegged to Midpoint",
        orderType="PEG MID",
        summary="Pegged to the NBBO midpoint, adjusted by offset, never "
        "beyond the limit price.",
        stability=STABLE,
        params=(LMT_PRICE, OFFSET),
        products=("STK",),
        example='"BUY", 100, 50.00, offset=0.01',
    ),
    OrderTypeSpec(
        className="MidpriceOrder",
        title="Midprice",
        orderType="MIDPRICE",
        summary="Fills at the NBBO midpoint or better.",
        usage="IBKR describes priceCap as optional, but rejects the "
        "order without it in live trading, and refuses it outside regular "
        "trading hours. SMART-routed US stocks only.",
        stability=STABLE,
        params=(PRICE_CAP,),
        products=("STK",),
        requires="TWS 975+",
        example='"BUY", 100, 50.00',
    ),
    OrderTypeSpec(
        className="SnapToMidpointOrder",
        title="Snap to Midpoint",
        orderType="SNAP MID",
        summary="Priced once, when placed, at the NBBO midpoint: a buy less "
        "offset, a sell plus offset. It does not move afterwards.",
        stability=STABLE,
        params=(LMT_PRICE, OFFSET),
        example='"BUY", 100, 50.00, offset=0.01',
    ),
    OrderTypeSpec(
        className="SnapToPrimaryOrder",
        title="Snap to Primary",
        orderType="SNAP PRIM",
        summary="Priced once, when placed, at the national best bid plus "
        "offset (buy) or offer less offset (sell). It does not move "
        "afterwards.",
        stability=STABLE,
        params=(LMT_PRICE, OFFSET),
        example='"BUY", 100, 50.00, offset=0.01',
    ),
    OrderTypeSpec(
        className="SnapToMarketOrder",
        title="Snap to Market",
        orderType="SNAP MKT",
        summary="Priced once, when placed, at the national best offer less "
        "offset (buy) or bid plus offset (sell). It does not move afterwards.",
        stability=STABLE,
        params=(LMT_PRICE, OFFSET),
        example='"BUY", 100, 50.00, offset=0.01',
    ),
    # --- limit order variants ----------------------------------------------------
    OrderTypeSpec(
        className="DiscretionaryOrder",
        title="Discretionary",
        orderType="LMT",
        summary="A limit order with a hidden discretionary amount: the market "
        "sees only the limit price, but it may execute up to that far beyond.",
        stability=STABLE,
        params=(
            LMT_PRICE,
            Param(
                "discretionaryAmt",
                "discretionaryAmt",
                "How far beyond the limit price it may execute.",
            ),
        ),
        products=("STK",),
        example='"BUY", 100, 50.00, 0.05',
    ),
    OrderTypeSpec(
        className="SweepToFillOrder",
        title="Sweep to Fill",
        orderType="LMT",
        defining=(FieldValue("sweepToFill", True),),
        summary="A limit order that takes the best price and, at once, the "
        "next best prices, for speed of execution over price.",
        usage="SMART-routed only.",
        stability=STABLE,
        params=(LMT_PRICE,),
        products=("CFD", "STK", "WAR"),
        example='"BUY", 100, 50.00',
    ),
    # --- specific venues --------------------------------------------------------
    OrderTypeSpec(
        className="BlockOrder",
        title="Block",
        orderType="LMT",
        defining=(FieldValue("blockOrder", True),),
        summary="A limit order for 50 or more option contracts, executed as a "
        "block on ISE.",
        stability=VENUE,
        params=(LMT_PRICE,),
        products=("OPT",),
        exchanges=("ISE",),
        example='"BUY", 50, 2.50',
    ),
    OrderTypeSpec(
        className="BoxTopOrder",
        title="Box Top",
        orderType="BOX TOP",
        summary="A market order at the best price on BOX; any unfilled part "
        "becomes a limit order at the price of its fill.",
        stability=VENUE,
        products=("OPT",),
        exchanges=("BOX",),
        example='"BUY", 10',
    ),
    OrderTypeSpec(
        className="AuctionLimitOrder",
        title="Auction Limit",
        orderType="LMT",
        summary="A limit order in a BOX price improvement auction.",
        stability=VENUE,
        params=(
            LMT_PRICE,
            Param(
                "auctionStrategy",
                "auctionStrategy",
                "1 match, 2 improvement, 3 transparent.",
            ),
        ),
        products=("OPT",),
        exchanges=("BOX",),
        example='"BUY", 10, 2.50, 2',
    ),
    OrderTypeSpec(
        className="PeggedToStockOrder",
        title="Pegged to Stock",
        orderType="PEG STK",
        summary="An option order whose price moves by delta times the "
        "underlying's change from the stock reference price.",
        usage="delta is entered as an absolute value, taken as positive for "
        "calls and negative for puts. Without stockRefPrice IBKR uses the "
        "underlying's NBBO midpoint at placement; stockRangeLower and "
        "stockRangeUpper cancel the order when the underlying leaves the "
        "range. On BOX this is the Auction Pegged to Stock order.",
        stability=VENUE,
        params=(
            Param("delta", "delta", "The option's price change per underlying move."),
            Param("startingPrice", "startingPrice", "The option price to start from."),
            Param(
                "stockRefPrice",
                "stockRefPrice",
                "The underlying price the change is measured from.",
                required=False,
            ),
            Param(
                "stockRangeLower",
                "stockRangeLower",
                "Cancel below this underlying price.",
                required=False,
            ),
            Param(
                "stockRangeUpper",
                "stockRangeUpper",
                "Cancel above this underlying price.",
                required=False,
            ),
        ),
        products=("OPT",),
        example='"BUY", 1, 0.5, 2.50, stockRefPrice=100.00',
    ),
    OrderTypeSpec(
        className="PegBestOrder",
        title="Pegged to Best (IBKR ATS)",
        orderType="PEG BEST",
        defining=(FieldValue("notHeld", True),),
        summary="Pegged to the best price on IBKR's ATS.",
        stability=VENUE,
        params=(
            LMT_PRICE,
            MIN_TRADE_QTY,
            MIN_COMPETE_SIZE,
            Param(
                "competeAgainstBestOffset",
                "competeAgainstBestOffset",
                "The offset off the midpoint.",
            ),
        ),
        products=("STK",),
        exchanges=("IBKRATS",),
        example='"BUY", 100, 50.00, 100, 100, 0.01',
    ),
    OrderTypeSpec(
        className="PegBestUpToMidOrder",
        title="Pegged to Best up to Midpoint (IBKR ATS)",
        orderType="PEG BEST",
        defining=(
            FieldValue("notHeld", True),
            FieldValue(
                "competeAgainstBestOffset", COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID
            ),
        ),
        summary="Pegged to the best price on IBKR's ATS, competing up to the "
        "midpoint, offset by midOffsetAtWhole or midOffsetAtHalf depending on "
        "the spread.",
        stability=VENUE,
        params=(
            LMT_PRICE,
            MIN_TRADE_QTY,
            MIN_COMPETE_SIZE,
            MID_OFFSET_AT_WHOLE,
            MID_OFFSET_AT_HALF,
        ),
        products=("STK",),
        exchanges=("IBKRATS",),
        example='"BUY", 100, 50.00, 100, 100, 0.01, 0.005',
    ),
    OrderTypeSpec(
        className="IbkrAtsLimitOrder",
        title="Limit (IBKR ATS)",
        orderType="LMT",
        defining=(FieldValue("notHeld", True),),
        summary="A not-held limit order on IBKR's ATS.",
        usage="For non-marketable US stock orders; route the contract to IBKRATS.",
        stability=VENUE,
        params=(LMT_PRICE,),
        products=("STK",),
        exchanges=("IBKRATS",),
        example='"BUY", 100, 50.00',
    ),
    OrderTypeSpec(
        className="PegMidOrder",
        title="Pegged to Midpoint (IBKR ATS)",
        orderType="PEG MID",
        defining=(FieldValue("notHeld", True),),
        summary="Pegged to the midpoint on IBKR's own venue, offset by "
        "midOffsetAtWhole or midOffsetAtHalf depending on the spread.",
        usage="Route stocks to IBKRATS and options to IBUSOPT. Live trading "
        "sends it without the offsets or a minimum fill.",
        stability=VENUE,
        params=(
            LMT_PRICE,
            dataclasses.replace(MIN_TRADE_QTY, required=False),
            dataclasses.replace(MID_OFFSET_AT_WHOLE, required=False),
            dataclasses.replace(MID_OFFSET_AT_HALF, required=False),
        ),
        products=("STK", "OPT"),
        exchanges=("IBKRATS", "IBUSOPT"),
        example='"BUY", 100, 50.00',
    ),
    # --- combos: for BAG contracts, whose legs are OPT, STK or FUT ----------------
    OrderTypeSpec(
        className="ComboLegPricesOrder",
        title="Combo with Leg Prices",
        orderType="LMT",
        summary="A limit order for a combo (BAG) contract with a limit price "
        "for each leg instead of one for the combo.",
        usage="One price per leg, in the order of the contract's legs. For "
        "one price for the whole combo, use LimitOrder.",
        stability=STABLE,
        params=(
            Param(
                "legPrices",
                "orderComboLegs",
                "The limit price of each leg, in leg order.",
                kind=Kind.LEG_PRICES,
            ),
        ),
        products=("BAG",),
        example='"BUY", 1, [2.50, 1.20]',
    ),
    OrderTypeSpec(
        className="RelativeLimitComboOrder",
        title="Relative + Limit (combo)",
        orderType="REL + LMT",
        summary="IBKR's relative plus limit combo order, with the combo's "
        "limit price. IBKR does not document how it works the legs.",
        stability=ADVANCED,
        params=(LMT_PRICE,),
        products=("BAG",),
        example='"BUY", 1, 2.50',
    ),
    OrderTypeSpec(
        className="RelativeMarketComboOrder",
        title="Relative + Market (combo)",
        orderType="REL + MKT",
        summary="A combo order whose legs start as relative orders, pegged to "
        "the bid (buy) or ask (sell); once a leg fills, the remaining legs "
        "are sent at market.",
        stability=ADVANCED,
        products=("BAG",),
        example='"BUY", 1',
    ),
    # --- advanced -----------------------------------------------------------------
    OrderTypeSpec(
        className="VolatilityOrder",
        title="Volatility",
        orderType="VOL",
        summary="An option order priced from an implied volatility.",
        usage="volatilityType: 1 daily, 2 annual. With continuousUpdate, TWS "
        "updates the price as the underlying moves. Delta-neutral hedging is "
        "set with the deltaNeutral* fields.",
        stability=ADVANCED,
        params=(
            Param("volatility", "volatility", "The implied volatility, in percent."),
            Param("volatilityType", "volatilityType", "1 daily, 2 annual."),
        ),
        products=("FOP", "OPT"),
        example='"BUY", 1, 25.0, 2',
    ),
    OrderTypeSpec(
        className="PeggedToBenchmarkOrder",
        title="Pegged to Benchmark",
        orderType="PEG BENCH",
        summary="Pegged to another contract: its price moves by "
        "peggedChangeAmount each time the reference contract moves by "
        "referenceChangeAmount.",
        usage="Both contracts must use the same currency.",
        stability=ADVANCED,
        params=(
            Param("startingPrice", "startingPrice", "The price to start from."),
            Param(
                "referenceContractId",
                "referenceContractId",
                "The conId of the contract it is pegged to.",
            ),
            Param(
                "referenceExchangeId",
                "referenceExchangeId",
                "The reference contract's exchange.",
            ),
            Param(
                "peggedChangeAmount",
                "peggedChangeAmount",
                "How much the order price changes per step.",
            ),
            Param(
                "referenceChangeAmount",
                "referenceChangeAmount",
                "How much the reference contract moves per step.",
            ),
            Param(
                "isPeggedChangeAmountDecrease",
                "isPeggedChangeAmountDecrease",
                "Whether the pegged price decreases rather than increases.",
                required=False,
            ),
            Param(
                "stockRefPrice",
                "stockRefPrice",
                "The reference price the change is measured from.",
                required=False,
            ),
            Param(
                "stockRangeLower",
                "stockRangeLower",
                "Cancel below this reference price.",
                required=False,
            ),
            Param(
                "stockRangeUpper",
                "stockRangeUpper",
                "Cancel above this reference price.",
                required=False,
            ),
        ),
        products=("STK", "OPT"),
        example='"BUY", 100, 50.00, 12345, "ISLAND", 0.02, 0.01',
    ),
)

# The catalog by class name.
SPECS: dict[str, OrderTypeSpec] = {spec.className: spec for spec in CATALOG}


# --- IB algos: strategies that work an order of the types they list ------------

RISK_AVERSION = ("Get Done", "Aggressive", "Neutral", "Passive")


def _algo(
    name: str, tag: str, doc: str, kind: Kind, allowed: tuple[str, ...] = ()
) -> Param:
    """An algo parameter: an optional tag value in algoParams."""
    return Param(name, "algoParams", doc, False, tag=tag, kind=kind, allowed=allowed)


TIME = "as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'"
START = _algo("startTime", "startTime", f"When to start, {TIME}.", Kind.STR)
END = _algo("endTime", "endTime", f"When to finish, {TIME}.", Kind.STR)
PAST_END = _algo(
    "allowPastEndTime",
    "allowPastEndTime",
    "Keep working after endTime if not done.",
    Kind.BOOL,
)
NO_TAKE_LIQ = _algo(
    "noTakeLiq", "noTakeLiq", "Attempt never to take liquidity.", Kind.BOOL
)
FORCE = _algo(
    "forceCompletion",
    "forceCompletion",
    "Attempt completion by the end of the day.",
    Kind.BOOL,
)
CATCH_UP = _algo("catchUp", "catchUp", "Catch up in time.", Kind.BOOL)
RISK = _algo(
    "riskAversion",
    "riskAversion",
    "How urgently to complete.",
    Kind.STR,
    allowed=RISK_AVERSION,
)


def _share(name: str, doc: str) -> Param:
    """A share of the market's volume, 0.1 (10%) to 0.5 (50%)."""
    return _algo(name, name, f"{doc}, 0.1 (10%) to 0.5 (50%).", Kind.FLOAT)


MAX_PCT_VOL = _share("maxPctVol", "The largest share of the market's volume")
PCT_VOL = _share("pctVol", "The share of the market's volume")
START_PCT = _share("startPctVol", "The share of volume at the start")
END_PCT = _share("endPctVol", "The share of volume at the end")

ALGOS: tuple[AlgoSpec, ...] = (
    AlgoSpec(
        className="Adaptive",
        title="Adaptive",
        strategy="Adaptive",
        summary="Works a market or limit order between the bid and ask, "
        "trading speed against price by priority.",
        usage="Day orders only. Live trading found it refused outside regular "
        "trading hours, and for CME futures options and SPXW index options.",
        stability=STABLE,
        orderTypes=("LMT", "MKT"),
        params=(
            _algo(
                "priority",
                "adaptivePriority",
                "Urgent fills fastest, Patient seeks the best price.",
                Kind.STR,
                allowed=("Urgent", "Normal", "Patient"),
            ),
        ),
        conditions=(FieldIn("tif", ("", "DAY")), FieldIn("outsideRth", (False,))),
        example='priority="Urgent"',
    ),
    AlgoSpec(
        className="ArrivalPrice",
        title="Arrival Price",
        strategy="ArrivalPx",
        summary="Aims for the bid/ask midpoint at the time the order is "
        "submitted, trading off market impact against the risk of the price "
        "moving.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(MAX_PCT_VOL, RISK, START, END, FORCE, PAST_END),
        example='maxPctVol=0.1, riskAversion="Neutral"',
    ),
    AlgoSpec(
        className="DarkIce",
        title="Dark Ice",
        strategy="DarkIce",
        summary="Shows only displaySize of a limit order, randomizing the size "
        "shown and keeping the rest hidden.",
        usage="Day orders only.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(
            _algo("displaySize", "displaySize", "The size to show.", Kind.INT),
            START,
            END,
            PAST_END,
        ),
        conditions=(FieldIn("tif", ("", "DAY")),),
        example="displaySize=100",
    ),
    AlgoSpec(
        className="PercentOfVolume",
        title="Percentage of Volume",
        strategy="PctVol",
        summary="Trades a fixed share of the market's volume.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(PCT_VOL, START, END, NO_TAKE_LIQ),
        example="pctVol=0.1",
    ),
    AlgoSpec(
        className="PriceVariantPercentOfVolume",
        title="Price Variant Percentage of Volume",
        strategy="PctVolPx",
        summary="Trades a share of volume that changes with the price: by "
        "deltaPctVol per move, between minPctVol4Px and maxPctVol4Px.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(
            PCT_VOL,
            _share("deltaPctVol", "The change in share per price move"),
            _share("minPctVol4Px", "The lowest share"),
            _share("maxPctVol4Px", "The highest share"),
            START,
            END,
            NO_TAKE_LIQ,
        ),
        example="pctVol=0.1, deltaPctVol=0.1",
    ),
    AlgoSpec(
        className="SizeVariantPercentOfVolume",
        title="Size Variant Percentage of Volume",
        strategy="PctVolSz",
        summary="Trades a share of volume that moves from startPctVol to "
        "endPctVol as the order fills.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(START_PCT, END_PCT, START, END, NO_TAKE_LIQ),
        example="startPctVol=0.2, endPctVol=0.4",
    ),
    AlgoSpec(
        className="TimeVariantPercentOfVolume",
        title="Time Variant Percentage of Volume",
        strategy="PctVolTm",
        summary="Trades a share of volume that moves from startPctVol to "
        "endPctVol between startTime and endTime.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(START_PCT, END_PCT, START, END, NO_TAKE_LIQ),
        example="startPctVol=0.2, endPctVol=0.4",
    ),
    AlgoSpec(
        className="Twap",
        title="TWAP",
        strategy="Twap",
        summary="Aims for the time-weighted average price from when the order "
        "is submitted to when it completes.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(
            _algo(
                "strategyType",
                "strategyType",
                "Which trades count toward the price.",
                Kind.STR,
                allowed=(
                    "Marketable",
                    "Matching",
                    "Midpoint",
                    "Matching Same Side",
                    "Matching Last",
                ),
            ),
            START,
            END,
            PAST_END,
            CATCH_UP,
        ),
        products=("STK",),
        example='strategyType="Marketable", startTime="09:30:00 US/Eastern"',
    ),
    AlgoSpec(
        className="Vwap",
        title="VWAP",
        strategy="Vwap",
        summary="Aims for the volume-weighted average price, on a best-efforts basis.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(
            MAX_PCT_VOL,
            START,
            END,
            PAST_END,
            NO_TAKE_LIQ,
            _algo(
                "speedUp",
                "speedUp",
                "Compensate for the lower fill rate a limit price causes.",
                Kind.BOOL,
            ),
        ),
        products=("STK",),
        example="maxPctVol=0.1",
    ),
    AlgoSpec(
        className="BalanceImpactRisk",
        title="Balance Impact and Risk",
        strategy="BalanceImpactRisk",
        summary="For options: balances the market impact of trading against "
        "the risk of the price moving.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(MAX_PCT_VOL, RISK, FORCE),
        products=("OPT",),
        example='maxPctVol=0.1, riskAversion="Neutral"',
    ),
    AlgoSpec(
        className="MinimiseImpact",
        title="Minimise Impact",
        strategy="MinImpact",
        summary="For options: minimizes market impact.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(MAX_PCT_VOL,),
        products=("OPT",),
        example="maxPctVol=0.1",
    ),
    AlgoSpec(
        className="ClosePrice",
        title="Close Price",
        strategy="ClosePx",
        summary="Aims for the closing price: breaks a large order down and "
        "times its entry.",
        stability=ADVANCED,
        orderTypes=("LMT",),
        params=(MAX_PCT_VOL, RISK, START, FORCE),
        example='maxPctVol=0.1, riskAversion="Neutral"',
    ),
    AlgoSpec(
        className="AccumulateDistribute",
        title="Accumulate/Distribute",
        strategy="AD",
        summary="Splits a large order into componentSize pieces sent "
        "timeBetweenOrders seconds apart, optionally randomized.",
        stability=ADVANCED,
        orderTypes=("LMT", "MKT", "REL"),
        params=(
            _algo(
                "componentSize",
                "componentSize",
                "The size of each piece; at most the order's size.",
                Kind.INT,
            ),
            _algo(
                "timeBetweenOrders",
                "timeBetweenOrders",
                "Seconds between pieces.",
                Kind.INT,
            ),
            _algo(
                "randomizeTime20",
                "randomizeTime20",
                "Vary the time between pieces by +/- 20%.",
                Kind.BOOL,
            ),
            _algo(
                "randomizeSize55",
                "randomizeSize55",
                "Vary the piece size by +/- 55%.",
                Kind.BOOL,
            ),
            _algo(
                "giveUp", "giveUp", "A number associated with the clearing.", Kind.INT
            ),
            CATCH_UP,
            _algo(
                "waitForFill",
                "waitForFill",
                "Wait for each piece to fill before the next.",
                Kind.BOOL,
            ),
            _algo("startTime", "activeTimeStart", f"When to start, {TIME}.", Kind.STR),
            _algo("endTime", "activeTimeEnd", f"When to finish, {TIME}.", Kind.STR),
        ),
        example="componentSize=100, timeBetweenOrders=60",
    ),
)

# The algos by constructor name, and by strategy (to name an order's algo).
ALGO_SPECS: dict[str, AlgoSpec] = {spec.className: spec for spec in ALGOS}
ALGO_BY_STRATEGY: dict[str, AlgoSpec] = {spec.strategy: spec for spec in ALGOS}


# --- SMART routing of combo (BAG) orders ---------------------------------------
# routing= of any order type, as ComboRouting(...).


def _routing(name: str, tag: str, doc: str, kind: Kind) -> Param:
    return Param(name, "smartComboRoutingParams", doc, False, tag=tag, kind=kind)


COMBO_ROUTING: tuple[Param, ...] = (
    _routing(
        "nonGuaranteed",
        "NonGuaranteed",
        "Let SMART execute each leg separately for the best execution; the "
        "combo is then not guaranteed to fill in proportion.",
        Kind.BOOL,
    ),
    _routing(
        "legInPriority",
        "LeginPrio",
        "IBKR's LeginPrio tag (live trading sends 0).",
        Kind.INT,
    ),
    _routing(
        "dontLegInNext",
        "DontLeginNext",
        "IBKR's DontLeginNext tag (live trading sends 1).",
        Kind.BOOL,
    ),
)


# --- order options: fields any order type takes --------------------------------

OPTIONS: tuple[OptionSpec, ...] = (
    OptionSpec(
        title="Time in force",
        fields=("tif", "goodTillDate", "goodAfterTime"),
        summary='How long the order works: "DAY"; "GTC" until canceled; '
        '"IOC" fills what it can at once and cancels the rest; "FOK" fills '
        'entirely at once or is canceled; "GTD" until goodTillDate; "DTC" '
        'day until canceled; "OPG" for a market or limit on open order. '
        "goodAfterTime is when the order becomes active.",
        usage="Times are 'yyyymmdd hh:mm:ss' with an optional zone, such as "
        "'20261231 16:00:00 US/Eastern'.",
        stability=STABLE,
        example='LimitOrder("BUY", 100, 50.00, tif="GTD", '
        'goodTillDate="20261231 16:00:00 US/Eastern")',
    ),
    OptionSpec(
        title="Outside regular trading hours",
        fields=("outsideRth",),
        summary="Lets the order also trigger or fill outside regular trading hours.",
        stability=STABLE,
        example='LimitOrder("BUY", 100, 50.00, outsideRth=True)',
    ),
    OptionSpec(
        title="Overnight session",
        fields=("includeOvernight",),
        summary="Includes overnight trading.",
        stability=VENUE,
        products=("STK",),
        example='LimitOrder("BUY", 100, 50.00, includeOvernight=True)',
    ),
    OptionSpec(
        title="Cash quantity",
        fields=("cashQty",),
        summary="The quantity as an amount of cash: a forex order in the "
        "pair's second currency.",
        usage="Live trading passes a totalQuantity of 0 with it.",
        stability=VENUE,
        products=("CASH",),
        example='LimitOrder("BUY", 0, 1.10, cashQty=10_000)',
    ),
    OptionSpec(
        title="Hidden and iceberg",
        fields=("hidden", "displaySize"),
        summary="hidden keeps the order out of the market depth shown to "
        "others; displaySize is the size shown, for an iceberg order.",
        usage="hidden applies only to orders routed to NASDAQ.",
        stability=VENUE,
        example='LimitOrder("BUY", 1_000, 50.00, displaySize=100)',
    ),
    OptionSpec(
        title="Fill conditions",
        fields=("allOrNone", "minQty"),
        summary="allOrNone fills the whole order in a single execution or "
        "not at all; minQty makes it a minimum quantity order.",
        stability=VENUE,
        example='LimitOrder("BUY", 1_000, 50.00, allOrNone=True)',
    ),
    OptionSpec(
        title="Conditions",
        fields=("conditions", "conditionsIgnoreRth", "conditionsCancelOrder"),
        summary="Activate the order (or with conditionsCancelOrder, cancel "
        "it) when conditions on price, time, margin, execution, volume or "
        "percent change hold: a list of PriceCondition, TimeCondition, ... "
        "joined by their conjunction (and/or).",
        usage="Only limit orders can be canceled by conditions.",
        stability=STABLE,
        example='LimitOrder("BUY", 100, 50.00, conditions=[TimeCondition('
        'time="20261231 15:30:00 US/Eastern")])',
    ),
    OptionSpec(
        title="One cancels all",
        fields=("ocaGroup", "ocaType"),
        summary="When an order of an ocaGroup executes, in full or in part, "
        "the rest are canceled (ocaType 1) or reduced in proportion (2), "
        "with overfill protection (block); 3 reduces them without it.",
        usage="IB.oneCancelsAll(orders, group, type) sets both on a list of orders.",
        stability=STABLE,
        example='LimitOrder("SELL", 100, 55.00, ocaGroup="exit-1", ocaType=1)',
    ),
    OptionSpec(
        title="Parent orders and transmit",
        fields=("parentId", "transmit"),
        summary="A child order (a bracket's profit taker or stop, an "
        "adjustable stop, an FX hedge) names its parent's orderId. TWS holds "
        "an order sent with transmit=False; the last of a group, sent with "
        "transmit=True, sends its parent and siblings with it.",
        usage="IB.bracketOrder builds a bracket with ids and transmit set.",
        stability=STABLE,
        example='StopOrder("SELL", 100, 45.00, parentId=1, transmit=True)',
    ),
    OptionSpec(
        title="Preset stop loss and profit taker",
        fields=("slOrderType", "slOrderId", "ptOrderType", "ptOrderId"),
        summary='With slOrderType and ptOrderType "PRESET", TWS attaches a '
        "stop loss and profit taker with the parameters of its order "
        "presets; slOrderId and ptOrderId are order ids reserved for them.",
        stability=ADVANCED,
        example='LimitOrder("BUY", 100, 50.00, slOrderType="PRESET", '
        'slOrderId=2, ptOrderType="PRESET", ptOrderId=3)',
    ),
    OptionSpec(
        title="Account and reference",
        fields=("account", "modelCode", "orderRef"),
        summary="The account the order is for, or a financial advisor's "
        "model; and a reference that comes back on the order's executions.",
        stability=STABLE,
        example='LimitOrder("BUY", 100, 50.00, account="U1234567", orderRef="entry")',
    ),
    OptionSpec(
        title="What if",
        fields=("whatIf",),
        summary="Get the order's commission and margin without placing it.",
        usage="IB.whatIfOrder(contract, order) sets it and returns the OrderState.",
        stability=STABLE,
        example='LimitOrder("BUY", 100, 50.00, whatIf=True)',
    ),
    OptionSpec(
        title="Manual order time",
        fields=("manualOrderTime",),
        summary="For brokers and advisors entering an order by hand: when it "
        "was entered, as 'YYYYMMDD-HH:mm:ss' in UTC.",
        stability=VENUE,
        example='LimitOrder("BUY", 100, 50.00, manualOrderTime="20261015-13:00:00")',
    ),
    OptionSpec(
        title="CME tagging",
        fields=("extOperator", "manualOrderIndicator"),
        summary="Under CME Rule 576, manualOrderIndicator marks an order "
        "manual (1) or automated (0); extOperator names the operator, for "
        "all US futures exchanges.",
        stability=VENUE,
        products=("FUT",),
        example='LimitOrder("BUY", 1, 5_000.00, extOperator="trader1", '
        "manualOrderIndicator=0)",
    ),
    OptionSpec(
        title="Customer account",
        fields=("customerAccount",),
        summary="For nondisclosed omnibus accounts, where it is required: the "
        "identifier of the account within the omnibus structure. Not for "
        "other accounts.",
        stability=VENUE,
        example='LimitOrder("BUY", 100, 50.00, customerAccount="CUST1")',
    ),
)


# --- IBKR's order type codes ------------------------------------------------------
# Every IBKR order type code, with the other spellings IBKR accepts for it and
# contract details list it by.
IBKR_ORDER_TYPES: dict[str, tuple[str, ...]] = {
    "MKT": ("MARKET",),
    "LMT": ("LIMIT",),
    "STP": ("STOP",),
    "STP LMT": ("STOP LIMIT", "STOPLIMIT", "STOPLMT", "STPLMT"),
    "REL": ("RELATIVE",),
    "TRAIL": ("TRAILING STOP",),
    "BOX TOP": ("BOXTOP", "BOX_TOP"),
    "FIX PEGGED": ("FIXPEGGED",),
    "LIT": (),
    "LMT + MKT": ("LMT+MKT",),
    "LOC": ("LMT CLS", "LMTCLS"),
    "MIDPRICE": ("MIDPX",),
    "MIT": (),
    "MKT PRT": ("MKTPRT",),
    "MOC": ("MKT CLS", "MKTCLS"),
    "MTL": ("MKT TO LMT", "MKTTOLMT"),
    "PASSV REL": (),
    "PEG BENCH": ("PEGBENCH",),
    "PEG BEST": ("PEGBEST",),
    "PEG MID": ("PEGMID",),
    "PEG MKT": ("PEGMKT",),
    "PEG PRIM": ("PEGPRIM",),
    "PEG STK": ("PEGSTK",),
    "REL + LMT": ("REL+LMT",),
    "REL + MKT": ("REL+MKT",),
    "SNAP MID": ("SNAPMID",),
    "SNAP MKT": ("SNAPMKT",),
    "SNAP PRIM": ("SNAPPRIM", "SNAPREL"),
    "STP PRT": ("STOP PROTECT",),
    "TRAIL LIMIT": ("TRAILLMT", "TRAILLIMIT"),
    "TRAIL LIT": ("TRAILLIT",),
    "TRAIL LMT + MKT": (),
    "TRAIL MIT": ("TRAILMIT",),
    "TRAIL REL + MKT": (),
    "VOL": ("VOLATILITY", "VOLAT"),
    "VWAP": (),
    "QUOTE": (),
    "PPV": ("PEG PRM VOL", "PEGPRIMVOL", "PEGPRMVOL"),
    "PDV": ("PEG MID VOL", "PEGMIDVOL"),
    "PMV": ("PEG MKT VOL", "PEGMKTVOL"),
    "PSV": ("PEG SURF VOL", "PEGSURFVOL", "PEGSRFVOL"),
}

# Why the codes the catalog does not build are left out; set their fields on
# Order directly.
VOLATILITY_PEG = "A volatility-pegged option type IBKR does not document for the API."
NOT_BUILT: dict[str, str] = {
    "FIX PEGGED": "IBKR does not document its parameters.",
    "PEG PRIM": "IBKR marks it uncertain; Relative (REL) is IBKR's order "
    "pegged to the primary price.",
    "LMT + MKT": "TWS takes its combo price as a trigger price; IBKR does "
    "not document how the API sends it.",
    "TRAIL LIT": "IBKR does not document how to build it.",
    "TRAIL MIT": "IBKR does not document how to build it.",
    "TRAIL LMT + MKT": "A trailing combo type IBKR does not document for the API.",
    "TRAIL REL + MKT": "A trailing combo type IBKR does not document for the API.",
    "VWAP": "IBKR does not document it for the API; the Vwap algo works an "
    "order for the volume-weighted average price.",
    "QUOTE": "A quote in reply to a request for quote, not an order to trade.",
    "PPV": VOLATILITY_PEG,
    "PDV": VOLATILITY_PEG,
    "PMV": VOLATILITY_PEG,
    "PSV": VOLATILITY_PEG,
}
