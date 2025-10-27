import HistogramDataEntry_pb2 as _HistogramDataEntry_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistogramData(_message.Message):
    __slots__ = ("reqId", "histogramDataEntries")
    REQID_FIELD_NUMBER: _ClassVar[int]
    HISTOGRAMDATAENTRIES_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    histogramDataEntries: _containers.RepeatedCompositeFieldContainer[_HistogramDataEntry_pb2.HistogramDataEntry]
    def __init__(self, reqId: _Optional[int] = ..., histogramDataEntries: _Optional[_Iterable[_Union[_HistogramDataEntry_pb2.HistogramDataEntry, _Mapping]]] = ...) -> None: ...
