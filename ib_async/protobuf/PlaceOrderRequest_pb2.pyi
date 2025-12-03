import Contract_pb2 as _Contract_pb2
import Order_pb2 as _Order_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PlaceOrderRequest(_message.Message):
    __slots__ = ("orderId", "contract", "order")
    ORDERID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    ORDER_FIELD_NUMBER: _ClassVar[int]
    orderId: int
    contract: _Contract_pb2.Contract
    order: _Order_pb2.Order
    def __init__(self, orderId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., order: _Optional[_Union[_Order_pb2.Order, _Mapping]] = ...) -> None: ...
