import HistoricalTick_pb2 as _HistoricalTick_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalTicks(_message.Message):
    __slots__ = ("reqId", "historicalTicks", "isDone")
    REQID_FIELD_NUMBER: _ClassVar[int]
    HISTORICALTICKS_FIELD_NUMBER: _ClassVar[int]
    ISDONE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    historicalTicks: _containers.RepeatedCompositeFieldContainer[_HistoricalTick_pb2.HistoricalTick]
    isDone: bool
    def __init__(self, reqId: _Optional[int] = ..., historicalTicks: _Optional[_Iterable[_Union[_HistoricalTick_pb2.HistoricalTick, _Mapping]]] = ..., isDone: bool = ...) -> None: ...
