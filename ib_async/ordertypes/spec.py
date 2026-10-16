"""Order type definitions as data.

An :class:`OrderTypeSpec` describes one IBKR order type:

* its ``orderType`` code;
* the constructor parameters and the :class:`~ib_async.order.Order` field
  each one sets;
* any other fields that define the type;
* the products and exchanges IBKR documents it for;
* its stability.

The order type constructors and their documentation are generated from
this catalog, and :func:`build` enforces it when an order is constructed.
Each spec validates the field names it uses when it is defined, so a
catalog mistake fails at import time.

Parameter values are validated by :func:`checkedValue`. Prices and
quantities must be finite numbers, counts whole numbers, flags bools and
codes strings. A value that the Order would silently unset or misread
raises :class:`OrderTypeError` naming the constructor and the parameter.
"""

from __future__ import annotations

import dataclasses
import enum
import math
import numbers
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType
from typing import Any, ClassVar, Protocol

from ..contract import TagValue
from ..order import (
    ORDER_FIELD_TYPES,
    Order,
    OrderComboLeg,
    finiteDecimal,
    orderDecimal,
    takesInfinity,
)
from ..util import checkUnique

# Every Order field's default, read-only: a field holding its default is
# unset. A default made by a factory (a list, a SoftDollarTier) is one
# instance here, only compared against; unset() makes a fresh one.
ORDER_DEFAULTS: Mapping[str, Any] = MappingProxyType(
    {
        f.name: f.default_factory() if callable(f.default_factory) else f.default
        for f in dataclasses.fields(Order)
    }
)


def isSet(field: str, value: Any) -> bool:
    """Return True if ``value`` for Order ``field`` is neither None nor
    the field's default.

    A price of 0 counts as set when the field defaults to None. When the
    field defaults to 0 (0 means "none" for that field), 0 is unset."""
    return value is not None and value != ORDER_DEFAULTS[field]


def unset(field: str) -> Any:
    """Return the default (unset) value of Order ``field``.

    Factory defaults such as a list or a SoftDollarTier are created fresh,
    as Order does."""
    factory = _DEFAULT_FACTORIES.get(field)
    return factory() if factory is not None else ORDER_DEFAULTS[field]


# The factories of Order's defaults made fresh for each Order.
_DEFAULT_FACTORIES: Mapping[str, Callable[[], Any]] = MappingProxyType(
    {
        f.name: f.default_factory
        for f in dataclasses.fields(Order)
        if callable(f.default_factory)
    }
)


def _checkFields(owner: str, fields: Iterable[str]) -> None:
    unknown = [f for f in fields if f not in ORDER_DEFAULTS]
    if unknown:
        raise ValueError(f"{owner}: Order has no field {', '.join(unknown)}")


# The actions IBKR takes: buy, sell, sell short, and sell long (for
# institutional accounts).
ACTIONS = ("BUY", "SELL", "SSHORT", "SLONG")

# How TWS reports back an order an IB algo works, whatever its type; IBKR
# refuses it on a modification.
ALGO_ORDER_TYPE = "IBALGO"


def baseOrderType(order: Order) -> str:
    """``order.orderType``, except "LMT" for an algo order TWS reported as
    "IBALGO", as an application modifying live algo orders sends it."""
    return "LMT" if order.orderType == ALGO_ORDER_TYPE else order.orderType


@dataclass(frozen=True, slots=True)
class FieldValue:
    """An Order field and the value it holds."""

    field: str
    value: Any


@dataclass(frozen=True, slots=True)
class FieldIn:
    """An Order field that must hold one of ``allowed``."""

    field: str
    allowed: tuple[Any, ...]


class Stability(enum.StrEnum):
    """How dependable an order type is to use."""

    # Broadly supported across products and exchanges; standard usage.
    STABLE = "stable"
    # Only on certain exchanges, products or venues; check the details.
    VENUE = "venue"
    # Many interacting parameters, and behavior that varies with the
    # market and IBKR's configuration; test before relying on it.
    ADVANCED = "advanced"


class Kind(enum.StrEnum):
    """How a parameter's value goes into the Order."""

    FIELD = "field"  # set on its field as the field holds it
    # A tag value: one TagValue in its field's list, encoded for IBKR.
    BOOL = "bool"  # sent as "1" / "0"
    INT = "int"
    FLOAT = "float"
    STR = "str"
    # A price per combo leg, set as orderComboLegs.
    LEG_PRICES = "legPrices"


# The kinds of a tag value.
_TAG_KINDS = frozenset({Kind.BOOL, Kind.INT, Kind.FLOAT, Kind.STR})


