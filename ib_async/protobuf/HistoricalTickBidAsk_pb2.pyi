import TickAttribBidAsk_pb2 as _TickAttribBidAsk_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalTickBidAsk(_message.Message):
    __slots__ = ("time", "tickAttribBidAsk", "priceBid", "priceAsk", "sizeBid", "sizeAsk")
    TIME_FIELD_NUMBER: _ClassVar[int]
    TICKATTRIBBIDASK_FIELD_NUMBER: _ClassVar[int]
    PRICEBID_FIELD_NUMBER: _ClassVar[int]
    PRICEASK_FIELD_NUMBER: _ClassVar[int]
    SIZEBID_FIELD_NUMBER: _ClassVar[int]
    SIZEASK_FIELD_NUMBER: _ClassVar[int]
    time: int
    tickAttribBidAsk: _TickAttribBidAsk_pb2.TickAttribBidAsk
    priceBid: float
    priceAsk: float
    sizeBid: str
    sizeAsk: str
    def __init__(self, time: _Optional[int] = ..., tickAttribBidAsk: _Optional[_Union[_TickAttribBidAsk_pb2.TickAttribBidAsk, _Mapping]] = ..., priceBid: _Optional[float] = ..., priceAsk: _Optional[float] = ..., sizeBid: _Optional[str] = ..., sizeAsk: _Optional[str] = ...) -> None: ...
