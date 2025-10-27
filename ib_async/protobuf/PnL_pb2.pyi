from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class PnL(_message.Message):
    __slots__ = ("reqId", "dailyPnL", "unrealizedPnL", "realizedPnL")
    REQID_FIELD_NUMBER: _ClassVar[int]
    DAILYPNL_FIELD_NUMBER: _ClassVar[int]
    UNREALIZEDPNL_FIELD_NUMBER: _ClassVar[int]
    REALIZEDPNL_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    dailyPnL: float
    unrealizedPnL: float
    realizedPnL: float
    def __init__(self, reqId: _Optional[int] = ..., dailyPnL: _Optional[float] = ..., unrealizedPnL: _Optional[float] = ..., realizedPnL: _Optional[float] = ...) -> None: ...
