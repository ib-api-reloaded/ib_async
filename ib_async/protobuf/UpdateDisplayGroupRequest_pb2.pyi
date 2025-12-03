from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class UpdateDisplayGroupRequest(_message.Message):
    __slots__ = ("reqId", "contractInfo")
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACTINFO_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contractInfo: str
    def __init__(self, reqId: _Optional[int] = ..., contractInfo: _Optional[str] = ...) -> None: ...