def _realNumber(value: Any) -> float | None:
    """Return ``value`` as a float if it is a finite real number, else None.

    Accepts int, float, Decimal and numpy numbers, but not bool."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real | Decimal):
        return None
    try:
        real = float(value)
    except (OverflowError, ValueError):  # too large for a float, or signaling NaN
        return None
    return real if math.isfinite(real) else None


def _wholeNumber(value: Any) -> int | None:
    """Return ``value`` as an int if it is a whole number, else None.

    Accepts int, numpy integers, and real numbers with a whole value such
    as 100.0 or Decimal(100), but not bool."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real | Decimal):
        return None
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, Decimal):
        whole = value.is_finite() and value == value.to_integral_value()
        return int(value) if whole else None
    real = _realNumber(value)
    return int(real) if real is not None and real.is_integer() else None


@dataclass(frozen=True, slots=True)
class Param:
    """One constructor parameter and the Order field it sets.

    With ``tag``, the field is a list of tag values (such as
    ``smartComboRoutingParams``) and the parameter adds one entry, its value
    encoded as its tag ``kind``."""

    name: str
    field: str
    doc: str
    required: bool = True
    tag: str = ""
    kind: Kind = Kind.FIELD
    # The values IBKR accepts, when it names them (string tag values only).
    allowed: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.tag) != (self.kind in _TAG_KINDS):
            raise ValueError(f"{self.name}: a tag needs a tag kind, and only a tag")
        if self.allowed and self.kind is not Kind.STR:
            raise ValueError(f"{self.name}: only string tag values have allowed values")
        _checkFields(self.name, (self.field,))

    def encode(self, owner: str, value: Any) -> str:
        """Encode ``value`` as an IBKR tag value string.

        Validates it against the parameter's kind and allowed values;
        errors name ``owner``."""
        if self.kind is Kind.BOOL and isinstance(value, bool):
            encoded = "1" if value else "0"
        elif self.kind is Kind.INT and (whole := _wholeNumber(value)) is not None:
            encoded = str(whole)
        elif self.kind is Kind.FLOAT and (real := _realNumber(value)) is not None:
            encoded = str(real)
        elif self.kind is Kind.STR and isinstance(value, str):
            encoded = value
        else:
            what = {
                Kind.INT: "a whole number",
                Kind.FLOAT: "a finite number",
            }.get(self.kind, f"a {self.kind}")
            raise OrderTypeError(f"{owner}: {self.name} must be {what}, not {value!r}")
        if self.allowed and value not in self.allowed:
            raise OrderTypeError(
                f"{owner}: {self.name} is one of {', '.join(self.allowed)}, "
                f"not {value!r}"
            )
        return encoded

    def coerce(self, owner: str, value: Any) -> Any:
        """Convert ``value`` to the form this parameter stores in the Order.

        Returns a TagValue for a tag parameter, a list of OrderComboLegs
        for leg prices, or the field value as checked by
        :func:`checkedValue`. None stays None.

        Raises :class:`OrderTypeError` for values the Order would silently
        unset or misread: NaN, infinity, or a non-number."""
        if value is None:
            return None
        if self.tag:
            return TagValue(self.tag, self.encode(owner, value))
        if self.kind is Kind.LEG_PRICES:
            return _legs(owner, self, value)
        return checkedValue(owner, self.name, self.field, value)

    def given(self, value: Any) -> bool:
        """Return True if the coerced ``value`` counts as given.

        It must not be None. For a plain field it must also not be the
        field's default, as checked by :func:`isSet`."""
        return value is not None and (
            self.kind is not Kind.FIELD or isSet(self.field, value)
        )


def checkedDecimal(owner: str, name: str, value: Any) -> Decimal:
    """Convert ``value`` (a number or numeric string) to a finite Decimal.

    Raises :class:`OrderTypeError` for NaN, infinity or an unparseable
    string, which the Order would otherwise silently unset."""
    number = finiteDecimal(value)
    if number is None:
        raise OrderTypeError(f"{owner}: {name} must be a finite number, not {value!r}")
    return number


