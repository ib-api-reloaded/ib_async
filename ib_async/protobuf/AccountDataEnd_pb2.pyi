from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccountDataEnd(_message.Message):
    __slots__ = ("accountName",)
    ACCOUNTNAME_FIELD_NUMBER: _ClassVar[int]
    accountName: str
    def __init__(self, accountName: _Optional[str] = ...) -> None: ...
