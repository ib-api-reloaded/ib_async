import Contract_pb2 as _Contract_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalDataRequest(_message.Message):
    __slots__ = ("reqId", "contract", "endDateTime", "barSizeSetting", "duration", "useRTH", "whatToShow", "formatDate", "keepUpToDate", "chartOptions")
    class ChartOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    ENDDATETIME_FIELD_NUMBER: _ClassVar[int]
    BARSIZESETTING_FIELD_NUMBER: _ClassVar[int]
    DURATION_FIELD_NUMBER: _ClassVar[int]
    USERTH_FIELD_NUMBER: _ClassVar[int]
    WHATTOSHOW_FIELD_NUMBER: _ClassVar[int]
    FORMATDATE_FIELD_NUMBER: _ClassVar[int]
    KEEPUPTODATE_FIELD_NUMBER: _ClassVar[int]
    CHARTOPTIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contract: _Contract_pb2.Contract
    endDateTime: str
    barSizeSetting: str
    duration: str
    useRTH: bool
    whatToShow: str
    formatDate: int
    keepUpToDate: bool
    chartOptions: _containers.ScalarMap[str, str]
    def __init__(self, reqId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., endDateTime: _Optional[str] = ..., barSizeSetting: _Optional[str] = ..., duration: _Optional[str] = ..., useRTH: bool = ..., whatToShow: _Optional[str] = ..., formatDate: _Optional[int] = ..., keepUpToDate: bool = ..., chartOptions: _Optional[_Mapping[str, str]] = ...) -> None: ...
