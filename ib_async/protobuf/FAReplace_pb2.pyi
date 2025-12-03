from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class FAReplace(_message.Message):
    __slots__ = ("reqId", "faDataType", "xml")
    REQID_FIELD_NUMBER: _ClassVar[int]
    FADATATYPE_FIELD_NUMBER: _ClassVar[int]
    XML_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    faDataType: int
    xml: str
    def __init__(self, reqId: _Optional[int] = ..., faDataType: _Optional[int] = ..., xml: _Optional[str] = ...) -> None: ...
