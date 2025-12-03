from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ReplaceFAEnd(_message.Message):
    __slots__ = ("reqId", "text")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    text: str
    def __init__(self, reqId: _Optional[int] = ..., text: _Optional[str] = ...) -> None: ...
