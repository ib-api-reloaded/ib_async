"""IBKR order types as typed, documented, validated constructors.

Each order type here returns an :class:`~ib_async.order.Order` built from
one entry of the catalog (``catalog.py``), which records the order type's
IBKR code, the fields it sets, and the products IBKR documents it for; the
catalog also describes IB algos, combo routing and the order options. ``attached.py`` builds adjustable stops and
FX hedges. ``docs/ordertypes.rst`` describes them all.

Beyond constructing orders:

- :func:`specOf` tells what order type an ``Order`` is, whichever way it
  was made (useful for logs, and for orders read back from TWS);
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
    Adjustment,
    Algo,
    AlgoSpec,
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


def specOf(order: Order) -> OrderTypeSpec | None:
    """The catalog's order type for ``order``: the most specific one whose
    code, defining fields and required parameters match; None for an order
    type outside the catalog."""
    matches = [
        spec
        for spec in CATALOG
        if spec.orderType == baseOrderType(order)
        and all(getattr(order, f) == v for f, v in spec.defining)
        and all(
            isSet(p.field, getattr(order, p.field)) for p in spec.params if p.required
        )
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda s: (len(s.defining), sum(p.required for p in s.params)),
    )


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
    spec = specOf(order)
    if spec is None:
        return problems
    if spec.products and product and product not in spec.products:
        problems.append(
            f"{spec.title} is documented for {', '.join(spec.products)}, not {product}"
        )
    if spec.exchanges and contract.exchange and contract.exchange not in spec.exchanges:
        problems.append(
            f"{spec.title} is offered on {', '.join(spec.exchanges)}, "
            f"not {contract.exchange}"
        )
    return problems


def _listed(listed: set[str], order: Order) -> list[str]:
    code = baseOrderType(order)
    if code and not listed & {code, *IBKR_ORDER_TYPES.get(code, ())}:
        return [f"the contract's order types do not list {code}"]
    return []


__all__ = [
    *_classes,
    "ALGOS",
    "AdjustToStop",
    "AdjustToStopLimit",
    "AdjustToTrail",
    "Adjustment",
    "Algo",
    "AlgoSpec",
    "CATALOG",
    "FxHedgeOrder",
    "IBKR_ORDER_TYPES",
    "NOT_BUILT",
    "OPTIONS",
    "OptionSpec",
    "SERVER_FILLED",
    "SPECS",
    "OrderTypeError",
    "OrderTypeSpec",
    "Param",
    "Routing",
    "Stability",
    "algoOf",
    "checkOrder",
    "modifiedOrder",
    "specOf",
]
