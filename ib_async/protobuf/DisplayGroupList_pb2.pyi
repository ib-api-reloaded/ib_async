from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class DisplayGroupList(_message.Message):
    __slots__ = ("reqId", "groups")
    REQID_FIELD_NUMBER: _ClassVar[int]
    GROUPS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    groups: str
    def __init__(self, reqId: _Optional[int] = ..., groups: _Optional[str] = ...) -> None: ...
