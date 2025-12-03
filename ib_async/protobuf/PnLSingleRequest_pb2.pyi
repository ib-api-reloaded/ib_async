from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PnLSingleRequest(_message.Message):
    __slots__ = ("reqId", "account", "modelCode", "conId")
    REQID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    MODELCODE_FIELD_NUMBER: _ClassVar[int]
    CONID_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    account: str
    modelCode: str
    conId: int
    def __init__(self, reqId: _Optional[int] = ..., account: _Optional[str] = ..., modelCode: _Optional[str] = ..., conId: _Optional[int] = ...) -> None: ...
