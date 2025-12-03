from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccountDataRequest(_message.Message):
    __slots__ = ("subscribe", "acctCode")
    SUBSCRIBE_FIELD_NUMBER: _ClassVar[int]
    ACCTCODE_FIELD_NUMBER: _ClassVar[int]
    subscribe: bool
    acctCode: str
    def __init__(self, subscribe: bool = ..., acctCode: _Optional[str] = ...) -> None: ...
