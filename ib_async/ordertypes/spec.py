"""What an order type is, as data.

An :class:`OrderTypeSpec` describes one IBKR order type: its ``orderType``
code, the constructor parameters and the :class:`~ib_async.order.Order`
field each one sets, the fields that define the type besides the code, the
products and exchanges IBKR documents it for, and how stable it is. The
catalog of specs is the single source of truth: the order type
constructors and their documentation are generated from it, and
:func:`build` enforces it when an order is constructed. Each spec checks
the names it refers to when it is defined, so a mistake in the catalog
fails on import, not on first use.

Values are checked as an order's values (:func:`checkedValue`): a price
or quantity is a finite number, a count a whole number, a flag a bool, a
code a string. What the Order would otherwise silently unset or misread
is refused with an :class:`OrderTypeError` naming the constructor and the
parameter.
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
    """Whether ``value`` of Order ``field`` is set: anything but None and
    the field's default. A price of 0 is set where the field's default is
    None; where the default is 0 (a field 0 means "none" for), 0 is
    unset."""
    return value is not None and value != ORDER_DEFAULTS[field]


def unset(field: str) -> Any:
    """Order ``field``'s default, its unset value (made fresh where Order
    makes it fresh: a list, a SoftDollarTier)."""
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
    """``value`` as a float when it is a finite real number (an int, a
    float, a Decimal, numpy's numbers; a bool is not); else None."""
    if isinstance(value, bool) or not isinstance(value, numbers.Real | Decimal):
        return None
    try:
        real = float(value)
    except OverflowError:
        return None
    return real if math.isfinite(real) else None


def _wholeNumber(value: Any) -> int | None:
    """``value`` as an int when it is a whole number (an int, numpy's, or
    a real number of whole value such as 100.0 or Decimal(100); a bool is
    not); else None."""
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
        """``value`` as the tag value IBKR expects, checked against the
        parameter's kind and allowed values (refusals name ``owner``)."""
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
        """``value`` as this parameter puts it into the Order: a tag
        value's TagValue, leg prices' OrderComboLegs, a field's value as
        the field holds it (see :func:`checkedValue`); None for None.

        Refuses what the Order would otherwise silently unset or misread:
        NaN, infinity, a value that is not a number."""
        if value is None:
            return None
        if self.tag:
            return TagValue(self.tag, self.encode(owner, value))
        if self.kind is Kind.LEG_PRICES:
            return _legs(owner, self, value)
        return checkedValue(owner, self.name, self.field, value)

    def given(self, value: Any) -> bool:
        """Whether the coerced ``value`` gives this parameter: not None,
        and for a plain field not the field's unset default either, as
        :func:`isSet` judges an order's fields."""
        return value is not None and (
            self.kind is not Kind.FIELD or isSet(self.field, value)
        )


def checkedDecimal(owner: str, name: str, value: Any) -> Decimal:
    """``value`` of ``name`` as the finite Decimal an Order holds (a number,
    or a string of one); refused when it is not (NaN, infinity, a string
    that does not parse), which the Order would silently unset."""
    number = finiteDecimal(value)
    if number is None:
        raise OrderTypeError(f"{owner}: {name} must be a finite number, not {value!r}")
    return number


def checkedValue(
    owner: str, name: str, field: str, value: Any, *, infinity: bool = False
) -> Any:
    """``value``, given as ``name``, as Order ``field`` holds it: a Decimal
    field a finite number (a string of one too), and +Infinity where IBKR
    gives it a meaning when ``infinity`` allows it; a float field a finite
    real number (as a float); an int field a whole number (as an int); a
    bool field True or False; a str field a string; any other field (a
    list, a record) the value as given, as is None.

    Refuses what the Order would silently unset (NaN, infinity, a string
    that is not a number) or misread (a float field's string, an int
    field's fraction, a bool field's "false")."""
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
    """Order ``fields`` (by field name), each checked as
    :func:`checkedValue` says, +Infinity allowed where IBKR gives it a
    meaning; None is the field's unset value (its default)."""
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
    """One OrderComboLeg per price of the list ``prices``, each a finite
    number, in the legs' order; at least one."""
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
    """The Order fields for ``spec``, from its parameter ``values`` (by
    parameter name) and any other Order fields in ``extra``, modified by an
    ``algo``, combo ``routing`` and an ``adjust``-ment.

    Refuses an action IBKR does not take, a quantity or a price that is
    not a finite number, a missing required parameter, a broken
    exactly-one group, ``extra`` fields the order type or a modifier sets
    itself (its code, its defining fields, its parameters' fields), a
    modifier that sets one of the order type's own fields, and a modifier
    that does not apply to the order type or whose conditions the order
    breaks."""
    owner = spec.className
    if action not in ACTIONS:
        raise OrderTypeError(
            f"{owner}: action is one of {', '.join(ACTIONS)}, not {action!r}"
        )
    quantity = checkedDecimal(owner, "totalQuantity", totalQuantity)
    extra = checkedFields(owner, extra)
    modifiers: list[Modifier] = [m for m in (algo, routing, adjust) if m is not None]
    # Who sets each field the order type or a modifier sets, to say why an
    # extra field cannot also be given.
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
