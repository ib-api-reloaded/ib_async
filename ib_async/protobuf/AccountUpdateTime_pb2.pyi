from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccountUpdateTime(_message.Message):
    __slots__ = ("timeStamp",)
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    timeStamp: str
    def __init__(self, timeStamp: _Optional[str] = ...) -> None: ...
