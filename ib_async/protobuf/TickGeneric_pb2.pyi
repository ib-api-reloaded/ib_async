from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TickGeneric(_message.Message):
    __slots__ = ("reqId", "tickType", "value")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TICKTYPE_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    tickType: int
    value: float
    def __init__(self, reqId: _Optional[int] = ..., tickType: _Optional[int] = ..., value: _Optional[float] = ...) -> None: ...
