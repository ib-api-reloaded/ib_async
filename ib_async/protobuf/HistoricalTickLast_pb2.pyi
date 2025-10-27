import TickAttribLast_pb2 as _TickAttribLast_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalTickLast(_message.Message):
    __slots__ = ("time", "tickAttribLast", "price", "size", "exchange", "specialConditions")
    TIME_FIELD_NUMBER: _ClassVar[int]
    TICKATTRIBLAST_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    SPECIALCONDITIONS_FIELD_NUMBER: _ClassVar[int]
    time: int
    tickAttribLast: _TickAttribLast_pb2.TickAttribLast
    price: float
    size: str
    exchange: str
    specialConditions: str
    def __init__(self, time: _Optional[int] = ..., tickAttribLast: _Optional[_Union[_TickAttribLast_pb2.TickAttribLast, _Mapping]] = ..., price: _Optional[float] = ..., size: _Optional[str] = ..., exchange: _Optional[str] = ..., specialConditions: _Optional[str] = ...) -> None: ...
