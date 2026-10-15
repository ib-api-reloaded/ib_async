"""What an order type is, as data.

An :class:`OrderTypeSpec` describes one IBKR order type: its ``orderType``
code, the constructor parameters and the :class:`~ib_async.order.Order`
field each one sets, the fields that define the type besides the code, the
products and exchanges IBKR documents it for, and how stable it is. The
catalog of specs is the single source of truth: the order type
constructors and their documentation are generated from it, and
:func:`build` enforces it when an order is constructed.
"""

from __future__ import annotations

import dataclasses
import enum
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, ClassVar

from ..contract import TagValue
from ..order import Order, OrderComboLeg

# Every Order field's default: a field holding its default is unset.
ORDER_DEFAULTS: Mapping[str, Any] = {
    f.name: f.default_factory() if callable(f.default_factory) else f.default
    for f in dataclasses.fields(Order)
}


def isSet(field: str, value: Any) -> bool:
    """Whether ``value`` of Order ``field`` is set: anything but its
    default (so a price of 0 is set; an empty list or string is not)."""
    return value != ORDER_DEFAULTS[field]


# How TWS reports back an order an IB algo works, whatever its type; IBKR
# refuses it on a modification.
ALGO_ORDER_TYPE = "IBALGO"


def baseOrderType(order: Order) -> str:
    """``order.orderType``, except "LMT" for an algo order TWS reported as
    "IBALGO", as an application modifying live algo orders sends it."""
    return "LMT" if order.orderType == ALGO_ORDER_TYPE else order.orderType


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

    FIELD = "field"  # set on its field as given
    # A tag value: one TagValue in its field's list, encoded for IBKR.
    BOOL = "bool"  # sent as "1" / "0"
    INT = "int"
    FLOAT = "float"
    STR = "str"
    # A price per combo leg, set as orderComboLegs.
    LEG_PRICES = "legPrices"


# The Python types each tag kind takes (bool is not an int or float here).
_TAG_TYPES: Mapping[Kind, tuple[type, ...]] = {
    Kind.BOOL: (bool,),
    Kind.INT: (int,),
    Kind.FLOAT: (int, float, Decimal),
    Kind.STR: (str,),
}


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
    # The values IBKR accepts, when it names them (tag values only).
    allowed: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if bool(self.tag) != (self.kind in _TAG_TYPES):
            raise ValueError(f"{self.name}: a tag needs a tag kind, and only a tag")
        if self.allowed and not self.tag:
            raise ValueError(f"{self.name}: only tag values have allowed values")
        if self.field not in ORDER_DEFAULTS:
            raise ValueError(f"{self.name}: Order has no field {self.field}")

    def encode(self, value: Any) -> str:
        """``value`` as the tag value IBKR expects, checked against the
        parameter's kind and allowed values."""
        types = _TAG_TYPES[self.kind]
        if not isinstance(value, types) or (
            isinstance(value, bool) and self.kind is not Kind.BOOL
        ):
            raise OrderTypeError(f"{self.name} must be {self.kind}, not {value!r}")
        if self.allowed and value not in self.allowed:
            raise OrderTypeError(
                f"{self.name} is one of {', '.join(self.allowed)}, not {value!r}"
            )
        if self.kind is Kind.BOOL:
            return "1" if value else "0"
        return str(value)


def required(owner: str, params: tuple[Param, ...], values: Mapping[str, Any]) -> None:
    """Refuse a required parameter left None."""
    missing = [p.name for p in params if p.required and values[p.name] is None]
    if missing:
        raise OrderTypeError(f"{owner} needs {', '.join(missing)}")


