"""Generate the order type constructors and their documentation from the
catalog.

``ib_async/ordertypes/catalog.py`` is the single source of truth for the
order types ib_async builds. This writes, from it:

- ``ib_async/ordertypes/generated.py``: one typed function per order
  type, returning an ``Order``, that takes the order type's parameters
  (types taken from the Order fields they set) and validates them through
  ``spec.build``;
- ``docs/ordertypes.rst``: the documentation of every order type.

``--check`` writes nothing and exits 1 if either file is out of date
(``make ruff`` runs it).

Usage::

    uv run python scripts/generate_ordertypes.py [--check]
"""

from __future__ import annotations

import dataclasses
import sys
import textwrap
from collections.abc import Callable

import generating

from ib_async.order import Order
from ib_async.ordertypes.catalog import (
    ALGOS,
    CATALOG,
    COMBO_ROUTING,
    IBKR_ORDER_TYPES,
    NOT_BUILT,
    OPTIONS,
)
from ib_async.ordertypes.spec import (
    ADJUSTABLE,
    AlgoSpec,
    Kind,
    OrderTypeSpec,
    Param,
    Stability,
)

ROOT = generating.ROOT
MODULE = ROOT / "ib_async" / "ordertypes" / "generated.py"
DOCS = ROOT / "docs" / "ordertypes.rst"

FIELD_TYPES = {f.name: str(f.type) for f in dataclasses.fields(Order)}
QUANTITY = "Decimal | float | str"


KIND_TYPES = {Kind.BOOL: "bool", Kind.INT: "int", Kind.FLOAT: "float", Kind.STR: "str"}


def paramType(param: Param) -> str:
    """A parameter's annotation: for a tag value, from its kind (its allowed
    values as a Literal); otherwise from the type of the Order field it
    sets, Decimal fields also taking floats and strings (the Order coerces
    them)."""
    if param.kind is Kind.LEG_PRICES:
        base = f"Sequence[{QUANTITY}]"
    elif param.tag:
        base = (
            "Literal[" + ", ".join(repr(v) for v in param.allowed) + "]"
            if param.allowed
            else KIND_TYPES[param.kind]
        )
    else:
        base = FIELD_TYPES[param.field].removesuffix(" | None")
        if base == "Decimal":
            base = QUANTITY
    return base if param.required else f"{base} | None = None"


def parameters(params: tuple[Param, ...], extra: tuple[str, ...] = ()) -> list[str]:
    """Required parameters positionally, then the optional ones (and
    ``extra``) keyword-only."""
    required = [p for p in params if p.required]
    optional = [p for p in params if not p.required]
    lines = [f"    {p.name}: {paramType(p)}," for p in required]
    if optional or extra:
        lines.append("    *,")
        lines += [f"    {p.name}: {paramType(p)}," for p in optional]
        lines += [f"    {e}," for e in extra]
    return lines


def signature(spec: OrderTypeSpec) -> str:
    lines = ["    action: str,", f"    totalQuantity: {QUANTITY},"]
    lines += parameters(
        spec.params,
        (
            "algo: Algo | None = None",
            "routing: Routing | None = None",
            "adjust: Adjustment | None = None",
        ),
    )
    lines.append("    **kwargs: Any,")
    return "\n".join(lines)


# How a fact marks source text: as is in a docstring, as a literal on the
# docs page.
Mark = Callable[[str], str]


def plain(text: str) -> str:
    return text


def literal(text: str) -> str:
    return f"``{text}``"


def typeFacts(spec: OrderTypeSpec, mark: Mark) -> list[str]:
    """What an order type sets and needs, and where IBKR offers it."""
    facts = []
    if spec.definingFields:
        facts.append(
            "Sets "
            + ", ".join(mark(f"{k}={v!r}") for k, v in spec.definingFields.items())
        )
    if spec.exactlyOne:
        facts.append(
            "Exactly one of "
            + "; ".join(", ".join(mark(n) for n in g) for g in spec.exactlyOne)
        )
    if spec.products:
        facts.append(f"Products: {', '.join(spec.products)}")
    if spec.exchanges:
        facts.append(f"Exchanges: {', '.join(spec.exchanges)}")
    if spec.requires:
        facts.append(f"Requires {spec.requires}")
    return facts


def algoFacts(spec: AlgoSpec, mark: Mark) -> list[str]:
    """The order types an algo works, what it needs, and where."""
    facts = [f"Works {', '.join(spec.orderTypes)} orders"]
    facts += [f"Needs {condition(c.field, c.allowed, mark)}" for c in spec.conditions]
    if spec.products:
        facts.append(f"Products: {', '.join(spec.products)}")
    facts.append(f"Stability: {spec.stability}")
    return facts


