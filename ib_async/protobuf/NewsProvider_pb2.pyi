from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class NewsProvider(_message.Message):
    __slots__ = ("providerCode", "providerName")
    PROVIDERCODE_FIELD_NUMBER: _ClassVar[int]
    PROVIDERNAME_FIELD_NUMBER: _ClassVar[int]
    providerCode: str
    providerName: str
    def __init__(self, providerCode: _Optional[str] = ..., providerName: _Optional[str] = ...) -> None: ...
