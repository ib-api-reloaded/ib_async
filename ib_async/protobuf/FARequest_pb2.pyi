from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class FARequest(_message.Message):
    __slots__ = ("faDataType",)
    FADATATYPE_FIELD_NUMBER: _ClassVar[int]
    faDataType: int
    def __init__(self, faDataType: _Optional[int] = ...) -> None: ...
