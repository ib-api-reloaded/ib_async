from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SecDefOptParamsRequest(_message.Message):
    __slots__ = ("reqId", "underlyingSymbol", "futFopExchange", "underlyingSecType", "underlyingConId")
    REQID_FIELD_NUMBER: _ClassVar[int]
    UNDERLYINGSYMBOL_FIELD_NUMBER: _ClassVar[int]
    FUTFOPEXCHANGE_FIELD_NUMBER: _ClassVar[int]
    UNDERLYINGSECTYPE_FIELD_NUMBER: _ClassVar[int]
    UNDERLYINGCONID_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    underlyingSymbol: str
    futFopExchange: str
    underlyingSecType: str
    underlyingConId: int
    def __init__(self, reqId: _Optional[int] = ..., underlyingSymbol: _Optional[str] = ..., futFopExchange: _Optional[str] = ..., underlyingSecType: _Optional[str] = ..., underlyingConId: _Optional[int] = ...) -> None: ...
