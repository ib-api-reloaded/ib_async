from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccountSummaryRequest(_message.Message):
    __slots__ = ("reqId", "group", "tags")
    REQID_FIELD_NUMBER: _ClassVar[int]
    GROUP_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    group: str
    tags: str
    def __init__(self, reqId: _Optional[int] = ..., group: _Optional[str] = ..., tags: _Optional[str] = ...) -> None: ...
