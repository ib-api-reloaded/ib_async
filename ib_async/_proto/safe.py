"""Safe coercion helpers for protobuf string fields.

IBKR encodes Decimal-typed quantities (positions, fractional-share
order sizes, fill quantities, commission components) as protobuf
``string`` fields. Naive ``Decimal(field)`` calls raise
``InvalidOperation`` on empty strings, ``"nan"``, or any malformed
input — and a converter that lets that propagate hangs the awaiter
when the decoder swallows the exception. This module provides the
single coercion path every converter must use so a malformed wire
value lands as ``None`` (the unset sentinel for our domain dataclass
``Decimal | None`` fields) instead of an uncaught exception.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def format_proto_double(value: float) -> str:
    """Format a protobuf ``double`` as the canonical IBKR string form.

    Whole numbers come back without a trailing decimal point, fractions
    keep up to eight digits with trailing zeros stripped. Used for
    fields like ``Contract.multiplier`` where the wire type is double
    but the domain dataclass stores a string for backwards compat.
    """
    return f"{value:.8f}".rstrip("0").rstrip(".")


def safe_decimal(value: str | None) -> Decimal | None:
    """Convert a protobuf-string Decimal field to a ``Decimal | None``.

    Returns ``None`` for any input that cannot be coerced to a finite
    ``Decimal`` — including empty / ``"nan"`` / ``"Infinity"`` / garbage
    — so domain dataclass fields typed ``Decimal | None`` carry the
    "unset" signal explicitly. Callers that need a non-``None``
    fallback (e.g. ``filledQuantity`` defaulting to zero) substitute
    via ``safe_decimal(value) or Decimal('0')``.
    """
    if value is None or value == "":
        return None
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if result.is_nan() or result.is_infinite():
        return None
    return result
