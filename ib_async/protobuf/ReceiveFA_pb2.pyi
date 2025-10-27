from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ReceiveFA(_message.Message):
    __slots__ = ("faDataType", "xml")
    FADATATYPE_FIELD_NUMBER: _ClassVar[int]
    XML_FIELD_NUMBER: _ClassVar[int]
    faDataType: int
    xml: str
    def __init__(self, faDataType: _Optional[int] = ..., xml: _Optional[str] = ...) -> None: ...
