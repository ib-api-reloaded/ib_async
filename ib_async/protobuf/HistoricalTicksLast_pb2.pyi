import HistoricalTickLast_pb2 as _HistoricalTickLast_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalTicksLast(_message.Message):
    __slots__ = ("reqId", "historicalTicksLast", "isDone")
    REQID_FIELD_NUMBER: _ClassVar[int]
    HISTORICALTICKSLAST_FIELD_NUMBER: _ClassVar[int]
    ISDONE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    historicalTicksLast: _containers.RepeatedCompositeFieldContainer[_HistoricalTickLast_pb2.HistoricalTickLast]
    isDone: bool
    def __init__(self, reqId: _Optional[int] = ..., historicalTicksLast: _Optional[_Iterable[_Union[_HistoricalTickLast_pb2.HistoricalTickLast, _Mapping]]] = ..., isDone: bool = ...) -> None: ...
