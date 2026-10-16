"""Hypothesis strategies shared by the tests. They generate codes, prices,
quantities, Orders and Contracts."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import strategies as st

import ib_async as ibi
from ib_async._pb import Order_pb2
from ib_async.order import ORDER_FIELD_TYPES, Order, OrderScalar

codes = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ", min_size=1, max_size=6
)
prices = st.decimals(Decimal("0.01"), Decimal(100000), places=2)
quantities = st.decimals(Decimal("0.0001"), Decimal(1000000), places=4)

# Order fields that the Order proto does not carry.
NOT_ON_THE_WIRE = {
    "orderId",  # sent in the request envelope and passed to the decoder
    "auctionStrategy",  # IBKR's Order proto has no such field
}


def orderField(
    name: str, kind: OrderScalar
) -> st.SearchStrategy[Decimal | float | int | bool | str]:
    if kind is Decimal:
        return quantities if "Quantity" in name or name == "cashQty" else prices
    if kind is float:
        return st.floats(0.01, 1000).map(lambda f: round(f, 4))
    if kind is int:
        return st.integers(0, 1000)
    if kind is bool:
        return st.booleans()
    return codes


SCALAR_FIELDS = sorted(
    name
    for name in ORDER_FIELD_TYPES
    if name not in NOT_ON_THE_WIRE and name in Order_pb2.Order.DESCRIPTOR.fields_by_name
)


@st.composite
def orders(draw: st.DrawFn) -> Order:
    """An Order with a random selection of its scalar fields set."""
    chosen = draw(st.lists(st.sampled_from(SCALAR_FIELDS), max_size=12, unique=True))
    values = {name: draw(orderField(name, ORDER_FIELD_TYPES[name])) for name in chosen}
    return Order(orderId=draw(st.integers(1, 10**6)), **values)


@st.composite
def contracts(draw: st.DrawFn) -> ibi.Contract:
    """A Contract of a random security type. A bag gets combo legs. Some
    contracts get a delta-neutral contract."""
    secType = draw(st.sampled_from(["STK", "OPT", "FUT", "CASH", "BAG", "CONTFUT"]))
    legs = []
    if secType == "BAG":
        legs = draw(
            st.lists(
                st.builds(
                    ibi.ComboLeg,
                    conId=st.integers(1, 10**6),
                    ratio=st.integers(1, 5),
                    action=st.sampled_from(["BUY", "SELL"]),
                    exchange=st.sampled_from(["SMART", "CME"]),
                ),
                min_size=1,
                max_size=3,
            )
        )
    deltaNeutral = draw(
        st.one_of(
            st.none(),
            st.builds(
                ibi.DeltaNeutralContract,
                conId=st.integers(1, 10**6),
                delta=st.floats(-1, 1).map(lambda d: round(d, 3)),
                price=st.floats(0.01, 1000).map(lambda p: round(p, 2)),
            ),
        )
    )
    return ibi.Contract(
        secType=secType,
        conId=draw(st.integers(0, 10**7)),
        symbol=draw(codes),
        lastTradeDateOrContractMonth=draw(st.sampled_from(["", "202612", "20261218"])),
        strike=draw(st.floats(0, 5000).map(lambda s: round(s, 2))),
        right=draw(st.sampled_from(["", "C", "P"])),
        multiplier=draw(st.sampled_from(["", "100", "50", "0.5"])),
        exchange=draw(st.sampled_from(["", "SMART", "CME", "ISLAND"])),
        currency=draw(st.sampled_from(["USD", "EUR", ""])),
        localSymbol=draw(codes),
        tradingClass=draw(codes),
        comboLegs=legs,
        deltaNeutralContract=deltaNeutral,
    )


def _withNoneConId(contract: ibi.Contract) -> ibi.Contract:
    contract.conId = None  # type: ignore[assignment]
    return contract


# Contracts as users write them. They may be unqualified, partly filled,
# or have None where a number belongs. Each example builds a new object
# because a request may change the contract it is given.
userContracts = st.one_of(
    contracts(),
    st.builds(lambda: ibi.Stock("AAPL")),
    st.builds(lambda: ibi.Stock("AAPL", "SMART", "USD")),
    st.builds(lambda: ibi.Forex("EURUSD")),
    st.builds(lambda: ibi.Index("SPX", "CBOE")),
    st.builds(lambda: ibi.Future("ES", "202612", "CME")),
    st.builds(lambda: ibi.Option("SPY", "20261218", 450, "C", "SMART")),
    st.builds(lambda: ibi.Option("SPY", "20261218", 0, "", "SMART")),
    st.builds(ibi.Bag),
    st.builds(lambda: ibi.Contract(conId=265598)),
    st.builds(ibi.Contract),
    st.builds(ibi.Stock, symbol=codes, exchange=st.just("SMART")).map(_withNoneConId),
)