def argsBlock(params: tuple[Param, ...]) -> str:
    """A docstring's Args section for ``params``."""
    return "\n".join(
        ["Args:"]
        + [
            textwrap.fill(
                f"{p.name}: {p.doc}" + ("" if p.required else " Optional."),
                width=76,
                initial_indent="    ",
                subsequent_indent="        ",
            )
            for p in params
        ]
    )


def algoExample(spec: AlgoSpec) -> str:
    """A limit order the algo works, as source text."""
    if "LMT" not in spec.orderTypes:
        raise SystemExit(f"{spec.className}: the example needs an algo working LMT")
    return f'LimitOrder("BUY", 100, 50.00, algo={spec.className}({spec.example}))'


def docstringOf(parts: list[str]) -> str:
    """The docstring of ``parts`` (paragraphs; one with a line break is
    kept as is), indented for a function body."""
    body = "\n\n".join(
        "\n".join(textwrap.wrap(p, 76)) if "\n" not in p else p for p in parts
    )
    return textwrap.indent(f'"""\n{body}\n"""', "    ").lstrip()


def docstring(spec: OrderTypeSpec) -> str:
    parts = [f"{spec.title} (``{spec.orderType}``): {spec.summary}"]
    if spec.usage:
        parts.append(spec.usage)
    facts = [*typeFacts(spec, plain), f"Stability: {spec.stability}"]
    parts.append(" ".join(f"{fact}." for fact in facts))
    if spec.params:
        parts.append(argsBlock(spec.params))
    parts.append(f"Example::\n\n    {spec.className}({spec.example})")
    return docstringOf(parts)


def functionSource(spec: OrderTypeSpec) -> str:
    values = ", ".join(f'"{p.name}": {p.name}' for p in spec.params)
    return f'''

def {spec.className}(
{signature(spec)}
) -> Order:
    {docstring(spec)}
    return Order(
        **build(
            SPECS["{spec.className}"], action, totalQuantity, {{{values}}}, kwargs, algo, routing, adjust
        )
    )
'''


def algoName(spec: AlgoSpec) -> str:
    """The algo's title, with its strategy code when that differs."""
    if spec.strategy == spec.title:
        return spec.title
    return f"{spec.title} (``{spec.strategy}``)"


def condition(field: str, allowed: tuple[object, ...], mark: Mark) -> str:
    if len(allowed) == 1:
        return mark(f"{field}={allowed[0]!r}")
    return f"{mark(field)} one of " + ", ".join(mark(repr(v)) for v in allowed)


def algoDocstring(spec: AlgoSpec) -> str:
    parts = [f"{algoName(spec)}: {spec.summary}"]
    if spec.usage:
        parts.append(spec.usage)
    parts.append(" ".join(f"{fact}." for fact in algoFacts(spec, plain)))
    if spec.params:
        parts.append(argsBlock(spec.params))
    parts.append(f"Example::\n\n    {algoExample(spec)}")
    return docstringOf(parts)


def algoSource(spec: AlgoSpec) -> str:
    values = ", ".join(f'"{p.name}": {p.name}' for p in spec.params)
    params = "\n".join(parameters(spec.params))
    return f'''

def {spec.className}(
{params}
) -> Algo:
    {algoDocstring(spec)}
    return buildAlgo(ALGO_SPECS["{spec.className}"], {{{values}}})
'''


def routingSource() -> str:
    values = ", ".join(f'"{p.name}": {p.name}' for p in COMBO_ROUTING)
    params = "\n".join(parameters(COMBO_ROUTING))
    doc = docstringOf(
        [
            "How SMART routes a combo (BAG) order: ``routing=`` of any order "
            "type placed for a combo contract. Each optional tag left as None "
            "is not sent.",
            argsBlock(COMBO_ROUTING),
            "Example::\n\n"
            '    LimitOrder("BUY", 1, 2.50, routing=ComboRouting(nonGuaranteed=True))',
        ]
    )
    return f"""

def ComboRouting(
{params}
) -> Routing:
    {doc}
    return buildRouting(COMBO_ROUTING, {{{values}}})
"""


def module() -> str:
    names = sorted(
        [*(s.className for s in CATALOG), *(a.className for a in ALGOS), "ComboRouting"]
    )
    header = (
        '''"""The order type and algo constructors, generated from ``catalog.py``
by ``scripts/generate_ordertypes.py``. Do not edit: change the catalog and
regenerate.

Each order type returns a plain ``Order``, so ``dataclasses.replace``,
copying and pickling work as for any order, and ``specOf`` tells its type.
Each algo returns an ``Algo``, for the ``algo=`` of the order types it
works."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal

from ..order import Order
from .catalog import ALGO_SPECS, COMBO_ROUTING, SPECS
from .spec import Adjustment, Algo, Routing, build, buildAlgo, buildRouting

__all__ = [
'''
        + "".join(f'    "{name}",\n' for name in names)
        + "]\n"
    )
    return generating.formatted(
        header
        + "".join(functionSource(spec) for spec in CATALOG)
        + "".join(algoSource(spec) for spec in ALGOS)
        + routingSource(),
        MODULE,
    )


