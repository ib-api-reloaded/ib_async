"""Round-trip tests for the protobuf Order and Contract encoders.

For generated Orders and Contracts, every field the proto carries must be
unchanged after encoding and decoding. A price sent as a double reads back
as the same Decimal, a quantity sent as a string reads back as the same
Decimal, and ids, flags and codes read back as sent.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._pb import Contract_pb2, Order_pb2
from ib_async._proto.contracts import createContract, createContractProto
from ib_async._proto.orders import createOrder, createOrderProto
from ib_async.order import ORDER_FIELD_TYPES, Order
from ib_async.util import dataclassAsDict
from tests._property import examples

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


def orderField(name: str, kind: type) -> st.SearchStrategy:
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


def comparable(value: object) -> object:
    """Convert numbers to Decimal for comparison; return others unchanged."""
    if isinstance(value, float | Decimal):
        return Decimal(str(value))
    return value


@given(order=orders())
@examples(300)
def test_order_round_trip(order):
    sent = dataclassAsDict(order)
    proto = createOrderProto(order)
    decoded = createOrder(proto, orderId=order.orderId)
    assert decoded.orderId == order.orderId
    for name in SCALAR_FIELDS:
        if proto.HasField(name):
            assert comparable(getattr(decoded, name)) == comparable(sent[name]), name


@st.composite
def contracts(draw: st.DrawFn) -> ibi.Contract:
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


@given(contract=contracts())
@examples(300)
def test_contract_round_trip(contract):
    proto = createContractProto(contract)
    assert isinstance(proto, Contract_pb2.Contract)
    decoded = createContract(proto)
    assert dataclassAsDict(decoded) == dataclassAsDict(contract)
