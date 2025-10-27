from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class RerouteMarketDepthRequest(_message.Message):
    __slots__ = ("reqId", "conId", "exchange")
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONID_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    conId: int
    exchange: str
    def __init__(self, reqId: _Optional[int] = ..., conId: _Optional[int] = ..., exchange: _Optional[str] = ...) -> None: ...