def paramFields(params: tuple[Param, ...], values: Mapping[str, Any]) -> dict[str, Any]:
    """The Order fields the parameters' ``values`` set, each as its kind
    says; a None value leaves its parameter out."""
    fields: dict[str, Any] = {}
    for p in params:
        value = values.get(p.name)
        if value is None:
            continue
        if p.tag:
            fields.setdefault(p.field, []).append(TagValue(p.tag, p.encode(value)))
        elif p.kind is Kind.LEG_PRICES:
            fields[p.field] = [OrderComboLeg(price=Decimal(str(v))) for v in value]
        else:
            fields[p.field] = value
    return fields


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
    defining: tuple[tuple[str, Any], ...] = ()
    # Groups of optional parameters of which exactly one must be given.
    exactlyOne: tuple[tuple[str, ...], ...] = ()
    usage: str = ""
    products: tuple[str, ...] = ()
    exchanges: tuple[str, ...] = ()
    requires: str = ""
    # Constructor arguments for the generated example, as source text.
    example: str = ""

    @property
    def definingFields(self) -> Mapping[str, Any]:
        return dict(self.defining)

    def param(self, name: str) -> Param:
        return next(p for p in self.params if p.name == name)


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
    # Order fields that must hold one of these values for the algo, such as
    # tif in ("", "DAY") for Adaptive.
    conditions: tuple[tuple[str, tuple[Any, ...]], ...] = ()
    usage: str = ""
    products: tuple[str, ...] = ()
    example: str = ""


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


# Algo, Routing and Adjustment modify an order type: each sets Order fields
# the order type then cannot also be given, and may work only certain order
# types (orderType codes; empty for any) or need certain field values.


@dataclass(frozen=True, slots=True)
class Routing:
    """How SMART routes a combo (BAG) order: ``routing=`` of any order
    type placed for a combo contract."""

    params: tuple[TagValue, ...] = ()

    title: ClassVar[str] = "Combo routing"
    orderTypes: ClassVar[tuple[str, ...]] = ()
    conditions: ClassVar[tuple[tuple[str, tuple[Any, ...]], ...]] = ()

    @property
    def orderFields(self) -> dict[str, Any]:
        return {"smartComboRoutingParams": list(self.params)}


def buildRouting(params: tuple[Param, ...], values: Mapping[str, Any]) -> Routing:
    return Routing(
        tuple(paramFields(params, values).get("smartComboRoutingParams", []))
    )


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
    def conditions(self) -> tuple[tuple[str, tuple[Any, ...]], ...]:
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
    fields: tuple[tuple[str, Any], ...]

    orderTypes: ClassVar[tuple[str, ...]] = ADJUSTABLE
    conditions: ClassVar[tuple[tuple[str, tuple[Any, ...]], ...]] = ()

    @property
    def orderFields(self) -> dict[str, Any]:
        return dict(self.fields)


class OrderTypeError(ValueError):
    """An order type constructed with missing, conflicting or forbidden values."""


# Set on every order by build(); the fields an order type always fills.
_CORE = frozenset({"orderType", "action", "totalQuantity"})


def buildAlgo(spec: AlgoSpec, values: Mapping[str, Any]) -> Algo:
    """An Algo for ``spec`` from its parameter values (None leaves a
    parameter to IBKR's default)."""
    required(spec.className, spec.params, values)
    return Algo(spec, tuple(paramFields(spec.params, values).get("algoParams", [])))


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

    Refuses a missing required parameter, a broken exactly-one group,
    ``extra`` fields the order type or a modifier sets itself (its code,
    its defining fields, its parameters' fields), and a modifier that does
    not apply to the order type or whose conditions the order breaks."""
    modifiers = [m for m in (algo, routing, adjust) if m is not None]
    owned = _CORE | set(spec.definingFields) | {p.field for p in spec.params}
    owned |= {field for m in modifiers for field in m.orderFields}
    clash = sorted(set(extra) & owned)
    if clash:
        raise OrderTypeError(
            f"{spec.className} sets {', '.join(clash)} itself; "
            "pass them as its parameters or use Order(...)"
        )
    required(spec.className, spec.params, values)
    for group in spec.exactlyOne:
        given = [name for name in group if values[name] is not None]
        if len(given) != 1:
            raise OrderTypeError(
                f"{spec.className} needs exactly one of {', '.join(group)}"
            )
    built = {
        "orderType": spec.orderType,
        "action": action,
        "totalQuantity": totalQuantity,
        **spec.definingFields,
        **paramFields(spec.params, values),
        **extra,
    }
    for m in modifiers:
        if m.orderTypes and spec.orderType not in m.orderTypes:
            raise OrderTypeError(
                f"{m.title} works {', '.join(m.orderTypes)} orders, not {spec.title}"
            )
        for field, allowed in m.conditions:
            value = built.get(field, ORDER_DEFAULTS[field])
            if value not in allowed:
                raise OrderTypeError(
                    f"{m.title} needs {field} in {allowed!r}, not {value!r}"
                )
        built |= m.orderFields
    return built
