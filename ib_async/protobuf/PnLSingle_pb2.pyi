from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PnLSingle(_message.Message):
    __slots__ = ("reqId", "position", "dailyPnL", "unrealizedPnL", "realizedPnL", "value")
    REQID_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    DAILYPNL_FIELD_NUMBER: _ClassVar[int]
    UNREALIZEDPNL_FIELD_NUMBER: _ClassVar[int]
    REALIZEDPNL_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    position: str
    dailyPnL: float
    unrealizedPnL: float
    realizedPnL: float
    value: float
    def __init__(self, reqId: _Optional[int] = ..., position: _Optional[str] = ..., dailyPnL: _Optional[float] = ..., unrealizedPnL: _Optional[float] = ..., realizedPnL: _Optional[float] = ..., value: _Optional[float] = ...) -> None: ...
