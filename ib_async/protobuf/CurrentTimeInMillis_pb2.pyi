from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CurrentTimeInMillis(_message.Message):
    __slots__ = ("currentTimeInMillis",)
    CURRENTTIMEINMILLIS_FIELD_NUMBER: _ClassVar[int]
    currentTimeInMillis: int
    def __init__(self, currentTimeInMillis: _Optional[int] = ...) -> None: ...
