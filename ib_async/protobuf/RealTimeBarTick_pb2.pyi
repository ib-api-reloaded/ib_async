from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class RealTimeBarTick(_message.Message):
    __slots__ = ("reqId", "time", "open", "high", "low", "close", "volume", "WAP", "count")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    OPEN_FIELD_NUMBER: _ClassVar[int]
    HIGH_FIELD_NUMBER: _ClassVar[int]
    LOW_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    WAP_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: str
    WAP: str
    count: int
    def __init__(self, reqId: _Optional[int] = ..., time: _Optional[int] = ..., open: _Optional[float] = ..., high: _Optional[float] = ..., low: _Optional[float] = ..., close: _Optional[float] = ..., volume: _Optional[str] = ..., WAP: _Optional[str] = ..., count: _Optional[int] = ...) -> None: ...
