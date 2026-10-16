"""Round-trip tests for the protobuf Order and Contract encoders.

For generated Orders and Contracts, every field the proto carries must be
unchanged after encoding and decoding. A price sent as a double reads back
as the same Decimal, a quantity sent as a string reads back as the same
Decimal, and ids, flags and codes read back as sent.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given

from ib_async._pb import Contract_pb2
from ib_async._proto.contracts import createContract, createContractProto
from ib_async._proto.orders import createOrder, createOrderProto
from ib_async.util import dataclassAsDict
from tests._property import examples
from tests._strategies import SCALAR_FIELDS, contracts, orders


def comparable(value: object) -> object:
    """Convert numbers to Decimal for comparison; return others unchanged."""
    if isinstance(value, float | Decimal):
        return Decimal(str(value))
    return value


@given(order=orders())
@examples()
def test_order_round_trip(order):
    sent = dataclassAsDict(order)
    proto = createOrderProto(order)
    decoded = createOrder(proto, orderId=order.orderId)
    assert decoded.orderId == order.orderId
    for name in SCALAR_FIELDS:
        if proto.HasField(name):
            assert comparable(getattr(decoded, name)) == comparable(sent[name]), name


@given(contract=contracts())
@examples()
def test_contract_round_trip(contract):
    proto = createContractProto(contract)
    assert isinstance(proto, Contract_pb2.Contract)
    decoded = createContract(proto)
    assert dataclassAsDict(decoded) == dataclassAsDict(contract)
