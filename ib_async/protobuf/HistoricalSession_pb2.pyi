from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalSession(_message.Message):
    __slots__ = ("startDateTime", "endDateTime", "refDate")
    STARTDATETIME_FIELD_NUMBER: _ClassVar[int]
    ENDDATETIME_FIELD_NUMBER: _ClassVar[int]
    REFDATE_FIELD_NUMBER: _ClassVar[int]
    startDateTime: str
    endDateTime: str
    refDate: str
    def __init__(self, startDateTime: _Optional[str] = ..., endDateTime: _Optional[str] = ..., refDate: _Optional[str] = ...) -> None: ...