def checkedValue(
    owner: str, name: str, field: str, value: Any, *, infinity: bool = False
) -> Any:
    """Validate ``value`` (passed as ``name``) for Order ``field``.

    By field type:

    * Decimal: a finite number or numeric string. +Infinity is also
      accepted if ``infinity`` is True and IBKR gives it a meaning for
      the field.
    * float: a finite real number, returned as a float.
    * int: a whole number, returned as an int.
    * bool: True or False.
    * str: a string.
    * anything else (a list, a record): returned unchanged. None is also
      returned unchanged.

    Raises :class:`OrderTypeError` for values the Order would silently
    unset (NaN, infinity, a non-numeric string) or misread (a string for
    a float field, a fraction for an int field, "false" for a bool
    field)."""
    if value is None:
        return None
    kind = ORDER_FIELD_TYPES.get(field)
    if kind is Decimal:
        if not (infinity and takesInfinity(field)):
            return checkedDecimal(owner, name, value)
        decimal = orderDecimal(field, value)
        if decimal is None:
            raise OrderTypeError(
                f"{owner}: {name} must be a finite number or +Infinity, not {value!r}"
            )
        return decimal
    if kind is float:
        real = _realNumber(value)
        if real is None:
            raise OrderTypeError(
                f"{owner}: {name} must be a finite number, not {value!r}"
            )
        return real
    if kind is int:
        whole = _wholeNumber(value)
        if whole is None:
            raise OrderTypeError(
                f"{owner}: {name} must be a whole number, not {value!r}"
            )
        return whole
    if kind is bool and not isinstance(value, bool):
        raise OrderTypeError(f"{owner}: {name} must be True or False, not {value!r}")
    if kind is str and not isinstance(value, str):
        raise OrderTypeError(f"{owner}: {name} must be a string, not {value!r}")
    return value


def checkedFields(owner: str, fields: Mapping[str, Any]) -> dict[str, Any]:
    """Validate Order ``fields`` by field name with :func:`checkedValue`.

    +Infinity is allowed where IBKR gives it a meaning. None becomes the
    field's default."""
    return {
        name: unset(name)
        if value is None and name in ORDER_DEFAULTS
        else checkedValue(owner, name, name, value, infinity=True)
        for name, value in fields.items()
    }


def coerced(
    owner: str, params: tuple[Param, ...], values: Mapping[str, Any]
) -> dict[str, Any]:
    """Each parameter's value (None when not passed) coerced as
    :meth:`Param.coerce` says, by parameter name."""
    return {p.name: p.coerce(owner, values.get(p.name)) for p in params}


def required(owner: str, params: tuple[Param, ...], values: Mapping[str, Any]) -> None:
    """Refuse a required parameter not given, of the coerced ``values``."""
    missing = [p.name for p in params if p.required and not p.given(values[p.name])]
    if missing:
        raise OrderTypeError(f"{owner} needs {', '.join(missing)}")


def _legs(owner: str, param: Param, prices: Any) -> list[OrderComboLeg]:
    """Build one OrderComboLeg per price in ``prices``, in leg order.

    Each price must be a finite number, and there must be at least one."""
    if isinstance(prices, str) or not isinstance(prices, Sequence):
        raise OrderTypeError(
            f"{owner}: {param.name} is a list of prices, one per leg, in the "
            f"legs' order, not {prices!r}"
        )
    legs = [
        OrderComboLeg(price=checkedDecimal(owner, f"{param.name}[{index}]", price))
        for index, price in enumerate(prices)
    ]
    if not legs:
        raise OrderTypeError(f"{owner}: {param.name} needs a price per leg, not none")
    return legs


def paramFields(params: tuple[Param, ...], values: Mapping[str, Any]) -> dict[str, Any]:
    """The Order fields the parameters' coerced ``values`` set; a None
    value leaves its parameter out."""
    fields: dict[str, Any] = {}
    for p in params:
        value = values[p.name]
        if value is None:
            continue
        if p.tag:
            fields.setdefault(p.field, []).append(value)
        else:
            fields[p.field] = value
    return fields


def checkTagParams(owner: str, params: tuple[Param, ...], field: str) -> None:
    """Refuse ``params`` that are not all tag values of ``field``, each
    tag once."""
    stray = [p.name for p in params if not p.tag or p.field != field]
    if stray:
        raise ValueError(f"{owner}: not tag values of {field}: {', '.join(stray)}")
    checkUnique(f"{owner} tags", (p.tag for p in params))


