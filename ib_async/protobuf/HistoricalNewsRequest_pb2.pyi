from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalNewsRequest(_message.Message):
    __slots__ = ("reqId", "conId", "providerCodes", "startDateTime", "endDateTime", "totalResults", "historicalNewsOptions")
    class HistoricalNewsOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONID_FIELD_NUMBER: _ClassVar[int]
    PROVIDERCODES_FIELD_NUMBER: _ClassVar[int]
    STARTDATETIME_FIELD_NUMBER: _ClassVar[int]
    ENDDATETIME_FIELD_NUMBER: _ClassVar[int]
    TOTALRESULTS_FIELD_NUMBER: _ClassVar[int]
    HISTORICALNEWSOPTIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    conId: int
    providerCodes: str
    startDateTime: str
    endDateTime: str
    totalResults: int
    historicalNewsOptions: _containers.ScalarMap[str, str]
    def __init__(self, reqId: _Optional[int] = ..., conId: _Optional[int] = ..., providerCodes: _Optional[str] = ..., startDateTime: _Optional[str] = ..., endDateTime: _Optional[str] = ..., totalResults: _Optional[int] = ..., historicalNewsOptions: _Optional[_Mapping[str, str]] = ...) -> None: ...