TIERS = {
    Stability.STABLE: "Standard order types, broadly supported.",
    Stability.VENUE: "Order types of specific exchanges or venues.",
    Stability.ADVANCED: "Order types with many interacting parameters; "
    "test them before relying on them.",
}


def docs() -> str:
    lines = [
        ".. This page is generated from ib_async/ordertypes/catalog.py by",
        "   scripts/generate_ordertypes.py. Do not edit it.",
        "",
        ".. _ordertypes:",
        "",
        "Order types",
        "===========",
        "",
        "Each order type is a function that returns an ``Order`` with the fields "
        "IBKR expects for it. Its "
        "parameters are the values that order type needs; any other ``Order`` "
        "field (``tif``, ``outsideRth``, ``account``, ``cashQty``, "
        "``includeOvernight``, ...) is a keyword argument. An action IBKR "
        "does not take, a value that is not one its field holds (a price or "
        "quantity that is not a finite number, say), a missing required "
        "value, not exactly one of a pair where one is needed, a field the "
        "type or a modifier (``algo=``, ``routing=``, ``adjust=``) sets "
        "itself, or a modifier that does not apply raises ``OrderTypeError``.",
        "",
        "``ib_async.ordertypes.specOf(order)`` names the order type of any "
        "``Order``, and ``specsOf(order)`` every type of an order combining "
        "types (such as an IBKR ATS limit order on the open); "
        "``ib_async.ordertypes.checkOrder(contract, order)`` lists "
        "what IBKR says against an order for a contract, such as a product "
        "it is not listed for; given the contract's ``ContractDetails`` "
        "instead, also an order type its ``orderTypes`` does not "
        "list.",
        "",
        "For an order type not listed here, set the fields on ``Order`` "
        "directly: ``Order(orderType=..., action=..., totalQuantity=...)``.",
        "",
    ]
    for tier, about in TIERS.items():
        title = f"{str(tier).capitalize()} order types"
        lines += [title, "-" * len(title), "", about, ""]
        for spec in (s for s in CATALOG if s.stability == tier):
            heading = f"{spec.title} (``{spec.orderType}``)"
            lines += [heading, "^" * len(heading), "", spec.summary, ""]
            if spec.usage:
                lines += [spec.usage, ""]
            lines += [
                ".. code-block:: python",
                "",
                f"    {spec.className}({spec.example})",
                "",
            ]
            if spec.params:
                lines += [
                    ".. list-table::",
                    "   :header-rows: 1",
                    "",
                    "   * - Parameter",
                    "     - Order field",
                    "     - Meaning",
                ]
                for p in spec.params:
                    note = "" if p.required else " Optional."
                    lines += [
                        f"   * - ``{p.name}``",
                        f"     - ``{p.field}``",
                        f"     - {p.doc}{note}",
                    ]
                lines.append("")
            facts = typeFacts(spec, literal)
            lines += [*(f"- {fact}" for fact in facts), ""] if facts else []
    lines += comboDocs()
    lines += optionsDocs()
    lines += attachedDocs()
    lines += modifyDocs()
    lines += algoDocs()
    lines += coverageDocs()
    return "\n".join(lines).rstrip() + "\n"


def comboDocs() -> list[str]:
    lines = [
        "Combo orders",
        "------------",
        "",
        "Combo (BAG) contracts also take ordinary order types such as "
        "LimitOrder and MarketOrder; the combo order types above are the ones "
        "only combos take. How SMART routes a combo is set with "
        "``routing=ComboRouting(...)`` on the order type:",
        "",
        ".. code-block:: python",
        "",
        '    LimitOrder("BUY", 1, 2.50, routing=ComboRouting(nonGuaranteed=True))',
        "",
    ]
    return lines + tagTable(COMBO_ROUTING)


def tagTable(params: tuple[Param, ...]) -> list[str]:
    """The docs page's table of tag parameters (an algo's, combo
    routing's): each one's name, IBKR tag and kind, meaning, the values it
    takes when IBKR names them, and whether it is required."""
    lines = [
        ".. list-table::",
        "   :header-rows: 1",
        "",
        "   * - Parameter",
        "     - IBKR tag",
        "     - Meaning",
    ]
    for p in params:
        values = f" One of: {', '.join(p.allowed)}." if p.allowed else ""
        note = " Required." if p.required else ""
        lines += [
            f"   * - ``{p.name}``",
            f"     - ``{p.tag}`` ({p.kind})",
            f"     - {p.doc}{values}{note}",
        ]
    return [*lines, ""]


