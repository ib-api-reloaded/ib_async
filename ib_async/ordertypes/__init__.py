"""IBKR order types as typed, documented, validated constructors.

Each order type here returns an :class:`~ib_async.order.Order` built from
one entry of the catalog (``catalog.py``), which records the order type's
IBKR code, the fields it sets, and the products IBKR documents it for; the
catalog also describes IB algos, combo routing and the order options.
``attached.py`` builds adjustable stops and FX hedges.
``docs/ordertypes.rst`` describes them all.

Beyond constructing orders:

- :func:`specOf` tells what order type an ``Order`` is, whichever way it
  was made (useful for logs, and for orders read back from TWS), and
  :func:`specsOf` every type an order combining types is;
- :func:`checkOrder` lists what IBKR says against sending an order for a
  contract (a product or exchange it is not offered for, or, from the
  contract's details, an order type they do not list);
- :func:`modifiedOrder` prepares an order TWS reported back for sending
  again as a modification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..contract import ContractDetails
from .attached import AdjustToStop, AdjustToStopLimit, AdjustToTrail, FxHedgeOrder
from .catalog import (
    ALGO_BY_STRATEGY,
    ALGOS,
    CATALOG,
    IBKR_ORDER_TYPES,
    NOT_BUILT,
    OPTIONS,
    SPECS,
)
from .generated import *  # noqa: F403  (the order types and algos)
from .generated import __all__ as _classes
from .modify import SERVER_FILLED, modifiedOrder
from .spec import (
    ACTIONS,
    Adjustment,
    Algo,
    AlgoSpec,
    FieldIn,
    FieldValue,
    Kind,
    OptionSpec,
    OrderTypeError,
    OrderTypeSpec,
    Param,
    Routing,
    Stability,
    baseOrderType,
    isSet,
)

if TYPE_CHECKING:
    from ..contract import Contract
    from ..order import Order


def specsOf(order: Order) -> list[OrderTypeSpec]:
    """The catalog's order types ``order`` is: those whose code, defining
    fields and required parameters it has, each parameter a value the
    type's constructor takes, the most specific only (a type whose defining
    fields and required parameters another one has too is left out).
    Several for an order combining types, such as an IBKR ATS limit order
    on the open; none for an order type outside the catalog, or one without
    a required parameter set."""
    return _mostSpecific(
        [
            spec
            for spec in _sameKind(order)
            if all(isSet(f, getattr(order, f)) for f in spec.requiredFields)
            and all(
                _takes(p, getattr(order, p.field)) for p in spec.params if p.required
            )
        ]
    )


def _takes(param: Param, value: object) -> bool:
    """Whether ``param``'s constructor argument may be ``value``, as an
    order holds it (an up-to-mid order's infinite competeAgainstBestOffset
    is no Pegged to Best order's); a tag value or leg prices, held as a
    list, is judged by its being set."""
    if param.tag or param.kind is Kind.LEG_PRICES:
        return True
    try:
        param.coerce(param.name, value)
    except OrderTypeError:
        return False
    return True


def specOf(order: Order) -> OrderTypeSpec | None:
    """The catalog's order type for ``order``, when it is one (see
    :func:`specsOf`); None for an order type outside the catalog, one
    without a required parameter set or with one its constructor would
    refuse, or an order combining types."""
    specs = specsOf(order)
    return specs[0] if len(specs) == 1 else None


def _sameKind(order: Order) -> list[OrderTypeSpec]:
    """The order types whose code and defining fields ``order`` has,
    whatever its parameters."""
    return [
        spec
        for spec in CATALOG
        if spec.orderType == baseOrderType(order)
        and all(getattr(order, d.field) == d.value for d in spec.defining)
    ]


def _covers(a: OrderTypeSpec, b: OrderTypeSpec) -> bool:
    """Whether ``a`` is at least as specific as ``b``: it has ``b``'s
    defining values, and pins every field ``b`` pins (by a defining value
    or a required parameter)."""
    return set(b.defining) <= set(a.defining) and _pinned(b) <= _pinned(a)


def _pinned(spec: OrderTypeSpec) -> frozenset[str]:
    return spec.requiredFields | set(spec.definingFields)


def _mostSpecific(specs: list[OrderTypeSpec]) -> list[OrderTypeSpec]:
    return [
        s for s in specs if not any(_covers(o, s) and not _covers(s, o) for o in specs)
    ]


def _leastSpecific(specs: list[OrderTypeSpec]) -> list[OrderTypeSpec]:
    return [
        s for s in specs if not any(_covers(s, o) and not _covers(o, s) for o in specs)
    ]


def algoOf(order: Order) -> AlgoSpec | None:
    """The catalog's algo working ``order``, if any; None for no algo or
    one outside the catalog. (IBKR reports an order worked by an algo with
    orderType "IBALGO".)"""
    return ALGO_BY_STRATEGY.get(order.algoStrategy) if order.algoStrategy else None


def checkOrder(target: Contract | ContractDetails, order: Order) -> list[str]:
    """What IBKR says against sending ``order`` for a contract.

    From IBKR's documentation, for a :class:`Contract`: an order type or
    algo it does not list for the contract's product, an order type it does
    not list for the exchange, combo routing on a contract that is not a
    combo. A combo's products are its legs', which a BAG contract does not
    say, so a combo's order type and algo are not product-checked.

    Given the contract's :class:`ContractDetails` (``ib.reqContractDetails``),
    also an order type its ``orderTypes`` does not list, in any of IBKR's
    spellings (``IBKR_ORDER_TYPES``). An empty list says nothing.

    Advice, not a rule: IBKR's lists are not complete, and TWS has the
    final word."""
    details: ContractDetails | None
    contract: Contract | None
    if isinstance(target, ContractDetails):
        details, contract = target, target.contract
    else:
        details, contract = None, target
    problems = []
    if contract is not None:
        problems += _documented(contract, order)
    if details and details.orderTypes:
        problems += _listed(set(details.orderTypes.split(",")), order)
    return problems


def _documented(contract: Contract, order: Order) -> list[str]:
    problems = []
    # The product to check order types and algos against, if one is known.
    product = "" if contract.secType == "BAG" else contract.secType
    if order.smartComboRoutingParams and product:
        problems.append(
            f"combo routing applies to combo (BAG) contracts, not {product}"
        )
    algo = algoOf(order)
    if algo and algo.products and product and product not in algo.products:
        problems.append(
            f"{algo.title} is documented for {', '.join(algo.products)}, not {product}"
        )
    specs = specsOf(order)
    if specs:
        # The order is each of these types: each one's limits apply.
        for spec in specs:
            problems += _offered(spec, product, contract.exchange)
        return problems
    # An order missing a parameter its type requires (TWS will say what):
    # what every least specific type of its code says against it.
    complaints = [
        _offered(spec, product, contract.exchange)
        for spec in _leastSpecific(_sameKind(order))
    ]
    if complaints and all(complaints):
        problems += complaints[0]
    return problems


def _offered(spec: OrderTypeSpec, product: str, exchange: str) -> list[str]:
    """What ``spec``'s documented products and exchanges say against
    ``product`` and ``exchange`` (either empty when not known)."""
    problems = []
    if spec.products and product and product not in spec.products:
        problems.append(
            f"{spec.title} is documented for {', '.join(spec.products)}, not {product}"
        )
    if spec.exchanges and exchange and exchange not in spec.exchanges:
        problems.append(
            f"{spec.title} is offered on {', '.join(spec.exchanges)}, not {exchange}"
        )
    return problems


def _listed(listed: set[str], order: Order) -> list[str]:
    code = baseOrderType(order)
    if code and not listed & {code, *IBKR_ORDER_TYPES.get(code, ())}:
        return [f"the contract's order types do not list {code}"]
    return []


__all__ = [
    *_classes,
    "ACTIONS",
    "ALGOS",
    "AdjustToStop",
    "AdjustToStopLimit",
    "AdjustToTrail",
    "Adjustment",
    "Algo",
    "AlgoSpec",
    "CATALOG",
    "FieldIn",
    "FieldValue",
    "FxHedgeOrder",
    "IBKR_ORDER_TYPES",
    "Kind",
    "NOT_BUILT",
    "OPTIONS",
    "OptionSpec",
    "OrderTypeError",
    "OrderTypeSpec",
    "Param",
    "Routing",
    "SERVER_FILLED",
    "SPECS",
    "Stability",
    "algoOf",
    "checkOrder",
    "modifiedOrder",
    "specOf",
    "specsOf",
]
