from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TickAttribLast(_message.Message):
    __slots__ = ("pastLimit", "unreported")
    PASTLIMIT_FIELD_NUMBER: _ClassVar[int]
    UNREPORTED_FIELD_NUMBER: _ClassVar[int]
    pastLimit: bool
    unreported: bool
    def __init__(self, pastLimit: bool = ..., unreported: bool = ...) -> None: ...
