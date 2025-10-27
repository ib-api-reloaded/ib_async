from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SmartComponentsRequest(_message.Message):
    __slots__ = ("reqId", "bboExchange")
    REQID_FIELD_NUMBER: _ClassVar[int]
    BBOEXCHANGE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    bboExchange: str
    def __init__(self, reqId: _Optional[int] = ..., bboExchange: _Optional[str] = ...) -> None: ...
