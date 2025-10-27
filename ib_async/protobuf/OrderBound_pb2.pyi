from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class OrderBound(_message.Message):
    __slots__ = ("permId", "clientId", "orderId")
    PERMID_FIELD_NUMBER: _ClassVar[int]
    CLIENTID_FIELD_NUMBER: _ClassVar[int]
    ORDERID_FIELD_NUMBER: _ClassVar[int]
    permId: int
    clientId: int
    orderId: int
    def __init__(self, permId: _Optional[int] = ..., clientId: _Optional[int] = ..., orderId: _Optional[int] = ...) -> None: ...
