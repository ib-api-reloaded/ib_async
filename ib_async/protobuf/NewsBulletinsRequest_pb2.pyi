from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class NewsBulletinsRequest(_message.Message):
    __slots__ = ("allMessages",)
    ALLMESSAGES_FIELD_NUMBER: _ClassVar[int]
    allMessages: bool
    def __init__(self, allMessages: bool = ...) -> None: ...
