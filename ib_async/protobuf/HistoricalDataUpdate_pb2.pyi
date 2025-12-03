import HistoricalDataBar_pb2 as _HistoricalDataBar_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalDataUpdate(_message.Message):
    __slots__ = ("reqId", "historicalDataBar")
    REQID_FIELD_NUMBER: _ClassVar[int]
    HISTORICALDATABAR_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    historicalDataBar: _HistoricalDataBar_pb2.HistoricalDataBar
    def __init__(self, reqId: _Optional[int] = ..., historicalDataBar: _Optional[_Union[_HistoricalDataBar_pb2.HistoricalDataBar, _Mapping]] = ...) -> None: ...
