import HistoricalDataBar_pb2 as _HistoricalDataBar_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalData(_message.Message):
    __slots__ = ("reqId", "historicalDataBars")
    REQID_FIELD_NUMBER: _ClassVar[int]
    HISTORICALDATABARS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    historicalDataBars: _containers.RepeatedCompositeFieldContainer[_HistoricalDataBar_pb2.HistoricalDataBar]
    def __init__(self, reqId: _Optional[int] = ..., historicalDataBars: _Optional[_Iterable[_Union[_HistoricalDataBar_pb2.HistoricalDataBar, _Mapping]]] = ...) -> None: ...