def algoDocs() -> list[str]:
    lines = [
        "IB algos",
        "--------",
        "",
        "An algo works an order of the types it lists (those IBKR shows it "
        "working): pass it as ``algo=`` to the order type. Its parameters are "
        "optional; IBKR uses its defaults for any left out. An algo the order "
        "type cannot take, or an order that breaks the algo's conditions, raises "
        "``OrderTypeError``; ``ib_async.ordertypes.algoOf(order)`` names the algo of any ``Order``.",
        "",
    ]
    for spec in ALGOS:
        heading = algoName(spec)
        lines += [heading, "^" * len(heading), "", spec.summary, ""]
        if spec.usage:
            lines += [spec.usage, ""]
        lines += [".. code-block:: python", "", f"    {algoExample(spec)}", ""]
        if spec.params:
            lines += tagTable(spec.params)
        lines += [f"- {fact}" for fact in algoFacts(spec, literal)] + [""]
    return lines


def optionsDocs() -> list[str]:
    lines = [
        "Order options",
        "-------------",
        "",
        "Fields any order type takes as keyword arguments.",
        "",
    ]
    for option in OPTIONS:
        lines += [option.title, "^" * len(option.title), "", option.summary, ""]
        if option.usage:
            lines += [option.usage, ""]
        lines += [".. code-block:: python", "", f"    {option.example}", ""]
        facts = ["Fields: " + ", ".join(f"``{f}``" for f in option.fields)]
        if option.products:
            facts.append(f"Products: {', '.join(option.products)}")
        facts.append(f"Stability: {option.stability}")
        lines += [f"- {fact}" for fact in facts] + [""]
    return lines


def attachedDocs() -> list[str]:
    lines = [
        "Attached orders",
        "---------------",
        "",
        "``IB.bracketOrder`` builds a bracket. An adjustable stop changes once, "
        "when the price penetrates its trigger price: pass an adjustment as "
        "``adjust=`` to a stop, stop limit or trailing stop order type "
        f"({', '.join(ADJUSTABLE)}). An FX hedge is a market order for 0 "
        "attached to its parent, placed on the currency pair's contract.",
        "",
    ]
    for name in ("AdjustToStop", "AdjustToStopLimit", "AdjustToTrail", "FxHedgeOrder"):
        lines += [f".. autofunction:: ib_async.ordertypes.{name}", ""]
    return lines


def modifyDocs() -> list[str]:
    return [
        "Modifying orders",
        "----------------",
        "",
        "To modify a live order, send it again with ``ib.placeOrder`` and the "
        "same orderId. Sending the order back as TWS reports it fails for "
        "fields TWS fills in; ``modifiedOrder`` prepares it.",
        "",
        ".. autofunction:: ib_async.ordertypes.modifiedOrder",
        "",
    ]


def coverageDocs() -> list[str]:
    """Every code of IBKR's client, the order types that send it, or why
    none does."""
    built: dict[str, list[str]] = {}
    for spec in CATALOG:
        built.setdefault(spec.orderType, []).append(spec.className)
    # (The catalog checks on import that every code is in IBKR's table,
    # and either built or said why not.)

    def codeCell(code: str) -> str:
        """The code, with its other spellings when it has any."""
        spellings = IBKR_ORDER_TYPES[code]
        others = f" ({', '.join(f'``{s}``' for s in spellings)})" if spellings else ""
        return f"``{code}``{others}"

    def table(header: str, rows: dict[str, str]) -> list[str]:
        lines = [
            ".. list-table::",
            "   :header-rows: 1",
            "",
            "   * - Code (other spellings)",
            f"     - {header}",
        ]
        for code, cell in rows.items():
            lines += [f"   * - {codeCell(code)}", f"     - {cell}"]
        return [*lines, ""]

    return [
        "IBKR order type codes",
        "---------------------",
        "",
        "Every IBKR order type code, with the "
        "other spellings IBKR and contract details use for it.",
        "",
        "Built",
        "^^^^^",
        "",
        *table(
            "Order types",
            {
                code: ", ".join(f"``{name}``" for name in built[code])
                for code in IBKR_ORDER_TYPES
                if code in built
            },
        ),
        "Not built",
        "^^^^^^^^^",
        "",
        "For these, set the fields on ``Order`` directly.",
        "",
        *table("Why not", {code: NOT_BUILT[code] for code in NOT_BUILT}),
    ]


def main(argv: list[str] | None = None) -> int:
    return generating.main(
        __doc__.split("\n\n")[0],
        "generate_ordertypes.py",
        lambda: {MODULE: module(), DOCS: docs()},
        argv,
    )


if __name__ == "__main__":
    sys.exit(main())
