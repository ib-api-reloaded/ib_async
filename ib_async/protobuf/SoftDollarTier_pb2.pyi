from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SoftDollarTier(_message.Message):
    __slots__ = ("name", "value", "displayName")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    DISPLAYNAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    value: str
    displayName: str
    def __init__(self, name: _Optional[str] = ..., value: _Optional[str] = ..., displayName: _Optional[str] = ...) -> None: ...
