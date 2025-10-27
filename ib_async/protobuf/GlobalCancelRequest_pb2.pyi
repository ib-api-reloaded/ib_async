import OrderCancel_pb2 as _OrderCancel_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GlobalCancelRequest(_message.Message):
    __slots__ = ("orderCancel",)
    ORDERCANCEL_FIELD_NUMBER: _ClassVar[int]
    orderCancel: _OrderCancel_pb2.OrderCancel
    def __init__(self, orderCancel: _Optional[_Union[_OrderCancel_pb2.OrderCancel, _Mapping]] = ...) -> None: ...
