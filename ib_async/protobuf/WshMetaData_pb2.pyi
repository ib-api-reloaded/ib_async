from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class WshMetaData(_message.Message):
    __slots__ = ("reqId", "dataJson")
    REQID_FIELD_NUMBER: _ClassVar[int]
    DATAJSON_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    dataJson: str
    def __init__(self, reqId: _Optional[int] = ..., dataJson: _Optional[str] = ...) -> None: ...
