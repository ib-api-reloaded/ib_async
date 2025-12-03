from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CancelMarketDepth(_message.Message):
    __slots__ = ("reqId", "isSmartDepth")
    REQID_FIELD_NUMBER: _ClassVar[int]
    ISSMARTDEPTH_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    isSmartDepth: bool
    def __init__(self, reqId: _Optional[int] = ..., isSmartDepth: bool = ...) -> None: ...
