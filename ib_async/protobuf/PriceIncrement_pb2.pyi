from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PriceIncrement(_message.Message):
    __slots__ = ("lowEdge", "increment")
    LOWEDGE_FIELD_NUMBER: _ClassVar[int]
    INCREMENT_FIELD_NUMBER: _ClassVar[int]
    lowEdge: float
    increment: float
    def __init__(self, lowEdge: _Optional[float] = ..., increment: _Optional[float] = ...) -> None: ...
