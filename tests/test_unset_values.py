"""A field holding IBKR's unset value reads as absent.

IBKR's clients send a field they did not set as absent; when one arrives
holding the unset value for its type (UNSET_INTEGER in a 32-bit field,
UNSET_LONG in a 64-bit one, UNSET_DOUBLE in a double), the decoder clears
it before any converter runs, so no domain object or wrapper call carries
the magic number. On the way out, a value equal to UNSET_DOUBLE, also as a
Decimal, is left off the wire.
"""

from __future__ import annotations

import dataclasses
import math
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest
from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.message import Message

import ib_async as ibi
from ib_async._pb import (
    ComboLeg_pb2,
    Contract_pb2,
    OpenOrder_pb2,
    Order_pb2,
    SecDefOptParameter_pb2,
)
from ib_async._proto.orders import createPlaceOrderRequestProto
from ib_async._proto.safe import clear_unset_fields
from ib_async.decoder import (
    _PROTO_MESSAGES,
    _PROTO_MSG_CLASSES,
    Decoder,
    _initProtoMsgClasses,
)
from ib_async.order import OrderComboLeg
from ib_async.util import UNSET_DOUBLE, UNSET_INTEGER, UNSET_LONG

UNSET_STRINGS = {"2147483647", "9223372036854775807", "1.7976931348623157e+308"}


def test_each_unset_value_is_cleared_for_its_type() -> None:
    order = Order_pb2.Order(
        clientId=UNSET_INTEGER, permId=UNSET_LONG, lmtPrice=UNSET_DOUBLE
    )
    clear_unset_fields(order)
    assert not order.HasField("clientId")
    assert not order.HasField("permId")
    assert not order.HasField("lmtPrice")


def test_values_that_are_not_unset_stay() -> None:
    """2147483647 is a value in a 64-bit field; 0, -1, NaN and infinity
    are values too (+Infinity is compete-up-to-mid)."""
    order = Order_pb2.Order(
        permId=UNSET_INTEGER,
        clientId=-1,
        parentId=0,
        competeAgainstBestOffset=math.inf,
        auxPrice=-math.inf,
    )
    order.lmtPrice = math.nan
    clear_unset_fields(order)
    assert order.permId == UNSET_INTEGER
    assert (order.clientId, order.parentId) == (-1, 0)
    assert order.competeAgainstBestOffset == math.inf
    assert order.auxPrice == -math.inf
    assert math.isnan(order.lmtPrice)


def test_nested_and_repeated_fields_are_cleared() -> None:
    contract = Contract_pb2.Contract(conId=UNSET_INTEGER, strike=UNSET_DOUBLE)
    contract.comboLegs.append(ComboLeg_pb2.ComboLeg(conId=UNSET_INTEGER, ratio=1))
    message = OpenOrder_pb2.OpenOrder(orderId=1, contract=contract)
    clear_unset_fields(message)
    assert not message.contract.HasField("conId")
    assert not message.contract.HasField("strike")
    [leg] = message.contract.comboLegs
    assert not leg.HasField("conId") and leg.ratio == 1

    parameter = SecDefOptParameter_pb2.SecDefOptParameter(
        strikes=[100.0, UNSET_DOUBLE, 105.0]
    )
    clear_unset_fields(parameter)
    assert list(parameter.strikes) == [100.0, 105.0]


def _setUnset(message: Message, depth: int = 0) -> None:
    """Set every numeric field of ``message``, nested messages included,
    to IBKR's unset value for its type."""
    unsetByType = {
        FieldDescriptor.CPPTYPE_INT32: UNSET_INTEGER,
        FieldDescriptor.CPPTYPE_UINT32: UNSET_INTEGER,
        FieldDescriptor.CPPTYPE_INT64: UNSET_LONG,
        FieldDescriptor.CPPTYPE_UINT64: UNSET_LONG,
        FieldDescriptor.CPPTYPE_DOUBLE: UNSET_DOUBLE,
    }
    for field in message.DESCRIPTOR.fields:
        if field.message_type is not None and field.message_type.GetOptions().map_entry:
            continue
        if field.cpp_type == FieldDescriptor.CPPTYPE_MESSAGE:
            if depth < 5:
                child = getattr(message, field.name)
                if field.is_repeated:
                    _setUnset(child.add(), depth + 1)
                else:
                    _setUnset(child, depth + 1)
                    child.SetInParent()
            continue
        unset = unsetByType.get(field.cpp_type)
        if unset is None:
            continue
        if field.is_repeated:
            getattr(message, field.name).append(unset)
        else:
            setattr(message, field.name, unset)


def _isUnset(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in (UNSET_INTEGER, UNSET_LONG)
    if isinstance(value, float):
        return value == UNSET_DOUBLE
    if isinstance(value, Decimal):
        return value.is_finite() and float(value) == UNSET_DOUBLE
    if isinstance(value, str):
        return value in UNSET_STRINGS
    return False


def _unsetValuesIn(value: object, path: str) -> list[str]:
    """The paths of every unset value inside ``value``."""
    if _isUnset(value):
        return [path]
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [
            found
            for f in dataclasses.fields(value)
            for found in _unsetValuesIn(getattr(value, f.name), f"{path}.{f.name}")
        ]
    if isinstance(value, list | tuple):
        return [
            found
            for i, item in enumerate(value)
            for found in _unsetValuesIn(item, f"{path}[{i}]")
        ]
    return []


@pytest.mark.parametrize("msgId", sorted(_PROTO_MESSAGES))
def test_no_unset_value_reaches_the_wrapper(msgId: int) -> None:
    _initProtoMsgClasses()
    message = _PROTO_MSG_CLASSES[msgId]()
    _setUnset(message)
    wrapper = MagicMock()
    wrapper.requests.set_error = MagicMock()
    Decoder(wrapper).processProtoBuf(msgId, message.SerializeToString())

    calls: list[call] = list(wrapper.mock_calls)
    found = [
        hit
        for name, args, _ in calls
        for i, arg in enumerate(args)
        for hit in _unsetValuesIn(arg, f"{name}[{i}]")
    ]
    assert found == []
    wrapper.requests.set_error.assert_not_called()


def test_an_unset_order_price_is_none_and_left_off_the_wire() -> None:
    """A cached order IBKR filled with its unset double (the typed
    constructors such as LimitOrder refuse it outright)."""
    order = ibi.Order(action="BUY", orderType="LMT", lmtPrice=UNSET_DOUBLE)
    assert order.lmtPrice is None
    # Set after construction, the Decimal is kept; the wire leaves it off.
    order.auxPrice = Decimal(repr(UNSET_DOUBLE))
    proto = createPlaceOrderRequestProto(1, ibi.Stock("SPY", "SMART", "USD"), order)
    assert not proto.order.HasField("lmtPrice")
    assert not proto.order.HasField("auxPrice")


def test_a_combo_leg_price_is_a_decimal() -> None:
    contract = Contract_pb2.Contract(conId=1, secType="BAG")
    contract.comboLegs.append(ComboLeg_pb2.ComboLeg(conId=2, perLegPrice=1.25))
    message = OpenOrder_pb2.OpenOrder(orderId=1, contract=contract)
    message.order.orderId = 1
    message.order.orderType = "LMT"
    message.orderState.status = "Submitted"
    wrapper = MagicMock()
    Decoder(wrapper).processProtoBuf(5, message.SerializeToString())

    [(_, args, _)] = [c for c in wrapper.mock_calls if c[0] == "openOrder"]
    order = args[2]
    assert order.orderComboLegs == [OrderComboLeg(price=Decimal("1.25"))]
