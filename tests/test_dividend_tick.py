"""The type-59 dividend tickString parser.

IBKR can embed thousands separators in any numeric field of the dividend
tick ('past12,next12,yyyymmdd,amount'), so the naive comma split
unpacks five fields misaligned or recombines them into an invented
number. The parser anchors the 8-digit date and accepts either numeric
form in every field."""

from __future__ import annotations

from datetime import date

from ib_async.objects import Dividends
from ib_async.wrapper import _parse_dividend_tick


def test_normal_shape_parses() -> None:
    assert _parse_dividend_tick("0.83,0.92,20130219,0.23") == Dividends(
        0.83, 0.92, date(2013, 2, 19), 0.23)


def test_separator_in_next12_parses() -> None:
    # measured live: empty past12, next12 over a thousand, five fields
    assert _parse_dividend_tick(",1,089.45,20261116,2.199") == Dividends(
        None, 1089.45, date(2026, 11, 16), 2.199)


def test_separator_in_amount_parses() -> None:
    assert _parse_dividend_tick("0.83,0.92,20261116,1,089.45") == Dividends(
        0.83, 0.92, date(2026, 11, 16), 1089.45)


def test_separator_in_every_numeric_field() -> None:
    assert _parse_dividend_tick(
        "1,089.45,2,234.56,20261116,1,089.45") == Dividends(
        1089.45, 2234.56, date(2026, 11, 16), 1089.45)


def test_empty_aggregates_parse_to_none() -> None:
    assert _parse_dividend_tick(",,20261218,") == Dividends(
        None, None, date(2026, 12, 18), None)


def test_garbage_is_none_never_a_guess() -> None:
    assert _parse_dividend_tick("not,a,tick") is None
    assert _parse_dividend_tick("") is None
    assert _parse_dividend_tick("1,2") is None


def test_non_eight_digit_date_refuses() -> None:
    assert _parse_dividend_tick("0.83,0.92,2013219,0.23") is None
