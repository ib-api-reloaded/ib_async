"""Negative-path coverage for ``safe_decimal``.

Every Decimal-typed protobuf field in the IBKR schema is encoded as a
``string`` on the wire. The converters call ``safe_decimal`` on every
such field; if a malformed value is ever observed in production, we
need a defined ``None`` outcome rather than a connection-breaking
exception. The domain dataclass fields are typed ``Decimal | None``
so ``None`` round-trips cleanly through ``if value:`` checks in user
code without the silent-truthy hazard of ``Decimal('NaN')``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ib_async._proto.safe import safe_decimal

# --- inputs that must produce ``None`` -----------------------------------


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "nan",
        "NaN",
        "NAN",
        "Infinity",
        "-Infinity",
        "inf",
        "-inf",
        "abc",
        "1.2.3",
        "  ",  # whitespace only
        "12abc",
    ],
)
def test_safe_decimal_returns_none_on_garbage_input(value):
    assert safe_decimal(value) is None


def test_safe_decimal_is_falsy_on_unset_so_if_checks_work():
    # The whole point of ``Decimal | None`` instead of ``Decimal('NaN')``
    # is that ``if price:`` correctly evaluates falsy on unset. Guard
    # against a future change that reverts to NaN-default and silently
    # breaks user code.
    result = safe_decimal("")
    assert not result
    assert result is None


# --- inputs that must round-trip to a usable Decimal --------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", Decimal(0)),
        ("0.0", Decimal("0.0")),
        ("1.5", Decimal("1.5")),
        ("100", Decimal(100)),
        ("-3.14", Decimal("-3.14")),
        ("0.00001", Decimal("0.00001")),
        ("9999999999999.999999", Decimal("9999999999999.999999")),
    ],
)
def test_safe_decimal_round_trips_clean_inputs(value, expected):
    assert safe_decimal(value) == expected
