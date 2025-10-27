import HistoricalTickBidAsk_pb2 as _HistoricalTickBidAsk_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalTicksBidAsk(_message.Message):
    __slots__ = ("reqId", "historicalTicksBidAsk", "isDone")
    REQID_FIELD_NUMBER: _ClassVar[int]
    HISTORICALTICKSBIDASK_FIELD_NUMBER: _ClassVar[int]
    ISDONE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    historicalTicksBidAsk: _containers.RepeatedCompositeFieldContainer[_HistoricalTickBidAsk_pb2.HistoricalTickBidAsk]
    isDone: bool
    def __init__(self, reqId: _Optional[int] = ..., historicalTicksBidAsk: _Optional[_Iterable[_Union[_HistoricalTickBidAsk_pb2.HistoricalTickBidAsk, _Mapping]]] = ..., isDone: bool = ...) -> None: ...
