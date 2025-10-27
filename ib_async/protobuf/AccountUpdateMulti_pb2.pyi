from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AccountUpdateMulti(_message.Message):
    __slots__ = ("reqId", "account", "modelCode", "key", "value", "currency")
    REQID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    MODELCODE_FIELD_NUMBER: _ClassVar[int]
    KEY_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    account: str
    modelCode: str
    key: str
    value: str
    currency: str
    def __init__(self, reqId: _Optional[int] = ..., account: _Optional[str] = ..., modelCode: _Optional[str] = ..., key: _Optional[str] = ..., value: _Optional[str] = ..., currency: _Optional[str] = ...) -> None: ...