@dataclass(frozen=True, slots=True)
class OrderTypeSpec:
    """One order type."""

    className: str
    title: str
    orderType: str
    summary: str
    stability: Stability
    params: tuple[Param, ...] = ()
    # Fields besides orderType whose values define the type, such as
    # tif="OPG" for Market on Open; they cannot be overridden.
    defining: tuple[FieldValue, ...] = ()
    # Groups of optional parameters of which exactly one must be given.
    exactlyOne: tuple[tuple[str, ...], ...] = ()
    usage: str = ""
    products: tuple[str, ...] = ()
    exchanges: tuple[str, ...] = ()
    requires: str = ""
    # Constructor arguments for the generated example, as source text.
    example: str = ""

    def __post_init__(self) -> None:
        _checkFields(self.className, [d.field for d in self.defining])
        core = sorted(
            _CORE & ({d.field for d in self.defining} | {p.field for p in self.params})
        )
        if core:
            raise ValueError(f"{self.className}: build sets {', '.join(core)}")
        checkUnique(f"{self.className} parameters", (p.name for p in self.params))
        checkUnique(
            f"{self.className} fields",
            [p.field for p in self.params if not p.tag]
            + [f"{p.field}:{p.tag}" for p in self.params if p.tag]
            + [d.field for d in self.defining],
        )
        optional = {p.name for p in self.params if not p.required}
        for group in self.exactlyOne:
            if not set(group) <= optional:
                raise ValueError(
                    f"{self.className}: exactlyOne names {group}, not all optional "
                    "parameters"
                )

    @property
    def definingFields(self) -> Mapping[str, Any]:
        return {d.field: d.value for d in self.defining}

    @property
    def requiredFields(self) -> frozenset[str]:
        return frozenset(p.field for p in self.params if p.required)


@dataclass(frozen=True, slots=True)
class AlgoSpec:
    """One IB algo: a strategy that works an order of certain types."""

    className: str
    title: str
    strategy: str  # algoStrategy
    summary: str
    stability: Stability
    # The order types (orderType codes) it can work.
    orderTypes: tuple[str, ...]
    params: tuple[Param, ...] = ()  # every one tag-valued, field algoParams
    # Order fields that must hold one of the allowed values for the algo,
    # such as tif "" or "DAY" for Adaptive.
    conditions: tuple[FieldIn, ...] = ()
    usage: str = ""
    products: tuple[str, ...] = ()
    example: str = ""

    def __post_init__(self) -> None:
        _checkFields(self.className, [c.field for c in self.conditions])
        checkTagParams(self.className, self.params, "algoParams")


@dataclass(frozen=True, slots=True)
class OptionSpec:
    """An order option: Order fields that work across order types, such as
    outsideRth, passed to any order type constructor by name."""

    title: str
    fields: tuple[str, ...]
    summary: str
    stability: Stability
    usage: str = ""
    products: tuple[str, ...] = ()
    # An order type call using the option, as source text.
    example: str = ""

    def __post_init__(self) -> None:
        _checkFields(self.title, self.fields)


class Modifier(Protocol):
    """What modifies an order type (an Algo, a Routing, an Adjustment): the
    Order fields it sets, which the order type then cannot also be given;
    the order types (orderType codes) it works, empty for any; and the
    values it needs other fields to hold."""

    @property
    def title(self) -> str: ...

    @property
    def orderTypes(self) -> tuple[str, ...]: ...

    @property
    def conditions(self) -> tuple[FieldIn, ...]: ...

    @property
    def orderFields(self) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Routing:
    """How SMART routes a combo (BAG) order: ``routing=`` of any order
    type placed for a combo contract."""

    params: tuple[TagValue, ...] = ()

    title: ClassVar[str] = "Combo routing"
    orderTypes: ClassVar[tuple[str, ...]] = ()
    conditions: ClassVar[tuple[FieldIn, ...]] = ()

    @property
    def orderFields(self) -> dict[str, Any]:
        return {"smartComboRoutingParams": list(self.params)}


def buildRouting(params: tuple[Param, ...], values: Mapping[str, Any]) -> Routing:
    """A Routing from its parameter values, checked as an algo's are."""
    given = coerced(Routing.title, params, values)
    required(Routing.title, params, given)
    return Routing(tuple(paramFields(params, given).get("smartComboRoutingParams", [])))


@dataclass(frozen=True, slots=True)
class Algo:
    """An algo with its parameters, to work an order: ``algo=`` of any
    order type constructor that the algo applies to."""

    spec: AlgoSpec
    params: tuple[TagValue, ...] = ()

    @property
    def title(self) -> str:
        return self.spec.title

    @property
    def orderTypes(self) -> tuple[str, ...]:
        return self.spec.orderTypes

    @property
    def conditions(self) -> tuple[FieldIn, ...]:
        return self.spec.conditions

    @property
    def orderFields(self) -> dict[str, Any]:
        return {"algoStrategy": self.spec.strategy, "algoParams": list(self.params)}


# The order types IBKR adjusts: stops, stop limits and trailing stops.
ADJUSTABLE = ("STP", "STP LMT", "TRAIL", "TRAIL LIMIT")


