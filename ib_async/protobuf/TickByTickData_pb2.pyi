import HistoricalTickLast_pb2 as _HistoricalTickLast_pb2
import HistoricalTickBidAsk_pb2 as _HistoricalTickBidAsk_pb2
import HistoricalTick_pb2 as _HistoricalTick_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TickByTickData(_message.Message):
    __slots__ = ("reqId", "tickType", "historicalTickLast", "historicalTickBidAsk", "historicalTickMidPoint")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TICKTYPE_FIELD_NUMBER: _ClassVar[int]
    HISTORICALTICKLAST_FIELD_NUMBER: _ClassVar[int]
    HISTORICALTICKBIDASK_FIELD_NUMBER: _ClassVar[int]
    HISTORICALTICKMIDPOINT_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    tickType: int
    historicalTickLast: _HistoricalTickLast_pb2.HistoricalTickLast
    historicalTickBidAsk: _HistoricalTickBidAsk_pb2.HistoricalTickBidAsk
    historicalTickMidPoint: _HistoricalTick_pb2.HistoricalTick
    def __init__(self, reqId: _Optional[int] = ..., tickType: _Optional[int] = ..., historicalTickLast: _Optional[_Union[_HistoricalTickLast_pb2.HistoricalTickLast, _Mapping]] = ..., historicalTickBidAsk: _Optional[_Union[_HistoricalTickBidAsk_pb2.HistoricalTickBidAsk, _Mapping]] = ..., historicalTickMidPoint: _Optional[_Union[_HistoricalTick_pb2.HistoricalTick, _Mapping]] = ...) -> None: ...
