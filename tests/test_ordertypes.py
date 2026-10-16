"""The order types built from the catalog: construction, validation, lookup."""

from __future__ import annotations

import dataclasses
import inspect
import itertools
import math
from decimal import Decimal
from pathlib import Path

import pytest

import ib_async
from ib_async import Future, Option, Order, Stock, TagValue, ordertypes
from ib_async.ordertypes import (
    CATALOG,
    Adaptive,
    LimitOnOpenOrder,
    LimitOrder,
    MarketOnCloseOrder,
    OrderTypeError,
    PeggedToMidpointOrder,
    PegMidOrder,
    SnapToMidpointOrder,
    TrailingStopOrder,
    catalog,
    checkOrder,
    specOf,
)
from ib_async.ordertypes.spec import (
    ORDER_DEFAULTS,
    Adjustment,
    AlgoSpec,
    FieldIn,
    FieldValue,
    Kind,
    OrderTypeSpec,
    Param,
    Stability,
)

SPECS = list(CATALOG)


def example(spec):
    """The order the spec's documented example builds."""
    return eval(f"{spec.className}({spec.example})", vars(ib_async))


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.className)
def test_example_builds_the_order_type(spec):
    order = example(spec)
    assert type(order) is Order
    assert order.orderType == spec.orderType
    for field, value in spec.definingFields.items():
        assert getattr(order, field) == value
    for param in spec.params:
        if param.required:
            assert getattr(order, param.field) not in (None, ""), param.name


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.className)
def test_spec_of_recognizes_the_example(spec):
    assert specOf(example(spec)) is spec


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.className)
def test_signature_follows_the_catalog(spec):
    parameters = inspect.signature(getattr(ordertypes, spec.className)).parameters
    names = list(parameters)
    assert names[:2] == ["action", "totalQuantity"]
    assert names[-4:] == ["algo", "routing", "adjust", "kwargs"]
    assert names[2:-4] == [p.name for p in spec.params if p.required] + [
        p.name for p in spec.params if not p.required
    ]
    for p in spec.params:
        keywordOnly = parameters[p.name].kind is inspect.Parameter.KEYWORD_ONLY
        assert keywordOnly is (not p.required), p.name


def test_every_order_type_is_exported():
    for spec in SPECS:
        assert getattr(ib_async, spec.className) is getattr(ordertypes, spec.className)


def test_market_on_close_issue_14():
    order = MarketOnCloseOrder("SELL", 100)
    assert (order.orderType, order.action, order.totalQuantity) == (
        "MOC",
        "SELL",
        Decimal(100),
    )


def test_snap_to_midpoint_issue_109():
    order = SnapToMidpointOrder("BUY", 1, 50.00, offset=0.25, tif="DAY")
    assert (order.orderType, order.lmtPrice, order.auxPrice, order.tif) == (
        "SNAP MID",
        Decimal(50),
        Decimal("0.25"),
        "DAY",
    )


def test_other_order_fields_pass_through():
    order = MarketOnCloseOrder("SELL", 100, account="DU1", outsideRth=False)
    assert order.account == "DU1"


def test_a_missing_required_value_is_refused():
    with pytest.raises(OrderTypeError, match="needs priceCap"):
        ib_async.MidpriceOrder("BUY", 100, None)


def test_exactly_one_of_a_pair():
    with pytest.raises(OrderTypeError, match="exactly one of"):
        TrailingStopOrder("SELL", 100)
    with pytest.raises(OrderTypeError, match="exactly one of"):
        TrailingStopOrder("SELL", 100, trailingAmount=1, trailingPercent=2)
    order = TrailingStopOrder("SELL", 100, trailingAmount=1)
    assert (order.auxPrice, order.trailingPercent) == (Decimal(1), None)


def test_fields_the_type_sets_cannot_be_overridden():
    with pytest.raises(
        OrderTypeError, match=r"cannot also take tif \(Limit on Open sets it\)"
    ):
        LimitOnOpenOrder("BUY", 100, 50, tif="DAY")
    with pytest.raises(
        OrderTypeError, match=r"cannot also take orderType \(Market on Close sets it\)"
    ):
        MarketOnCloseOrder("BUY", 100, orderType="MKT")
    # stopPrice is the auxPrice field: setting both would be ambiguous
    with pytest.raises(
        OrderTypeError,
        match=r"cannot also take auxPrice \(its parameter stopPrice sets it\)",
    ):
        ib_async.StopOrder("SELL", 100, 45, auxPrice=44)


def test_spec_of_tells_apart_types_sharing_a_code():
    assert specOf(PegMidOrder("BUY", 100, 50)).className == "PegMidOrder"
    plain = PeggedToMidpointOrder("BUY", 100, 50)
    assert specOf(plain).className == "PeggedToMidpointOrder"
    assert specOf(Order(orderType="LMT", lmtPrice=1, tif="OPG")).className == (
        "LimitOnOpenOrder"
    )
    assert specOf(Order(orderType="XYZ")) is None


def test_orders_replace_and_copy_like_any_order():
    order = ib_async.StopOrder("SELL", 100, 45)
    moved = dataclasses.replace(order, auxPrice=Decimal(44))
    assert (moved.orderType, moved.auxPrice) == ("STP", Decimal(44))


