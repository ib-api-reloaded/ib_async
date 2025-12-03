from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccountValue(_message.Message):
    __slots__ = ("key", "value", "currency", "accountName")
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    ACCOUNTNAME_FIELD_NUMBER: _ClassVar[int]
    key: str
    value: str
    currency: str
    accountName: str
    def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ..., currency: _Optional[str] = ..., accountName: _Optional[str] = ...) -> None: ...
