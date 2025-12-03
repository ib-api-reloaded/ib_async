from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ScannerParameters(_message.Message):
    __slots__ = ("xml",)
    XML_FIELD_NUMBER: _ClassVar[int]
    xml: str
    def __init__(self, xml: _Optional[str] = ...) -> None: ...
