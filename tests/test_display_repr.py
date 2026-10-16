"""Pin the ONE display-repr policy every order-plane object shares.

``ib_async/util.py`` owns the policy: ``dataclassDisplayFields`` decides
which fields carry information, ``dataclassDisplayValue`` decides how one
value prints, and ``dataclassRepr`` / the hand-written ``Order`` /
``Contract`` reprs are the only consumers.

What these tests hold still, because a live session reads these strings
out of its console and its log files:

* no ``None``, no ``''``, no empty list, no ``NaN`` field ever appears;
* no ``Decimal('...')`` wrapper — a price prints as ``29403.25``;
* IBKR's "not applicable" string boilerplate (``adjustedOrderType='None'``,
  ``shareholder='Not an insider or substantial shareholder'``, TWS's
  ``'?'`` placeholder) never appears;
* a zero that IS information — ``remaining=0`` on a filled order — stays.

The expected strings are spelled out in full rather than probed with
``in`` checks: the point of the policy is the WHOLE line, and a field
creeping back in must fail here.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from ib_async.contract import Contract, Forex, Future, Stock
from ib_async.objects import CommissionReport, Execution, Fill, TradeLogEntry
from ib_async.order import Order, OrderStatus, Trade
from ib_async.ordertypes import LimitOrder
from ib_async.util import (
    DISPLAY_BOILERPLATE_STRINGS,
    DISPLAY_KEEP_ZERO_FIELDS,
    dataclassDisplayFields,
    dataclassDisplayValue,
    dataclassNonDefaults,
)

FILL_TIME = dt.datetime(2026, 9, 16, 15, 30, 55, tzinfo=dt.UTC)


def _nqz6() -> Future:
    contract = Future(
        symbol="NQ",
        exchange="CME",
        localSymbol="NQZ6",
        currency="USD",
    )
    contract.conId = 563947726
    return contract


def _limit_order() -> LimitOrder:
    order = LimitOrder("BUY", 1, 29403.25, tif="GTC")
    order.orderId = 10282
    order.clientId = 169
    order.permId = 1275529321
    # The two string sentinels IBKR stamps on an ``openOrder`` decode of
    # effectively every order.
    order.adjustedOrderType = "None"
    order.shareholder = "Not an insider or substantial shareholder"
    return order


def _order_status() -> OrderStatus:
    return OrderStatus(
        orderId=10282,
        status="Filled",
        filled=Decimal(1),
        # Zero IS information here: the order is done, nothing is left.
        remaining=Decimal(0),
        avgFillPrice=Decimal("29403.25"),
        permId=1275529321,
        lastFillPrice=Decimal("29403.25"),
        clientId=169,
    )


def _execution() -> Execution:
    return Execution(
        execId="0000e9b5.68c9f1d2.01.01",
        time=FILL_TIME,
        acctNumber="U1234567",
        exchange="CME",
        side="BOT",
        shares=Decimal(1),
        price=Decimal("29403.25"),
        permId=1275529321,
        clientId=169,
        orderId=10282,
        cumQty=Decimal(1),
        avgPrice=Decimal("29403.25"),
        lastLiquidity=1,
    )


def _commission_report() -> CommissionReport:
    return CommissionReport(
        execId="0000e9b5.68c9f1d2.01.01",
        commissionAndFees=Decimal("2.32"),
        currency="USD",
        realizedPNL=Decimal(0),
    )


def _fill() -> Fill:
    return Fill(
        contract=_nqz6(),
        execution=_execution(),
        commissionReport=_commission_report(),
        time=FILL_TIME,
    )


CONTRACT_REPR = (
    "Future(conId=563947726, symbol='NQ', exchange='CME', "
    "currency='USD', localSymbol='NQZ6')"
)

ORDER_REPR = (
    "Order(orderId=10282, clientId=169, permId=1275529321, "
    "action='BUY', totalQuantity=1, orderType='LMT', lmtPrice=29403.25, tif='GTC')"
)

ORDER_STATUS_REPR = (
    "OrderStatus(orderId=10282, status='Filled', filled=1, remaining=0, "
    "avgFillPrice=29403.25, permId=1275529321, lastFillPrice=29403.25, "
    "clientId=169)"
)

EXECUTION_REPR = (
    "Execution(execId='0000e9b5.68c9f1d2.01.01', "
    "time=datetime.datetime(2026, 9, 16, 15, 30, 55, tzinfo=datetime.timezone.utc), "
    "acctNumber='U1234567', exchange='CME', side='BOT', shares=1, "
    "price=29403.25, permId=1275529321, clientId=169, orderId=10282, "
    "cumQty=1, avgPrice=29403.25, lastLiquidity=1)"
)

COMMISSION_REPORT_REPR = (
    "CommissionReport(execId='0000e9b5.68c9f1d2.01.01', "
    "commissionAndFees=2.32, currency='USD')"
)

FILL_REPR = (
    f"Fill(contract={CONTRACT_REPR}, execution={EXECUTION_REPR}, "
    f"commissionReport={COMMISSION_REPORT_REPR}, "
    "time=datetime.datetime(2026, 9, 16, 15, 30, 55, tzinfo=datetime.timezone.utc))"
)

TRADE_LOG_ENTRY_REPR = (
    "TradeLogEntry("
    "time=datetime.datetime(2026, 9, 16, 15, 30, 55, tzinfo=datetime.timezone.utc), "
    "status='Filled', message='Fill 1@29403.25')"
)


def test_contract_repr_shows_only_the_fields_ibkr_named() -> None:
    assert repr(_nqz6()) == CONTRACT_REPR


def test_order_repr_drops_ibkr_string_boilerplate_and_decimal_wrappers() -> None:
    """``adjustedOrderType='None'`` and the shareholder disclosure are on the
    object, and must not be on the line."""

    order = _limit_order()
    text = repr(order)

    assert text == ORDER_REPR
    assert "adjustedOrderType" not in text
    assert "shareholder" not in text
    assert "Decimal(" not in text


def test_order_status_repr_keeps_a_zero_remaining() -> None:
    text = repr(_order_status())

    assert text == ORDER_STATUS_REPR
    # The generated repr printed all three of these on every status line.
    assert "whyHeld" not in text
    assert "mktCapPrice" not in text
    assert "parentId" not in text


def test_execution_repr_drops_the_ev_and_model_placeholders() -> None:
    text = repr(_execution())

    assert text == EXECUTION_REPR
    for absent in ("evRule", "evMultiplier", "modelCode", "submitter"):
        assert absent not in text


def test_commission_report_repr_drops_a_zero_realized_pnl() -> None:
    """A zero ``realizedPNL`` is not an identity or a quantity, so it is
    dropped; the commission the broker actually charged stays."""

    text = repr(_commission_report())

    assert text == COMMISSION_REPORT_REPR
    assert "yield" not in text


def test_trade_log_entry_repr_drops_a_zero_error_code() -> None:
    entry = TradeLogEntry(time=FILL_TIME, status="Filled", message="Fill 1@29403.25")

    assert repr(entry) == TRADE_LOG_ENTRY_REPR


def test_fill_repr_nests_culled_reprs() -> None:
    assert repr(_fill()) == FILL_REPR


def test_trade_repr_is_one_line_with_no_placeholder_fields() -> None:
    trade = Trade(
        contract=_nqz6(),
        order=_limit_order(),
        orderStatus=_order_status(),
        fills=[_fill()],
        log=[TradeLogEntry(time=FILL_TIME, status="Filled", message="Fill 1@29403.25")],
    )

    text = repr(trade)

    assert text == (
        f"Trade(contract={CONTRACT_REPR}, order={ORDER_REPR}, "
        f"orderStatus={ORDER_STATUS_REPR}, fills=[{FILL_REPR}], "
        f"log=[{TRADE_LOG_ENTRY_REPR}])"
    )
    assert "\n" not in text
    assert "Decimal(" not in text
    assert "=None" not in text
    assert "=''" not in text
    assert "advancedError" not in text
    assert "serverOrder" not in text
    # ``str`` and ``format`` reach the same policy.
    assert f"{trade}" == text


def test_empty_trade_repr_shows_its_three_structural_fields() -> None:
    """A default ``Trade`` still names what it is made of — the three
    structural fields are declared with a ``default_factory``, so there is no
    declared default to compare them against."""

    assert (
        repr(Trade())
        == "Trade(contract=Contract(), order=Order(), orderStatus=OrderStatus())"
    )


def test_nan_and_empty_values_never_print() -> None:
    order = Order(orderId=7)
    order.lmtPrice = Decimal("NaN")
    order.orderRef = ""
    order.orderComboLegs = []

    text = repr(order)

    assert text == "Order(orderId=7)"


def test_boilerplate_string_set_is_dropped_field_by_field() -> None:
    for sentinel in DISPLAY_BOILERPLATE_STRINGS:
        order = Order(orderId=7, orderRef=sentinel)
        assert repr(order) == "Order(orderId=7)", sentinel


def test_keep_zero_fields_survive_a_non_default_zero() -> None:
    """Every keep-zero name that a zero can actually reach on this plane
    prints its zero rather than vanishing."""

    status = OrderStatus(orderId=1, filled=Decimal(0), remaining=Decimal(0))
    assert repr(status) == "OrderStatus(orderId=1, filled=0, remaining=0)"

    execution = Execution(execId="x", shares=Decimal(0), cumQty=Decimal(0))
    assert repr(execution) == "Execution(execId='x', shares=0, cumQty=0)"

    order = Order(orderId=1, totalQuantity=Decimal(0))
    assert repr(order) == "Order(orderId=1, totalQuantity=0)"

    assert {"orderId", "permId", "parentId", "clientId", "conId", "reqId"} <= (
        DISPLAY_KEEP_ZERO_FIELDS
    )


def test_a_zero_price_is_dropped_because_it_is_not_a_quantity() -> None:
    order = Order(orderId=1, lmtPrice=Decimal(0), auxPrice=Decimal(0))

    assert repr(order) == "Order(orderId=1)"


def test_a_flag_that_differs_from_its_default_is_never_read_as_zero() -> None:
    """``transmit`` defaults ``True``; ``False`` is an ``int``-like zero and
    must survive, because a held order is the whole point of the flag."""

    order = Order(orderId=1, transmit=False)

    assert repr(order) == "Order(orderId=1, transmit=False)"


def test_decimal_values_print_plain_everything_else_through_repr() -> None:
    assert dataclassDisplayValue(Decimal("29403.25")) == "29403.25"
    assert dataclassDisplayValue(Decimal(1)) == "1"
    assert dataclassDisplayValue("GTC") == "'GTC'"
    assert dataclassDisplayValue(7) == "7"


def test_non_defaults_policy_is_untouched_for_its_own_callers() -> None:
    """``dataclassNonDefaults`` feeds ``tree`` and is public in ``util``,
    and keeps its own, looser semantics: it does not drop empty strings,
    zeros or IBKR's string boilerplate."""

    order = Order(orderId=1, orderRef="None", lmtPrice=Decimal(0))
    softDollarTier = order.softDollarTier

    assert dataclassNonDefaults(order) == {
        "orderId": 1,
        "orderRef": "None",
        "lmtPrice": Decimal(0),
        # ``default_factory`` fields have no declared default to compare
        # against, so both policies keep them; ``Order.__repr__`` is what
        # drops an empty tier from the line.
        "softDollarTier": softDollarTier,
    }
    assert dataclassDisplayFields(order) == {
        "orderId": 1,
        "softDollarTier": softDollarTier,
    }
    assert "softDollarTier" not in repr(order)


def test_forex_and_stock_reprs_still_read_as_before() -> None:
    assert repr(Forex("EURUSD")) == "Forex('EURUSD', exchange='IDEALPRO')"
    assert repr(Stock("AAPL", "SMART", "USD")) == (
        "Stock(symbol='AAPL', exchange='SMART', currency='USD')"
    )


def test_a_contract_with_a_zero_strike_and_a_real_one() -> None:
    """``strike`` defaults ``0.0``, so a zero strike was already invisible;
    a real strike prints as the plain float it is."""

    assert "strike" not in repr(Contract(secType="OPT", symbol="SPY"))
    assert "strike=470.0" in repr(
        Contract(secType="OPT", symbol="SPY", strike=470.0, right="C")
    )