def test_check_order_names_unlisted_products_and_exchanges():
    stock = Stock("SPY", "SMART", "USD")
    assert checkOrder(stock, MarketOnCloseOrder("SELL", 100)) == []
    option = Option("SPY", "20261218", 600, "C", "SMART")
    assert checkOrder(option, MarketOnCloseOrder("SELL", 1)) == [
        "Market on Close is documented for CFD, FUT, STK, WAR, not OPT"
    ]
    future = Future("ES", "202612", "CME")
    problems = checkOrder(future, ib_async.BoxTopOrder("BUY", 1))
    assert problems == [
        "Box Top is documented for OPT, not FUT",
        "Box Top is offered on BOX, not CME",
    ]
    assert checkOrder(stock, Order(orderType="XYZ")) == []


# --- algos -------------------------------------------------------------------

ALGO_SPECS = list(ordertypes.ALGOS)


def algoExample(spec):
    return eval(f"{spec.className}({spec.example})", vars(ib_async))


@pytest.mark.parametrize("spec", ALGO_SPECS, ids=lambda s: s.className)
def test_algo_example_works_an_order_it_lists(spec):
    algo = algoExample(spec)
    base = LimitOrder if "LMT" in spec.orderTypes else ib_async.MarketOrder
    args = ("BUY", 100, 50) if base is LimitOrder else ("BUY", 100)
    order = base(*args, algo=algo)
    assert order.algoStrategy == spec.strategy
    assert order.algoParams == list(algo.params)
    assert ordertypes.algoOf(order) is spec


def test_adaptive_as_live_trading_sends_it():
    """An urgent adaptive limit order and a patient adaptive market order."""
    fast = LimitOrder("BUY", 100, 50, tif="DAY", algo=Adaptive(priority="Urgent"))
    assert (fast.orderType, fast.algoStrategy, fast.algoParams) == (
        "LMT",
        "Adaptive",
        [TagValue("adaptivePriority", "Urgent")],
    )
    slow = ib_async.MarketOrder("SELL", 100, algo=Adaptive(priority="Patient"))
    assert slow.algoParams == [TagValue("adaptivePriority", "Patient")]
    assert specOf(slow).className == "MarketOrder"


def test_an_algo_only_works_the_order_types_it_lists():
    with pytest.raises(
        OrderTypeError, match="Adaptive works LMT, MKT orders, not Stop"
    ):
        ib_async.StopOrder("SELL", 100, 45, algo=Adaptive(priority="Urgent"))
    with pytest.raises(OrderTypeError, match="works LMT orders"):
        ib_async.MarketOrder("BUY", 100, algo=ib_async.DarkIce(displaySize=100))


def test_adaptive_conditions():
    with pytest.raises(OrderTypeError, match="needs tif"):
        LimitOrder("BUY", 100, 50, tif="GTC", algo=Adaptive())
    with pytest.raises(OrderTypeError, match="needs outsideRth"):
        LimitOrder("BUY", 100, 50, outsideRth=True, algo=Adaptive())


def test_algo_values_are_checked_and_encoded():
    with pytest.raises(
        OrderTypeError, match="priority is one of Urgent, Normal, Patient"
    ):
        Adaptive(priority="Fast")
    vwap = ib_async.Vwap(maxPctVol=0.1, noTakeLiq=True, speedUp=False)
    assert vwap.params == (
        TagValue("maxPctVol", "0.1"),
        TagValue("noTakeLiq", "1"),
        TagValue("speedUp", "0"),
    )


def test_an_algo_and_algo_fields_together_are_refused():
    with pytest.raises(OrderTypeError, match=r"algoStrategy \(Adaptive sets it\)"):
        LimitOrder("BUY", 100, 50, algo=Adaptive(), algoStrategy="Vwap")


# --- combos ------------------------------------------------------------------


def test_combo_leg_prices():
    order = ib_async.ComboLegPricesOrder("BUY", 1, [2.50, "1.20"])
    assert order.orderType == "LMT"
    assert order.lmtPrice is None
    assert [leg.price for leg in order.orderComboLegs] == [
        Decimal("2.5"),
        Decimal("1.20"),
    ]
    assert specOf(order).className == "ComboLegPricesOrder"


def test_combo_routing_as_an_application_sends_it():
    """NonGuaranteed=1, LeginPrio=0, DontLeginNext=1, as live trading sends combos."""
    routing = ib_async.ComboRouting(
        nonGuaranteed=True, legInPriority=0, dontLegInNext=True
    )
    order = LimitOrder("BUY", 1, -0.35, routing=routing)
    assert order.smartComboRoutingParams == [
        TagValue("NonGuaranteed", "1"),
        TagValue("LeginPrio", "0"),
        TagValue("DontLeginNext", "1"),
    ]
    assert ib_async.ComboRouting().params == ()


def test_combo_routing_and_its_field_together_are_refused():
    with pytest.raises(
        OrderTypeError, match=r"smartComboRoutingParams \(Combo routing sets it\)"
    ):
        LimitOrder(
            "BUY",
            1,
            2.5,
            routing=ib_async.ComboRouting(nonGuaranteed=True),
            smartComboRoutingParams=[],
        )


def test_relative_combo_codes():
    assert ib_async.RelativeLimitComboOrder("BUY", 1, 2.5).orderType == "REL + LMT"
    assert ib_async.RelativeMarketComboOrder("BUY", 1).orderType == "REL + MKT"


