from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class VerifyMessageApi(_message.Message):
    __slots__ = ("apiData",)
    APIDATA_FIELD_NUMBER: _ClassVar[int]
    apiData: str
    def __init__(self, apiData: _Optional[str] = ...) -> None: ...
