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

import dataclasses
from collections.abc import MutableMapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Final, TypeGuard, TypeVar

from ..util import UNSET_DECIMAL, UNSET_DOUBLE, UNSET_INTEGER, UNSET_LONG

if TYPE_CHECKING:
    from ..contract import TagValue

# Plain-scalar type annotation strings that survive ``from __future__ import
# annotations``. Fields typed as ``int | None`` / ``Optional[int]`` etc are
# intentionally left out — for those, ``None`` is the domain unset sentinel
# and is meant to skip the wire emission. If a caller sets ``None`` on a
# plain ``int``, ``float``, ``bool`` or ``str`` field with a real default,
# the field is set back to that default. The binary path does the
# equivalent: ``Client._formatField`` writes None as "" when it formats
# the message.
_PLAIN_SCALAR_TYPES: Final[frozenset[str]] = frozenset({"int", "float", "bool", "str"})

T = TypeVar("T")


def normalize_none_scalars(obj: T) -> T:
    """Coerce ``None`` on plain-scalar dataclass fields back to the field's
    default value. Mutates and returns ``obj`` so callers can chain it on
    converter entry — the proto path's analog of the binary path's
    ``NoneType → ""`` formatter, which the TWS server parses as the
    field's wire-default (typically ``0`` for plain ``int`` fields like
    ``parentId``, ``ocaType``, ``triggerMethod``).

    Without this normalization, a caller that sets ``parentId = None``
    (to send no parent link) produces a wire frame missing the field
    entirely; TWS reads
    proto3-absent as its own ``UNSET_INTEGER = 2147483647`` sentinel and
    rejects the request with ``Error 135: Can't find order with id =
    2147483647``. The binary path always emits ``""`` for None and the
    server reads ``""`` as the field's default, which is what
    end-users expect from ``= None``.

    Only acts on plain-scalar annotations (``int`` / ``float`` / ``bool``
    / ``str``). ``int | None`` / ``Decimal | None`` / etc are left alone
    because ``None`` is their domain unset sentinel and the converter
    callers already gate emission on ``is not None`` / ``_isValidInt`` /
    similar.
    """
    if not dataclasses.is_dataclass(obj):
        return obj
    for f in dataclasses.fields(obj):
        if f.type in _PLAIN_SCALAR_TYPES and getattr(obj, f.name, None) is None:
            # ``MISSING`` for fields with no default is rare on the IBKR
            # dataclasses but guarded for symmetry: leave the slot as
            # None and let the converter's gate skip it.
            if f.default is not dataclasses.MISSING:
                setattr(obj, f.name, f.default)
    return obj


# These wire strings are IBKR's "unset Decimal" sentinel: max int32,
# max int64, max double (in each spelling it arrives in), and the
# most-negative int64. Any of these arriving as the wire string for a
# Decimal field means "no value" — the caller's domain ``Decimal | None`` should
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

    ``None`` (our domain unset sentinel) and the IBKR magic ``UNSET_INTEGER``
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


def fill_tag_value_map(
    items: Sequence[TagValue] | None, target: MutableMapping[str, str]
) -> None:
    """Copy a domain ``list[TagValue]`` into a proto ``map<string,string>``.

    The target is the map field of the parent proto. An empty or ``None``
    input leaves the map field unset on the wire. The binary path also
    skips the options block when the list is empty.
    """
    if not items:
        return
    for tv in items:
        target[tv.tag] = tv.value


def safe_decimal(value: str | Decimal | float | None) -> Decimal | None:
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
    that behaviour exactly. Used by the tick, market-depth and
    historical-tick converters, whose wrapper methods take floats.
    """
    d = safe_decimal(s)
    return float(d) if d is not None else 0.0