def test_check_order_names_combo_routing_off_a_combo_and_algo_products():
    stock = Stock("SPY", "SMART", "USD")
    routed = LimitOrder(
        "BUY", 1, 2.5, routing=ib_async.ComboRouting(nonGuaranteed=True)
    )
    assert checkOrder(stock, routed) == [
        "combo routing applies to combo (BAG) contracts, not STK"
    ]
    combo = ib_async.Bag(symbol="SPY", exchange="SMART", currency="USD")
    assert checkOrder(combo, routed) == []
    minImpact = LimitOrder("BUY", 1, 2.5, algo=ib_async.MinimiseImpact())
    assert checkOrder(stock, minImpact) == [
        "Minimise Impact is documented for OPT, not STK"
    ]


def test_check_order_names_a_combo_only_type_off_a_combo():
    stock = Stock("SPY", "SMART", "USD")
    assert checkOrder(stock, ib_async.RelativeMarketComboOrder("BUY", 1)) == [
        "Relative + Market (combo) is documented for BAG, not STK"
    ]


# --- options, attached orders, IBKR's codes ------------------------------------


@pytest.mark.parametrize("option", ordertypes.OPTIONS, ids=lambda o: o.title)
def test_option_fields_exist_and_its_example_builds(option):
    fields = {f.name for f in dataclasses.fields(Order)}
    assert set(option.fields) <= fields
    order = eval(option.example, vars(ib_async))
    assert type(order) is Order
    assert any(getattr(order, f) not in (None, "", 0, False, []) for f in option.fields)


def test_every_ibkr_code_is_built_or_explained():
    built = {spec.orderType for spec in CATALOG}
    codes = set(ordertypes.IBKR_ORDER_TYPES)
    assert built <= codes
    assert set(ordertypes.NOT_BUILT) == codes - built


def test_adjustable_stops():
    stop = ib_async.StopOrder(
        "SELL",
        100,
        45,
        parentId=7,
        adjust=ordertypes.AdjustToStopLimit(55, 50, "49.50"),
    )
    assert (
        stop.adjustedOrderType,
        stop.triggerPrice,
        stop.adjustedStopPrice,
        stop.adjustedStopLimitPrice,
    ) == ("STP LMT", Decimal(55), Decimal(50), Decimal("49.50"))
    trail = ib_async.StopOrder(
        "SELL", 100, 45, adjust=ordertypes.AdjustToTrail(55, 50, trailingPercent=2)
    )
    assert (trail.adjustedTrailingAmount, trail.adjustableTrailingUnit) == (
        Decimal(2),
        ordertypes.attached.TRAIL_BY_PERCENT,
    )
    with pytest.raises(OrderTypeError, match="exactly one of"):
        ordertypes.AdjustToTrail(55, 50)
    with pytest.raises(OrderTypeError, match="works STP, STP LMT, TRAIL"):
        LimitOrder("SELL", 100, 55, adjust=ordertypes.AdjustToStop(55, 50))
    with pytest.raises(
        OrderTypeError, match=r"triggerPrice \(Adjust to stop sets it\)"
    ):
        ib_async.StopOrder(
            "SELL", 100, 45, triggerPrice=1, adjust=ordertypes.AdjustToStop(55, 50)
        )


def test_fx_hedge_attaches_to_its_parent():
    parent = LimitOrder("BUY", 100, 50, orderId=12, transmit=False)
    hedge = ordertypes.FxHedgeOrder(parent, "BUY")
    assert (hedge.orderType, hedge.totalQuantity, hedge.parentId, hedge.hedgeType) == (
        "MKT",
        Decimal(0),
        12,
        "F",
    )
    with pytest.raises(OrderTypeError, match="parent's orderId"):
        ordertypes.FxHedgeOrder(LimitOrder("BUY", 100, 50), "BUY")


def test_ibkr_ats_variants_are_told_apart():
    upToMid = ib_async.PegBestUpToMidOrder("BUY", 100, 50, 100, 100, 0.01, 0.005)
    assert upToMid.competeAgainstBestOffset == math.inf
    assert specOf(upToMid).className == "PegBestUpToMidOrder"
    best = ib_async.PegBestOrder("BUY", 100, 50, 100, 100, 0.01)
    assert specOf(best).className == "PegBestOrder"
    assert specOf(ib_async.IbkrAtsLimitOrder("BUY", 100, 50)).className == (
        "IbkrAtsLimitOrder"
    )
    assert specOf(LimitOrder("BUY", 100, 50)).className == "LimitOrder"


def test_an_order_is_no_type_whose_constructor_refuses_its_values():
    """An up-to-mid order without its midpoint offsets is not a Pegged to
    Best order, whose competeAgainstBestOffset is finite: it is no type."""
    upToMid = ib_async.PegBestUpToMidOrder("BUY", 100, 50, 100, 100, 0.01, 0.005)
    incomplete = dataclasses.replace(
        upToMid, midOffsetAtWhole=None, midOffsetAtHalf=None
    )
    assert ordertypes.specsOf(incomplete) == []
    assert specOf(incomplete) is None


# --- modification and contract details --------------------------------------

