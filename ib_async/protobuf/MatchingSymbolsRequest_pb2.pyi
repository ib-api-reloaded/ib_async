from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class MatchingSymbolsRequest(_message.Message):
    __slots__ = ("reqId", "pattern")
    REQID_FIELD_NUMBER: _ClassVar[int]
    PATTERN_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    pattern: str
    def __init__(self, reqId: _Optional[int] = ..., pattern: _Optional[str] = ...) -> None: ...
