from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SetServerLogLevelRequest(_message.Message):
    __slots__ = ("logLevel",)
    LOGLEVEL_FIELD_NUMBER: _ClassVar[int]
    logLevel: int
    def __init__(self, logLevel: _Optional[int] = ...) -> None: ...