# ContractDetails.orderTypes of an NVDA option, as TWS sent it.
NVDA_OPTION_ORDER_TYPES = (
    "ACTIVETIM,AD,ADJUST,ALERT,ALGO,ALLOC,AON,AVGCOST,BASKET,COND,CONDORDER,"
    "DAY,DEACT,DEACTDIS,DEACTEOD,DIS,FOK,GAT,GTC,GTD,GTT,HID,ICE,IOC,LIT,LMT,"
    "MIT,MKT,MTL,NGCOMB,NONALGO,OCA,OPENCLOSE,PAON,PEGMIDVOL,PEGMKTVOL,"
    "PEGPRMVOL,PEGSRFVOL,POSTONLY,PRICECHK,REL,RELPCTOFS,RELSTK,SCALE,"
    "SCALERST,SIZECHK,SMARTSTG,SNAPMID,SNAPMKT,SNAPREL,STP,STPLMT,TRAIL,"
    "TRAILLIT,TRAILLMT,TRAILMIT,VOLAT,WHATIF"
)


def optionDetails(orderTypes=NVDA_OPTION_ORDER_TYPES):
    contract = Option("NVDA", "20261218", 200, "C", "SMART")
    return ib_async.ContractDetails(contract=contract, orderTypes=orderTypes)


def test_check_order_against_listed_order_types():
    details = optionDetails()
    assert checkOrder(details, LimitOrder("BUY", 1, 2.5)) == []
    # listed under other spellings: SNAPREL, STPLMT, VOLAT
    snap = ib_async.SnapToPrimaryOrder("BUY", 1, 2.5, offset=0.05)
    assert checkOrder(details, snap) == []
    assert checkOrder(details, ib_async.StopLimitOrder("SELL", 1, 2, 2.1)) == []
    assert checkOrder(details, LimitOrder("BUY", 1, 2.5, algo=Adaptive())) == []
    assert checkOrder(details, ib_async.MidpriceOrder("BUY", 1, 2.5)) == [
        "Midprice is documented for STK, not OPT",
        "the contract's order types do not list MIDPRICE",
    ]


def test_check_order_on_an_order_read_back_from_tws():
    """The fields TWS fills in on a live order (from a reported read-back of
    a trailing stop limit) are not mistaken for things the order uses."""
    readBackOrder = Order(
        action="SELL",
        totalQuantity=9,
        orderType="TRAIL LIMIT",
        lmtPrice=280.76,
        auxPrice=5.0,
        tif="GTC",
        ocaType=3,
        displaySize=2112345647,
        trailStopPrice=281.65,
        deltaNeutralOrderType="None",
        clearingIntent="IB",
        adjustedOrderType="None",
        lmtPriceOffset=0.89,
        dontUseAutoPriceForHedge=True,
    )
    assert checkOrder(optionDetails("LMT,TRAILLMT"), readBackOrder) == []


def test_check_order_with_no_listed_order_types_says_nothing_extra():
    midprice = ib_async.MidpriceOrder("BUY", 1, 2.5)
    assert checkOrder(optionDetails(""), midprice) == [
        "Midprice is documented for STK, not OPT"
    ]
    assert checkOrder(ib_async.ContractDetails(), LimitOrder("BUY", 1, 2.5)) == []


def readBack(**fields):
    """An order as TWS reports a live one: fields it filled in included."""
    order = Order(
        orderId=5,
        parentId=4,
        action="BUY",
        totalQuantity=Decimal(100),
        filledQuantity=Decimal(40),
        lmtPrice=Decimal(50),
        transmit=False,
        volatility=Decimal("0.3"),
        volatilityType=2,
        trailStopPrice=Decimal(49),
        clearingIntent="IB",
        displaySize=100,
        dontUseAutoPriceForHedge=True,
        deltaNeutralOrderType="None",
        adjustedOrderType="None",
    )
    return dataclasses.replace(order, **fields)


def test_modified_order_clears_what_tws_fills_in():
    live = readBack(orderType="LMT")
    order = ordertypes.modifiedOrder(live, lmtPrice=50.1)
    assert (order.orderId, order.parentId, order.transmit) == (5, 0, True)
    kept = ordertypes.modifiedOrder(live, preserveParentId=True)
    assert kept.parentId == 4
    assert order.lmtPrice == Decimal("50.1")
    for name in ordertypes.SERVER_FILLED:
        assert getattr(order, name) == getattr(Order(), name), name
    assert order.volatility is None
    assert live.lmtPrice == Decimal(50)  # the original is untouched


def test_modified_order_keeps_what_the_change_sets():
    order = ordertypes.modifiedOrder(readBack(orderType="LMT"), displaySize=10)
    assert order.displaySize == 10
    vol = ordertypes.modifiedOrder(readBack(orderType="VOL"))
    pegVol = ordertypes.modifiedOrder(readBack(orderType="PEG MID VOL"))
    assert pegVol.volatility == Decimal("0.3")
    assert vol.volatility == Decimal("0.3")


def test_modified_order_sends_an_algo_order_as_a_limit_order():
    assert ordertypes.modifiedOrder(readBack(orderType="IBALGO")).orderType == "LMT"
    market = readBack(orderType="IBALGO", lmtPrice=None)
    assert ordertypes.modifiedOrder(market).orderType == "LMT"


def test_modified_order_refuses_a_quantity_below_filled():
    with pytest.raises(OrderTypeError, match="below the 40 already filled"):
        ordertypes.modifiedOrder(readBack(orderType="LMT"), totalQuantity=30)
    assert ordertypes.modifiedOrder(
        readBack(orderType="LMT"), totalQuantity=40
    ).totalQuantity == Decimal(40)


