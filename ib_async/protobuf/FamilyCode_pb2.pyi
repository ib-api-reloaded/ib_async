from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class FamilyCode(_message.Message):
    __slots__ = ("accountId", "familyCode")
    ACCOUNTID_FIELD_NUMBER: _ClassVar[int]
    FAMILYCODE_FIELD_NUMBER: _ClassVar[int]
    accountId: str
    familyCode: str
    def __init__(self, accountId: _Optional[str] = ..., familyCode: _Optional[str] = ...) -> None: ...
