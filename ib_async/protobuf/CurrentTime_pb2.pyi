from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CurrentTime(_message.Message):
    __slots__ = ("currentTime",)
    CURRENTTIME_FIELD_NUMBER: _ClassVar[int]
    currentTime: int
    def __init__(self, currentTime: _Optional[int] = ...) -> None: ...
