from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class FundamentalsData(_message.Message):
    __slots__ = ("reqId", "data")
    REQID_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    data: str
    def __init__(self, reqId: _Optional[int] = ..., data: _Optional[str] = ...) -> None: ...
