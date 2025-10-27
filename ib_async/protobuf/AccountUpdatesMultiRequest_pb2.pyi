from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccountUpdatesMultiRequest(_message.Message):
    __slots__ = ("reqId", "account", "modelCode", "ledgerAndNLV")
    REQID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    MODELCODE_FIELD_NUMBER: _ClassVar[int]
    LEDGERANDNLV_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    account: str
    modelCode: str
    ledgerAndNLV: bool
    def __init__(self, reqId: _Optional[int] = ..., account: _Optional[str] = ..., modelCode: _Optional[str] = ..., ledgerAndNLV: bool = ...) -> None: ...
