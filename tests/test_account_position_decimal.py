"""Decimal-native account / position dataclass migrations.

Negative paths first (garbage Decimal strings, missing wire values,
non-monetary tags), then the happy paths. Covers the v3.0 shifts:

* ``AccountValue`` is now a slotted frozen dataclass with a typed
  ``decimalValue`` property gated by ``MONETARY_ACCOUNT_VALUE_TAGS``.
* ``Position`` / ``PortfolioItem`` / ``Fill`` are slotted frozen
  dataclasses; ``Position.position``, ``Position.avgCost`` and the
  six ``PortfolioItem`` numeric fields are ``Decimal | None``.
* ``OrderState.commission`` / ``minCommission`` / ``maxCommission``
  are ``Decimal | None`` with ``None`` as the unset sentinel.
* ``Wrapper.position`` and ``Wrapper.updatePortfolio`` accept
  ``Decimal | None`` and treat both ``None`` and ``Decimal('0')`` as
  "drop the cached entry".
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from datetime import UTC
from decimal import Decimal

import pytest

import ib_async as ibi
from ib_async.objects import (
    MONETARY_ACCOUNT_VALUE_TAGS,
    AccountValue,
    Execution,
    Fill,
    PortfolioItem,
    Position,
)
from ib_async.order import OrderState, OrderStateNumeric

# ---------------------------------------------------------------------------
# Slots / frozen / @dataclass shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [AccountValue, Position, PortfolioItem, Fill])
def test_is_real_dataclass(cls):
    """v3.0: NamedTuples are gone; these are real dataclasses now."""
    assert is_dataclass(cls)


@pytest.mark.parametrize("cls", [AccountValue, Position, PortfolioItem, Fill])
def test_has_slots(cls):
    assert "__slots__" in cls.__dict__


def test_position_is_frozen():
    p = Position(account="DU1", contract=ibi.Stock("AAPL", "SMART", "USD"))
    with pytest.raises(FrozenInstanceError):
        p.account = "DU2"  # type: ignore[misc]


def test_portfolio_item_is_frozen():
    item = PortfolioItem(contract=ibi.Stock("AAPL", "SMART", "USD"))
    with pytest.raises(FrozenInstanceError):
        item.position = Decimal("100")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AccountValue: monetary-tag whitelist + decimalValue property
# ---------------------------------------------------------------------------


def test_account_value_defaults_to_string_value():
    """``value`` is the wire-shape string regardless of tag."""
    av = AccountValue("DU1", "AccountType", "FA", "USD", "")
    assert av.value == "FA"
    assert av.decimalValue is None


def test_account_value_non_monetary_tag_returns_none_even_for_numeric_string():
    """``Currency`` is a string tag — never coerce to Decimal."""
    av = AccountValue("DU1", "Currency", "USD", "", "")
    assert av.decimalValue is None


def test_account_value_monetary_tag_garbage_returns_none():
    """A monetary tag with a malformed value returns None, not raises."""
    av = AccountValue("DU1", "NetLiquidation", "abc", "USD", "")
    assert av.decimalValue is None


def test_account_value_monetary_tag_empty_returns_none():
    av = AccountValue("DU1", "NetLiquidation", "", "USD", "")
    assert av.decimalValue is None


def test_account_value_monetary_tag_nan_returns_none():
    """Decimal('NaN') is silently truthy — must be normalized to None."""
    av = AccountValue("DU1", "NetLiquidation", "nan", "USD", "")
    assert av.decimalValue is None


def test_account_value_monetary_tag_infinity_returns_none():
    av = AccountValue("DU1", "NetLiquidation", "Infinity", "USD", "")
    assert av.decimalValue is None


def test_account_value_monetary_tag_valid_returns_decimal():
    av = AccountValue("DU1", "NetLiquidation", "12345.67", "USD", "")
    assert av.decimalValue == Decimal("12345.67")


def test_account_value_negative_monetary_value():
    av = AccountValue("DU1", "RealizedPnL", "-1234.56", "USD", "")
    assert av.decimalValue == Decimal("-1234.56")


def test_monetary_tag_whitelist_covers_known_aliases():
    """Sanity: catch the case where the whitelist is silently emptied."""
    for tag in (
        "NetLiquidation",
        "AvailableFunds",
        "TotalCashValue",
        "BuyingPower",
        "GrossPositionValue",
        "MaintMarginReq",
        "InitMarginReq",
        "RegTEquity",
    ):
        assert tag in MONETARY_ACCOUNT_VALUE_TAGS, tag


# ---------------------------------------------------------------------------
# Position / PortfolioItem: Decimal | None semantics
# ---------------------------------------------------------------------------


def test_position_defaults_are_none():
    p = Position(account="DU1", contract=ibi.Stock("AAPL", "SMART", "USD"))
    assert p.position is None
    assert p.avgCost is None


def test_position_constructed_with_decimals():
    p = Position(
        "DU1",
        ibi.Stock("AAPL", "SMART", "USD"),
        Decimal("100"),
        Decimal("150.25"),
    )
    assert p.position == Decimal("100")
    assert p.avgCost == Decimal("150.25")


def test_portfolio_item_defaults_are_none():
    item = PortfolioItem(contract=ibi.Stock("AAPL", "SMART", "USD"))
    assert item.position is None
    assert item.marketPrice is None
    assert item.marketValue is None
    assert item.averageCost is None
    assert item.unrealizedPNL is None
    assert item.realizedPNL is None
    assert item.account == ""


def test_portfolio_item_full_construction():
    item = PortfolioItem(
        ibi.Stock("AAPL", "SMART", "USD"),
        Decimal("100"),
        Decimal("150.25"),
        Decimal("15025.00"),
        Decimal("145.00"),
        Decimal("125.00"),
        Decimal("-50.00"),
        "DU1",
    )
    assert item.position == Decimal("100")
    assert item.unrealizedPNL == Decimal("125.00")
    assert item.realizedPNL == Decimal("-50.00")


# ---------------------------------------------------------------------------
# OrderState commission family: Decimal | None
# ---------------------------------------------------------------------------


def test_order_state_commission_defaults_are_none():
    s = OrderState()
    assert s.commissionAndFees is None
    assert s.minCommission is None
    assert s.maxCommission is None


def test_order_state_unset_commission_is_falsy():
    """The Decimal('NaN') trap fix: ``if state.commissionAndFees:`` must be
    False when commission is unset, not silently True the way NaN was.
    """
    s = OrderState()
    assert not s.commissionAndFees
    assert not s.minCommission
    assert not s.maxCommission


def test_order_state_commission_explicit_zero_is_falsy_too():
    s = OrderState(commissionAndFees=Decimal("0"))
    assert not s.commissionAndFees


def test_order_state_commission_nonzero_is_truthy():
    s = OrderState(commissionAndFees=Decimal("1.50"))
    assert s.commissionAndFees


def test_order_state_numeric_round_trip_with_decimal_input():
    """``.numeric(2)`` must accept ``Decimal | None`` input from a
    Decimal-native ``OrderState`` and return float | None on the
    commissionAndFees family.
    """
    s = OrderState(commissionAndFees=Decimal("1.567"), minCommission=None)
    n: OrderStateNumeric = s.numeric(2)
    assert n.commissionAndFees == 1.57
    assert n.minCommission is None


def test_order_state_formatted_handles_decimal_and_none():
    s = OrderState(commissionAndFees=Decimal("1234.567"))
    out = s.formatted(2)
    assert out.commissionAndFees == "1,234.57"
    assert out.minCommission is None


# ---------------------------------------------------------------------------
# Wrapper.position drop-on-zero / drop-on-None semantics
# ---------------------------------------------------------------------------


def _ib() -> ibi.IB:
    """Bare wrapper — no connection — exercising position bookkeeping."""
    return ibi.IB()


def test_wrapper_position_stores_nonzero_position():
    ib = _ib()
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 7
    ib.wrapper.position("DU1", contract, Decimal("100"), Decimal("150.25"))
    assert ib.wrapper.positions["DU1"][7].position == Decimal("100")


def test_wrapper_position_zero_drops_cached_entry():
    """A real wire ``Decimal('0')`` means closed position — drop entry."""
    ib = _ib()
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 7
    ib.wrapper.position("DU1", contract, Decimal("100"), Decimal("150.25"))
    assert 7 in ib.wrapper.positions["DU1"]
    ib.wrapper.position("DU1", contract, Decimal("0"), Decimal("0"))
    assert 7 not in ib.wrapper.positions["DU1"]


def test_wrapper_position_none_drops_cached_entry():
    """A wire-empty position string (``safe_decimal("") == None``) drops too."""
    ib = _ib()
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 7
    ib.wrapper.position("DU1", contract, Decimal("100"), Decimal("150.25"))
    assert 7 in ib.wrapper.positions["DU1"]
    ib.wrapper.position("DU1", contract, None, None)
    assert 7 not in ib.wrapper.positions["DU1"]


def test_wrapper_update_portfolio_zero_drops_cached_entry():
    ib = _ib()
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 7
    ib.wrapper.updatePortfolio(
        contract,
        Decimal("100"),
        Decimal("150.25"),
        Decimal("15025.00"),
        Decimal("145.00"),
        Decimal("125.00"),
        Decimal("-50.00"),
        "DU1",
    )
    assert 7 in ib.wrapper.portfolio["DU1"]
    ib.wrapper.updatePortfolio(
        contract,
        Decimal("0"),
        None,
        None,
        None,
        None,
        None,
        "DU1",
    )
    assert 7 not in ib.wrapper.portfolio["DU1"]


# ---------------------------------------------------------------------------
# Fill construction (slots/frozen sanity)
# ---------------------------------------------------------------------------


def test_fill_construction_round_trip():
    from datetime import datetime

    fill = Fill(
        ibi.Stock("AAPL", "SMART", "USD"),
        Execution(execId="abc", shares=Decimal("10"), price=Decimal("150")),
        ibi.CommissionReport(execId="abc", commissionAndFees=Decimal("1.0")),
        datetime(2026, 5, 9, tzinfo=UTC),
    )
    assert fill.execution.shares == Decimal("10")
    assert fill.commissionReport.commissionAndFees == Decimal("1.0")
