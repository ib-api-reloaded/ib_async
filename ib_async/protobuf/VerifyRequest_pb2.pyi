from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class VerifyRequest(_message.Message):
    __slots__ = ("apiName", "apiVersion")
    APINAME_FIELD_NUMBER: _ClassVar[int]
    APIVERSION_FIELD_NUMBER: _ClassVar[int]
    apiName: str
    apiVersion: str
    def __init__(self, apiName: _Optional[str] = ..., apiVersion: _Optional[str] = ...) -> None: ...
