from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalDataBar(_message.Message):
    __slots__ = ("date", "open", "high", "low", "close", "volume", "WAP", "barCount")
    DATE_FIELD_NUMBER: _ClassVar[int]
    OPEN_FIELD_NUMBER: _ClassVar[int]
    HIGH_FIELD_NUMBER: _ClassVar[int]
    LOW_FIELD_NUMBER: _ClassVar[int]
    CLOSE_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    WAP_FIELD_NUMBER: _ClassVar[int]
    BARCOUNT_FIELD_NUMBER: _ClassVar[int]
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: str
    WAP: str
    barCount: int
    def __init__(self, date: _Optional[str] = ..., open: _Optional[float] = ..., high: _Optional[float] = ..., low: _Optional[float] = ..., close: _Optional[float] = ..., volume: _Optional[str] = ..., WAP: _Optional[str] = ..., barCount: _Optional[int] = ...) -> None: ...
