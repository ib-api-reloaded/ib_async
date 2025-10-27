from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class OrderCondition(_message.Message):
    __slots__ = ("type", "isConjunctionConnection", "isMore", "conId", "exchange", "symbol", "secType", "percent", "changePercent", "price", "triggerMethod", "time", "volume")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ISCONJUNCTIONCONNECTION_FIELD_NUMBER: _ClassVar[int]
    ISMORE_FIELD_NUMBER: _ClassVar[int]
    CONID_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SECTYPE_FIELD_NUMBER: _ClassVar[int]
    PERCENT_FIELD_NUMBER: _ClassVar[int]
    CHANGEPERCENT_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    TRIGGERMETHOD_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    VOLUME_FIELD_NUMBER: _ClassVar[int]
    type: int
    isConjunctionConnection: bool
    isMore: bool
    conId: int
    exchange: str
    symbol: str
    secType: str
    percent: int
    changePercent: float
    price: float
    triggerMethod: int
    time: str
    volume: int
    def __init__(self, type: _Optional[int] = ..., isConjunctionConnection: bool = ..., isMore: bool = ..., conId: _Optional[int] = ..., exchange: _Optional[str] = ..., symbol: _Optional[str] = ..., secType: _Optional[str] = ..., percent: _Optional[int] = ..., changePercent: _Optional[float] = ..., price: _Optional[float] = ..., triggerMethod: _Optional[int] = ..., time: _Optional[str] = ..., volume: _Optional[int] = ...) -> None: ...