def test_generated_docs_have_no_empty_cells_or_trailing_space():
    page = Path(__file__).parent.parent / "docs" / "ordertypes.rst"
    lines = page.read_text().splitlines()
    for number, line in enumerate(lines, 1):
        assert line == line.rstrip(), f"trailing whitespace on line {number}"
        assert line.strip() not in ("-", "* -"), f"empty table cell on line {number}"
    for number, (line, following) in enumerate(itertools.pairwise(lines), 1):
        assert line or following, f"two blank lines at line {number}"
    # a heading is a line underlined by one repeated character of its length
    headings = [
        text
        for text, under in itertools.pairwise(lines)
        if text
        and len(set(under)) == 1
        and under[0] in "=-^"
        and len(under) == len(text)
    ]
    duplicates = {h for h in headings if headings.count(h) > 1}
    assert not duplicates, f"headings appear twice: {duplicates}"


# --- the design holds together -----------------------------------------------


def test_a_zero_price_is_a_price():
    """Unset is the Order default (None), not every falsy value."""
    assert specOf(LimitOrder("BUY", 1, 0)).className == "LimitOrder"


def test_an_algo_order_read_back_is_its_base_type():
    readBack = Order(orderType="IBALGO", lmtPrice=50, algoStrategy="Adaptive")
    assert specOf(readBack).className == "LimitOrder"
    assert checkOrder(optionDetails("LMT,ALGO"), readBack) == []
    assert checkOrder(optionDetails("MKT,ALGO"), readBack) == [
        "the contract's order types do not list LMT"
    ]


def test_tag_values_are_checked_against_their_kind():
    with pytest.raises(
        OrderTypeError, match="maxPctVol must be a finite number, not 'lots'"
    ):
        ib_async.Vwap(maxPctVol="lots")
    with pytest.raises(
        OrderTypeError, match="legInPriority must be a whole number, not True"
    ):
        ib_async.ComboRouting(legInPriority=True)
    with pytest.raises(OrderTypeError, match="displaySize must be a whole number"):
        ib_async.DarkIce(displaySize=10.5)
    assert ib_async.DarkIce(displaySize=100.0).params[0].value == "100"
    with pytest.raises(OrderTypeError, match="noTakeLiq must be a bool, not 1"):
        ib_async.Vwap(noTakeLiq=1)
    assert ib_async.Vwap(maxPctVol=Decimal("0.2")).params == (
        TagValue("maxPctVol", "0.2"),
    )


def test_params_validate_themselves():
    with pytest.raises(ValueError, match="a tag needs a tag kind"):
        ordertypes.Param("x", "algoParams", "doc", tag="x")
    with pytest.raises(ValueError, match="a tag needs a tag kind"):
        ordertypes.Param("x", "lmtPrice", "doc", kind=ordertypes.spec.Kind.INT)
    with pytest.raises(ValueError, match="Order has no field lmtPirce"):
        ordertypes.Param("x", "lmtPirce", "doc")


def test_the_package_exports_constructors_not_the_catalog():
    for name in ("Param", "Stability", "CATALOG", "OPTIONS", "SERVER_FILLED"):
        assert not hasattr(ib_async, name), name
        assert hasattr(ordertypes, name), name
    for name in (
        "LimitOrder",
        "Adaptive",
        "ComboRouting",
        "AdjustToTrail",
        "FxHedgeOrder",
    ):
        assert name in ib_async.__all__, name


def test_the_catalog_refers_only_to_what_exists():
    fields = ordertypes.spec.ORDER_DEFAULTS
    codes = ordertypes.IBKR_ORDER_TYPES
    names = [s.className for s in (*CATALOG, *ordertypes.ALGOS)] + ["ComboRouting"]
    assert len(names) == len(set(names)), "a constructor name is used twice"
    for spec in CATALOG:
        assert spec.orderType in codes, spec.className
        assert {d.field for d in spec.defining} <= set(fields), spec.className
        optional = {p.name for p in spec.params if not p.required}
        for group in spec.exactlyOne:
            assert set(group) <= optional, spec.className
    for algo in ordertypes.ALGOS:
        assert set(algo.orderTypes) <= set(codes), algo.className
        assert {c.field for c in algo.conditions} <= set(fields), algo.className
        assert all(p.field == "algoParams" for p in algo.params), algo.className
    assert set(ordertypes.spec.ADJUSTABLE) <= set(codes)
    assert set(ordertypes.SERVER_FILLED) <= set(fields)


def test_trailing_stop_limit_takes_a_limit_price_or_an_offset():
    byOffset = ib_async.TrailingStopLimitOrder(
        "SELL", 100, lmtPriceOffset=0.1, trailingAmount=1
    )
    assert (byOffset.lmtPriceOffset, byOffset.lmtPrice) == (Decimal("0.1"), None)
    byPrice = ib_async.TrailingStopLimitOrder(
        "SELL", 100, lmtPrice=44, trailingAmount=1
    )
    assert byPrice.lmtPrice == Decimal(44)
    with pytest.raises(OrderTypeError, match="exactly one of lmtPriceOffset, lmtPrice"):
        ib_async.TrailingStopLimitOrder(
            "SELL", 100, lmtPrice=44, lmtPriceOffset=0.1, trailingAmount=1
        )


def test_algos_work_only_the_order_types_shown_working():
    with pytest.raises(OrderTypeError, match="VWAP works LMT orders"):
        ib_async.MarketOrder("BUY", 100, algo=ib_async.Vwap())
    relative = ib_async.RelativeOrder(
        "BUY", 100, 0.01, 50, algo=ib_async.AccumulateDistribute(componentSize=10)
    )
    assert relative.algoStrategy == "AD"
    with pytest.raises(OrderTypeError, match="Dark Ice needs tif"):
        LimitOrder("BUY", 100, 50, tif="GTC", algo=ib_async.DarkIce(displaySize=10))


