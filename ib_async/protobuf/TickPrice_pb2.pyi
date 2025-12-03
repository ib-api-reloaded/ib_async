from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TickPrice(_message.Message):
    __slots__ = ("reqId", "tickType", "price", "size", "attrMask")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TICKTYPE_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    ATTRMASK_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    tickType: int
    price: float
    size: str
    attrMask: int
    def __init__(self, reqId: _Optional[int] = ..., tickType: _Optional[int] = ..., price: _Optional[float] = ..., size: _Optional[str] = ..., attrMask: _Optional[int] = ...) -> None: ...
