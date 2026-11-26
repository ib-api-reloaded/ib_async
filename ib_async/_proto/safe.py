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

from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message

from ..util import UNSET_DECIMAL, UNSET_DOUBLE, UNSET_INTEGER, UNSET_LONG

if TYPE_CHECKING:
    from ..contract import TagValue

# Plain-scalar type annotation strings that survive ``from __future__ import
# annotations``. Fields typed as ``int | None`` / ``Optional[int]`` etc are
# intentionally left out — for those, ``None`` is the domain unset sentinel
# and is meant to skip the wire emission. If a caller sets ``None`` on a
# plain ``int``, ``float``, ``bool`` or ``str`` field with a real default,
# the field is set back to that default.
_PLAIN_SCALAR_TYPES: Final[frozenset[str]] = frozenset({"int", "float", "bool", "str"})

T = TypeVar("T")


def normalize_none_scalars(obj: T) -> T:
    """Coerce ``None`` on plain-scalar dataclass fields back to the field's
    default value (typically ``0`` for plain ``int`` fields like
    ``parentId``, ``ocaType``, ``triggerMethod``). Mutates and returns
    ``obj`` so callers can chain it on converter entry.

    Without this normalization, a caller that sets ``parentId = None``
    (to send no parent link) produces a wire frame missing the field
    entirely; TWS reads
    proto3-absent as its own ``UNSET_INTEGER = 2147483647`` sentinel and
    rejects the request with ``Error 135: Can't find order with id =
    2147483647``. The field's default is what end-users expect from
    ``= None``.

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
    ``None`` and the IBKR magic ``UNSET_DOUBLE`` sentinel, also as a
    Decimal, which ``float()`` would turn back into it on the wire."""
    if value is None:
        return False
    return float(value) != UNSET_DOUBLE


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
    ``Order.totalQuantity``). Rejects ``UNSET_DOUBLE`` too."""
    if value is None:
        return False
    return value != UNSET_DECIMAL and float(value) != UNSET_DOUBLE


# The value IBKR writes in a numeric field it did not set, by the field's
# protobuf type. A 32-bit field can hold only UNSET_INTEGER, a 64-bit one
# UNSET_LONG; 2147483647 in a 64-bit field (a permId, say) is a value.
_UNSET_BY_CPPTYPE: Final[dict[int, int | float]] = {
    FieldDescriptor.CPPTYPE_INT32: UNSET_INTEGER,
    FieldDescriptor.CPPTYPE_UINT32: UNSET_INTEGER,
    FieldDescriptor.CPPTYPE_INT64: UNSET_LONG,
    FieldDescriptor.CPPTYPE_UINT64: UNSET_LONG,
    FieldDescriptor.CPPTYPE_DOUBLE: UNSET_DOUBLE,
}


def clear_unset_fields(message: Message) -> None:
    """Clear every numeric field of ``message``, nested ones included,
    that holds IBKR's unset value for its type, and drop such values from
    repeated fields.

    IBKR's clients send an unset field as absent, so a field present with
    the unset value means the same: after this, the converters' ``HasField``
    checks give the field's default (None in the domain objects). NaN and
    infinity stay; +Infinity is a value for ``competeAgainstBestOffset``.
    """
    for field, value in message.ListFields():
        if field.cpp_type == FieldDescriptor.CPPTYPE_MESSAGE:
            if field.message_type.GetOptions().map_entry:
                mapped = field.message_type.fields_by_name["value"]
                if mapped.cpp_type == FieldDescriptor.CPPTYPE_MESSAGE:
                    for item in value.values():
                        clear_unset_fields(item)
            elif field.is_repeated:
                for item in value:
                    clear_unset_fields(item)
            else:
                clear_unset_fields(value)
            continue
        unset = _UNSET_BY_CPPTYPE.get(field.cpp_type)
        if unset is None:
            continue
        if field.is_repeated:
            kept = [item for item in value if item != unset]
            if len(kept) != len(value):
                del value[:]
                value.extend(kept)
        elif value == unset:
            message.ClearField(field.name)


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
    input leaves the map field unset on the wire.
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
    sentinel / NaN / Infinity guards), so running the helper again over
    an already-coerced value changes nothing.
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
    ``size == 0`` checks treat that as "size is unset". Used by the
    tick, market-depth and historical-tick converters, whose wrapper
    methods take floats.
    """
    d = safe_decimal(s)
    return float(d) if d is not None else 0.0