def test_check_order_knows_the_midprice_spelling_contract_details_use():
    stock = ib_async.ContractDetails(
        contract=Stock("SPY", "SMART", "USD"), orderTypes="LMT,MIDPX"
    )
    assert checkOrder(stock, ib_async.MidpriceOrder("BUY", 1, 500)) == []


def test_leg_prices_are_finite_decimals_one_per_leg():
    order = ib_async.ComboLegPricesOrder("BUY", 1, [2.5, "1.2", Decimal(3)])
    assert [leg.price for leg in order.orderComboLegs] == [
        Decimal("2.5"),
        Decimal("1.2"),
        Decimal(3),
    ]
    # a single price, or a string of one, is not a list of them
    for given in (2.5, "2.5"):
        with pytest.raises(OrderTypeError, match="a list of prices, one per leg"):
            ib_async.ComboLegPricesOrder("BUY", 1, given)
    legs = ib_async.ComboLegPricesOrder("BUY", 1, (2.5, 1.2))
    assert [leg.price for leg in legs.orderComboLegs] == [
        Decimal("2.5"),
        Decimal("1.2"),
    ]
    with pytest.raises(OrderTypeError, match=r"legPrices\[1\] must be a finite number"):
        ib_async.ComboLegPricesOrder("BUY", 1, [2.5, None])
    with pytest.raises(OrderTypeError, match=r"legPrices\[0\] must be a finite number"):
        ib_async.ComboLegPricesOrder("BUY", 1, [math.nan])


def test_a_float_tag_value_is_a_finite_number():
    param = Param("x", "algoParams", "A float.", tag="x", kind=Kind.FLOAT)
    assert param.encode("X", 1.5) == "1.5"
    for value in (math.nan, math.inf, Decimal("Infinity")):
        with pytest.raises(OrderTypeError, match="finite"):
            param.encode("X", value)


def test_a_field_at_its_unset_default_is_not_given():
    tif = Param("tif", "tif", "The time in force.")
    assert not tif.given(None)
    assert not tif.given("")
    assert tif.given("DAY")
    # 0 is a price where the field's unset value is None
    assert Param("lmtPrice", "lmtPrice", "A price.").given(0)


def test_a_modifier_cannot_set_the_order_types_own_fields():
    stomp = Adjustment("Stomp", (FieldValue("auxPrice", Decimal(1)),))
    with pytest.raises(
        OrderTypeError,
        match=r"Stomp cannot also set auxPrice \(its parameter stopPrice sets it\)",
    ):
        ib_async.StopOrder("SELL", 100, 45, adjust=stomp)


def test_adjustments_need_their_prices():
    with pytest.raises(OrderTypeError, match="needs triggerPrice"):
        ordertypes.AdjustToStop(None, 50)  # type: ignore[arg-type]
    with pytest.raises(OrderTypeError, match="needs limitPrice"):
        ordertypes.AdjustToStopLimit(55, 50, None)  # type: ignore[arg-type]


def test_an_fx_hedge_sets_its_parent_and_hedge_type_itself():
    parent = LimitOrder("BUY", 100, 50.00, orderId=7, transmit=False)
    hedge = ordertypes.FxHedgeOrder(parent, "BUY")
    assert (hedge.parentId, hedge.hedgeType) == (7, "F")
    with pytest.raises(OrderTypeError, match="sets hedgeType itself"):
        ordertypes.FxHedgeOrder(parent, "BUY", hedgeType="D")


def test_check_order_checks_a_type_missing_a_required_value():
    # No priceCap: not quite a MidpriceOrder, still a midprice order.
    order = Order(orderType="MIDPRICE", action="BUY", totalQuantity=Decimal(1))
    assert specOf(order) is None
    problems = checkOrder(Future("ES", exchange="CME"), order)
    assert any("documented for STK" in p for p in problems), problems


def test_a_catalog_mistake_fails_when_it_is_defined():
    with pytest.raises(ValueError, match="no field nope"):
        OrderTypeSpec(
            "X", "X", "X", "X", Stability.STABLE, defining=(FieldValue("nope", 1),)
        )
    with pytest.raises(ValueError, match="not all optional"):
        OrderTypeSpec(
            "X",
            "X",
            "X",
            "X",
            Stability.STABLE,
            params=(Param("lmtPrice", "lmtPrice", "A price."),),
            exactlyOne=(("lmtPrice",),),
        )
    with pytest.raises(ValueError, match="no field nope"):
        AlgoSpec(
            "X",
            "X",
            "X",
            "X",
            Stability.STABLE,
            ("LMT",),
            conditions=(FieldIn("nope", ()),),
        )


def test_order_defaults_are_read_only():
    with pytest.raises(TypeError):
        ORDER_DEFAULTS["lmtPrice"] = 1  # type: ignore[index]


def test_modified_order_shares_no_lists_with_the_live_order():
    live = readBack(orderType="LMT", algoParams=[TagValue("a", "1")])
    order = ordertypes.modifiedOrder(live)
    order.algoParams.append(TagValue("b", "2"))
    assert live.algoParams == [TagValue("a", "1")]


