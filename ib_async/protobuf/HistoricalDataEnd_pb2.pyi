from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalDataEnd(_message.Message):
    __slots__ = ("reqId", "startDateStr", "endDateStr")
    REQID_FIELD_NUMBER: _ClassVar[int]
    STARTDATESTR_FIELD_NUMBER: _ClassVar[int]
    ENDDATESTR_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    startDateStr: str
    endDateStr: str
    def __init__(self, reqId: _Optional[int] = ..., startDateStr: _Optional[str] = ..., endDateStr: _Optional[str] = ...) -> None: ...
