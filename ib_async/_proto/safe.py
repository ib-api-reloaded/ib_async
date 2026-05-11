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
from typing import Final, TypeGuard

from ..util import UNSET_DECIMAL, UNSET_DOUBLE, UNSET_INTEGER, UNSET_LONG

# IBKR's reference ``decode(Decimal, fields)`` (utils.py) treats these
# wire strings as the "unset Decimal" sentinel: max int32, max int64,
# max double in upper-case-E scientific form, and the most-negative
# int64. Any of these arriving as the wire string for a Decimal field
# means "no value" — the caller's domain ``Decimal | None`` should
# stay ``None`` instead of carrying a 2.1 billion or 1.8e308 fake
# quantity that would corrupt every downstream calculation.
_DECIMAL_UNSET_STRINGS: Final[frozenset[str]] = frozenset(
    {
        "2147483647",  # UNSET_INTEGER
        "9223372036854775807",  # UNSET_LONG
        "1.7976931348623157E308",  # UNSET_DOUBLE (uppercase E, IBKR's spelling)
        "1.7976931348623157e+308",  # UNSET_DOUBLE (lowercase e+, Python's str(float))
        "1.7976931348623157e308",  # UNSET_DOUBLE (lowercase e, no plus sign)
        "-9223372036854775808",  # most-negative int64
    }
)


def is_valid_int(value: int | None) -> TypeGuard[int]:
    """Returns True when ``value`` should be written to the proto wire.

    Mirrors IBKR's ``isValidIntValue`` (``client_utils.py``): ``None``
    (our domain unset sentinel) and the IBKR magic ``UNSET_INTEGER``
    wire value both come back False, so the proto3-optional field stays
    absent on the wire and the server's default fill behaves correctly.
    """
    if value is None:
        return False
    return value != UNSET_INTEGER


def is_valid_float(value: float | Decimal | None) -> TypeGuard[float | Decimal]:
    """Float / Decimal analogue of :func:`is_valid_int`. Rejects
    ``None`` and the IBKR magic ``UNSET_DOUBLE`` sentinel."""
    if value is None:
        return False
    return value != UNSET_DOUBLE


def is_valid_long(value: int | None) -> TypeGuard[int]:
    """``int64`` analogue. Rejects ``None`` and ``UNSET_LONG``. Use for
    proto fields typed ``optional int64`` (e.g. ``Order.permId``)."""
    if value is None:
        return False
    return value != UNSET_LONG


def is_valid_decimal(value: Decimal | None) -> TypeGuard[Decimal]:
    """Stringly-encoded Decimal analogue. Rejects ``None`` and the
    ``UNSET_DECIMAL`` sentinel. Use for proto string fields that carry
    a Decimal in IBKR's canonical wire form (e.g.
    ``Order.totalQuantity``)."""
    if value is None:
        return False
    return value != UNSET_DECIMAL


def format_proto_double(value: float) -> str:
    """Format a protobuf ``double`` as the canonical IBKR string form.

    Whole numbers come back without a trailing decimal point, fractions
    keep up to eight digits with trailing zeros stripped. Used for
    fields like ``Contract.multiplier`` where the wire type is double
    but the domain dataclass stores a string for backwards compat.
    """
    return f"{value:.8f}".rstrip("0").rstrip(".")


def fill_tag_value_map(items: object, target: object) -> None:
    """Copy a domain ``list[TagValue]`` into a proto ``map<string,string>``.

    Mirrors IBKR's ``client_utils.fillTagValueList`` — empty / ``None``
    inputs leave the proto map field unset on the wire (matching the
    binary path's "skip the options block when the list is empty"
    behaviour). Each ``TagValue`` is unpacked positionally so any
    ``NamedTuple`` / dataclass / 2-tuple shape works.

    Both args are typed ``object`` because the protobuf generated stubs
    expose maps as ``ScalarMap[str, str]`` from a private name we can't
    import, and the input is a domain list whose element type lives in
    ``contract`` (importing it here would cycle).
    """
    if not items:
        return
    for tv in items:  # type: ignore[attr-defined]
        tag, value = tv  # NamedTuple / sequence unpack
        target[tag] = value  # type: ignore[index]


def safe_decimal(value: str | Decimal | float | int | None) -> Decimal | None:
    """Convert any wire-typed numeric to a domain ``Decimal | None``.

    Accepts protobuf ``string`` (the IBKR-canonical encoding for
    quantities, prices, commissions), protobuf ``double`` (used for
    a handful of legacy fields like ``percentOffset`` and the
    ``cashQty`` family), pre-coerced ``Decimal``, plain ``int``,
    or ``None``. Returns ``None`` for any input that cannot be coerced
    to a finite ``Decimal`` — including empty / ``"nan"`` / ``"Infinity"``
    / IBKR's UNSET_INTEGER / UNSET_LONG / UNSET_DOUBLE sentinel strings
    / garbage — so domain dataclass fields typed ``Decimal | None``
    carry the "unset" signal explicitly. Callers that need a non-``None``
    fallback (e.g. ``filledQuantity`` defaulting to zero) substitute
    via ``safe_decimal(value) or Decimal('0')``.

    Float inputs route through ``str()`` so binary-float imprecision
    (e.g. ``Decimal(0.1) == Decimal('0.1000000000000000055...')``)
    does not contaminate the result; ``Decimal(str(0.1)) == Decimal('0.1')``.

    Pre-coerced ``Decimal`` inputs pass through unchanged (after the
    sentinel / NaN / Infinity guards) so callers like ``Decoder.parse``
    that re-run the helper over already-coerced dataclass attributes
    are idempotent.
    """
    if value is None or value == "":
        return None
    if isinstance(value, str) and value in _DECIMAL_UNSET_STRINGS:
        return None
    if isinstance(value, float):
        # The IBKR magic-double sentinel arrives here on the protobuf
        # ``double`` paths; checking after str() would miss it because
        # ``str(sys.float_info.max)`` does not match the canonical
        # sentinel spelling on every Python build.
        from ..util import UNSET_DOUBLE

        if value == UNSET_DOUBLE:
            return None
        value = str(value)
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return None
    if result.is_nan() or result.is_infinite():
        return None
    return result


def wire_size_to_float(s: str) -> float:
    """Coerce a wire-string size (Decimal-typed on the wire, float-typed
    on the wrapper signature) to ``float``.

    Goes through ``safe_decimal`` so empty / ``"nan"`` / sentinel /
    garbage land as ``0.0`` instead of raising. The wrapper's
    ``size == 0`` checks are semantically equivalent to "size is unset"
    on the binary path, so dropping unparseable values to zero matches
    that behaviour exactly. Used by tick / market-depth / historical-
    tick converters pending the Ticker hot-path Decimal benchmark.
    """
    d = safe_decimal(s)
    return float(d) if d is not None else 0.0