def test_a_subclass_of_order_shows_its_order_type():
    class Mine(Order):
        pass

    assert "orderType='LMT'" in repr(Mine(orderType="LMT"))


@pytest.mark.parametrize(
    "make",
    [
        lambda: LimitOrder("BUY", 100, math.nan),
        lambda: LimitOrder("BUY", 100, math.inf),
        lambda: LimitOrder("BUY", 100, ""),
        lambda: LimitOrder("BUY", 100, "abc"),
        lambda: ib_async.StopOrder("SELL", 100, Decimal("NaN")),
        lambda: TrailingStopOrder("SELL", 100, trailingPercent=math.nan),
        lambda: ib_async.MarketOrder("BUY", math.nan),
        lambda: ib_async.MarketOrder("BUY", None),
        # infinity is Pegged to Best up to Midpoint's own value, not a price
        lambda: ib_async.PegBestOrder("BUY", 100, 50, 100, 100, math.inf),
        lambda: LimitOrder("BUY", 100, 50, trailStopPrice=math.nan),
        lambda: ordertypes.AdjustToStop(math.nan, 50),
    ],
)
def test_a_value_the_order_would_silently_unset_is_refused(make):
    with pytest.raises(OrderTypeError, match="must be a"):
        make()


def test_an_adjustment_holds_decimals():
    adjust = ordertypes.AdjustToStopLimit(55, "50", 49.5)
    assert adjust.orderFields == {
        "adjustedOrderType": "STP LMT",
        "triggerPrice": Decimal(55),
        "adjustedStopPrice": Decimal(50),
        "adjustedStopLimitPrice": Decimal("49.5"),
    }


def test_leg_prices_need_a_price_per_leg():
    with pytest.raises(OrderTypeError, match="needs a price per leg"):
        ib_async.ComboLegPricesOrder("BUY", 1, [])


def test_an_action_ibkr_does_not_take_is_refused():
    with pytest.raises(OrderTypeError, match="action is one of"):
        LimitOrder("BYU", 1, 50)
    assert LimitOrder("SSHORT", 1, 50).action == "SSHORT"


def test_an_order_combining_types_is_each_of_them():
    order = ib_async.IbkrAtsLimitOrder("BUY", 1, 50, tif="OPG")
    names = {spec.className for spec in ordertypes.specsOf(order)}
    assert names == {"IbkrAtsLimitOrder", "LimitOnOpenOrder"}
    assert specOf(order) is None
    problems = checkOrder(Stock("X", "SMART", "USD"), order)
    assert any("offered on IBKRATS, not SMART" in p for p in problems), problems


def test_modified_order_refuses_changes_its_rules_override():
    live = readBack(orderType="LMT")
    for changes in ({"parentId": 7}, {"transmit": False}):
        with pytest.raises(OrderTypeError, match="sets .* itself"):
            ordertypes.modifiedOrder(live, **changes)
    with pytest.raises(OrderTypeError, match="takes no volatility"):
        ordertypes.modifiedOrder(live, volatility=30)
    vol = ordertypes.modifiedOrder(readBack(orderType="VOL"), volatility=30)
    assert vol.volatility == Decimal(30)


def test_catalog_entries_check_their_parameters():
    price = Param("lmtPrice", "lmtPrice", "A price.")
    with pytest.raises(ValueError, match="fields given twice: lmtPrice"):
        OrderTypeSpec(
            "X",
            "X",
            "X",
            "X",
            Stability.STABLE,
            params=(price, dataclasses.replace(price, name="other")),
        )
    with pytest.raises(ValueError, match="not tag values of algoParams"):
        AlgoSpec("X", "X", "X", "X", Stability.STABLE, ("LMT",), params=(price,))


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: ib_async.DiscretionaryOrder("BUY", 100, 50, math.nan), "finite"),
        (lambda: ib_async.DiscretionaryOrder("BUY", 100, 50, "0.05"), "finite number"),
        (lambda: ib_async.PegBestOrder("BUY", 100, 50, 100.5, 100, 0.01), "whole"),
        (lambda: LimitOrder("BUY", 100, 50, minQty=math.nan), "whole"),
        (lambda: LimitOrder("BUY", 100, 50, displaySize="x"), "whole"),
    ],
)
def test_every_numeric_field_takes_only_its_kind_of_number(make, message):
    with pytest.raises(OrderTypeError, match=message):
        make()


def test_a_float_field_holds_a_float():
    order = ib_async.DiscretionaryOrder("BUY", 100, 50, Decimal("0.05"))
    assert order.discretionaryAmt == 0.05


def test_modified_order_refuses_a_change_its_field_cannot_hold():
    live = readBack(orderType="LMT")
    for changes in (
        {"lmtPrice": math.nan},
        {"lmtPrice": "50.1O"},
        {"totalQuantity": "abc"},
    ):
        with pytest.raises(OrderTypeError, match="must be a finite number"):
            ordertypes.modifiedOrder(live, **changes)


def test_a_field_set_by_a_modifier_names_the_modifier():
    with pytest.raises(OrderTypeError, match=r"algoParams \(Adaptive sets it\)"):
        LimitOrder("BUY", 1, 50, algo=Adaptive(), algoParams=[])