@dataclass(frozen=True, slots=True)
class Adjustment:
    """A one-time change of a stop order into another once the price
    penetrates triggerPrice: ``adjust=`` of a stop, stop limit or trailing
    stop order (usually attached to a parent)."""

    title: str
    fields: tuple[FieldValue, ...]

    orderTypes: ClassVar[tuple[str, ...]] = ADJUSTABLE
    conditions: ClassVar[tuple[FieldIn, ...]] = ()

    def __post_init__(self) -> None:
        _checkFields(self.title, [f.field for f in self.fields])

    @property
    def orderFields(self) -> dict[str, Any]:
        return {f.field: f.value for f in self.fields}


class OrderTypeError(ValueError):
    """An order type constructed with missing, conflicting or forbidden values."""


# Set on every order by build(); the fields an order type always fills.
_CORE = frozenset({"orderType", "action", "totalQuantity"})


def buildAlgo(spec: AlgoSpec, values: Mapping[str, Any]) -> Algo:
    """An Algo for ``spec`` from its parameter values (None leaves a
    parameter to IBKR's default)."""
    given = coerced(spec.className, spec.params, values)
    required(spec.className, spec.params, given)
    return Algo(spec, tuple(paramFields(spec.params, given).get("algoParams", [])))


def build(
    spec: OrderTypeSpec,
    action: str,
    totalQuantity: Any,
    values: Mapping[str, Any],
    extra: Mapping[str, Any],
    algo: Algo | None = None,
    routing: Routing | None = None,
    adjust: Adjustment | None = None,
) -> dict[str, Any]:
    """Build the Order fields for ``spec``.

    Uses the parameter ``values`` (by parameter name) and other Order
    fields in ``extra``, then applies the optional ``algo``, combo
    ``routing`` and ``adjust`` modifiers.

    Raises :class:`OrderTypeError` for:

    * an action IBKR does not accept;
    * a quantity or price that is not a finite number;
    * a missing required parameter;
    * an exactly-one group with zero or several values given;
    * ``extra`` fields that the order type or a modifier sets itself (the
      code, the defining fields, the parameters' fields);
    * a modifier that sets one of the order type's own fields;
    * a modifier that does not apply to the order type, or whose
      conditions the order does not meet."""
    owner = spec.className
    if action not in ACTIONS:
        raise OrderTypeError(
            f"{owner}: action is one of {', '.join(ACTIONS)}, not {action!r}"
        )
    quantity = checkedDecimal(owner, "totalQuantity", totalQuantity)
    extra = checkedFields(owner, extra)
    modifiers: list[Modifier] = [m for m in (algo, routing, adjust) if m is not None]
    # Maps each field set by the order type or a modifier to who sets it,
    # for the error message when ``extra`` also sets it.
    setBy = dict.fromkeys(_CORE | set(spec.definingFields), f"{spec.title} sets it")
    setBy |= {p.field: f"its parameter {p.name} sets it" for p in spec.params}
    for m in modifiers:
        overlap = sorted(set(m.orderFields) & set(setBy))
        if overlap:
            raise OrderTypeError(
                f"{m.title} cannot also set "
                + "; ".join(f"{field} ({setBy[field]})" for field in overlap)
            )
        setBy |= dict.fromkeys(m.orderFields, f"{m.title} sets it")
    clash = sorted(set(extra) & set(setBy))
    if clash:
        raise OrderTypeError(
            f"{owner} cannot also take "
            + "; ".join(f"{field} ({setBy[field]})" for field in clash)
        )
    given = coerced(owner, spec.params, values)
    required(owner, spec.params, given)
    params = {p.name: p for p in spec.params}
    for group in spec.exactlyOne:
        if sum(params[name].given(given[name]) for name in group) != 1:
            raise OrderTypeError(f"{owner} needs exactly one of {', '.join(group)}")
    built = {
        "orderType": spec.orderType,
        "action": action,
        "totalQuantity": quantity,
        **spec.definingFields,
        **paramFields(spec.params, given),
        **extra,
    }
    for m in modifiers:
        if m.orderTypes and spec.orderType not in m.orderTypes:
            raise OrderTypeError(
                f"{m.title} works {', '.join(m.orderTypes)} orders, not {spec.title}"
            )
        for condition in m.conditions:
            value = built.get(condition.field, ORDER_DEFAULTS[condition.field])
            if value not in condition.allowed:
                raise OrderTypeError(
                    f"{m.title} needs {condition.field} in {condition.allowed!r}, "
                    f"not {value!r}"
                )
        built |= checkedFields(m.title, m.orderFields)
    return built
