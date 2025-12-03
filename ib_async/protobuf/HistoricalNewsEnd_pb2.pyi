from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalNewsEnd(_message.Message):
    __slots__ = ("reqId", "hasMore")
    REQID_FIELD_NUMBER: _ClassVar[int]
    HASMORE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    hasMore: bool
    def __init__(self, reqId: _Optional[int] = ..., hasMore: bool = ...) -> None: ...