def test_an_order_type_cannot_redefine_what_build_sets():
    with pytest.raises(ValueError, match="build sets orderType"):
        OrderTypeSpec(
            "X",
            "X",
            "LMT",
            "X",
            Stability.STABLE,
            defining=(FieldValue("orderType", "MKT"),),
        )
    with pytest.raises(ValueError, match="build sets totalQuantity"):
        OrderTypeSpec(
            "X",
            "X",
            "LMT",
            "X",
            Stability.STABLE,
            params=(Param("q", "totalQuantity", "Q."),),
        )


def test_numbers_are_recognized_by_kind():
    """A whole-valued float or Decimal is a whole number, taken exactly; a
    Decimal is a float field's or a float tag's finite number."""
    order = ib_async.PegBestOrder("BUY", 100, 50, 100.0, Decimal(100), 0.01)
    assert (order.minTradeQty, order.minCompeteSize) == (100, 100)
    assert ib_async.VolatilityOrder("BUY", 1, 25, 2.0).volatilityType == 2
    assert ib_async.ComboRouting(legInPriority=0.0).params == (
        TagValue("LeginPrio", "0"),
    )
    algo = ib_async.AccumulateDistribute(componentSize=Decimal(2**53 + 1))
    assert TagValue("componentSize", str(2**53 + 1)) in algo.params
    assert ib_async.Vwap(maxPctVol=Decimal("0.25")).params == (
        TagValue("maxPctVol", "0.25"),
    )


def test_numpy_numbers_are_numbers():
    np = pytest.importorskip("numpy")
    order = LimitOrder("BUY", np.int64(100), np.float64(50.5), displaySize=np.int64(10))
    assert order.displaySize == 10 and type(order.displaySize) is int
    discretionary = ib_async.DiscretionaryOrder("BUY", 100, 50, np.int64(1))
    assert discretionary.discretionaryAmt == 1.0


def test_infinity_is_named_where_it_is_allowed():
    with pytest.raises(
        OrderTypeError, match="lmtPrice must be a finite number, not inf"
    ):
        LimitOrder("BUY", 100, math.inf)
    with pytest.raises(OrderTypeError, match=r"a finite number or \+Infinity"):
        LimitOrder("BUY", 100, 50, competeAgainstBestOffset="lots")
    order = LimitOrder("BUY", 100, 50, competeAgainstBestOffset=math.inf)
    assert order.competeAgainstBestOffset == Decimal("Infinity")


def test_a_modifier_clash_names_whoever_set_the_field():
    hand = Adjustment("Hand adjust", (FieldValue("smartComboRoutingParams", []),))
    with pytest.raises(
        OrderTypeError,
        match=r"Hand adjust cannot also set smartComboRoutingParams "
        r"\(Combo routing sets it\)",
    ):
        ib_async.StopOrder(
            "SELL", 1, 4, routing=ib_async.ComboRouting(nonGuaranteed=True), adjust=hand
        )


def test_none_for_a_field_is_its_unset_value():
    order = LimitOrder("BUY", 1, 1, tif=None, outsideRth=None, algo=Adaptive())
    assert (order.tif, order.outsideRth) == ("", False)
    assert ordertypes.modifiedOrder(readBack(orderType="LMT"), tif=None).tif == ""
    assert not ordertypes.spec.isSet("tif", None)


def test_a_hand_built_adjustment_is_checked_as_any_field():
    hand = Adjustment("Hand adjust", (FieldValue("triggerPrice", math.nan),))
    with pytest.raises(OrderTypeError, match="Hand adjust: triggerPrice must be"):
        ib_async.StopOrder("SELL", 1, 4, adjust=hand)


def test_an_unset_default_is_never_shared():
    a = LimitOrder("BUY", 1, 50, softDollarTier=None)
    b = LimitOrder("BUY", 1, 50, softDollarTier=None)
    assert a.softDollarTier is not b.softDollarTier
    a.softDollarTier.name = "TIER"
    assert b.softDollarTier.name == ""
    assert ORDER_DEFAULTS["softDollarTier"].name == ""


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: LimitOrder("BUY", 1, 50, outsideRth="false"), "True or False"),
        (lambda: LimitOrder("BUY", 1, 50, tif=1), "a string"),
        (
            lambda: ordertypes.modifiedOrder(readBack(orderType="LMT"), hidden="no"),
            "True or False",
        ),
    ],
)
def test_a_bool_or_str_field_takes_only_its_kind(make, message):
    with pytest.raises(OrderTypeError, match=message):
        make()


def test_the_catalog_refuses_a_code_ibkr_does_not_have(monkeypatch):
    typo = dataclasses.replace(catalog.ALGOS[0], orderTypes=("LMT", "MKT "))
    monkeypatch.setattr(catalog, "ALGOS", (typo, *catalog.ALGOS[1:]))
    with pytest.raises(ValueError, match=r"not in IBKR_ORDER_TYPES: \['MKT '\]"):
        catalog._checkCodes()


def test_only_a_string_tag_names_its_allowed_values():
    with pytest.raises(ValueError, match="only string tag values"):
        Param("x", "algoParams", "doc", tag="x", kind=Kind.INT, allowed=("1",))


def test_combo_routing_enforces_a_required_parameter():
    required = Param("x", "smartComboRoutingParams", "doc", tag="X", kind=Kind.BOOL)
    with pytest.raises(OrderTypeError, match="needs x"):
        ordertypes.spec.buildRouting((required,), {})


def test_a_tag_refusal_names_its_constructor():
    with pytest.raises(OrderTypeError, match="^Adaptive: priority is one of"):
        Adaptive(priority="urgent")
