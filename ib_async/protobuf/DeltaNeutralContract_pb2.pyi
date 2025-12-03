from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class DeltaNeutralContract(_message.Message):
    __slots__ = ("conId", "delta", "price")
    CONID_FIELD_NUMBER: _ClassVar[int]
    DELTA_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    conId: int
    delta: float
    price: float
    def __init__(self, conId: _Optional[int] = ..., delta: _Optional[float] = ..., price: _Optional[float] = ...) -> None: ...
