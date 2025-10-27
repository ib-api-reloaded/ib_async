from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalTick(_message.Message):
    __slots__ = ("time", "price", "size")
    TIME_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    time: int
    price: float
    size: str
    def __init__(self, time: _Optional[int] = ..., price: _Optional[float] = ..., size: _Optional[str] = ...) -> None: ...
