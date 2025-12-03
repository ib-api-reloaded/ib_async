from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ManagedAccounts(_message.Message):
    __slots__ = ("accountsList",)
    ACCOUNTSLIST_FIELD_NUMBER: _ClassVar[int]
    accountsList: str
    def __init__(self, accountsList: _Optional[str] = ...) -> None: ...
