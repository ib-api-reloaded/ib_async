import HistoricalSession_pb2 as _HistoricalSession_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalSchedule(_message.Message):
    __slots__ = ("reqId", "startDateTime", "endDateTime", "timeZone", "historicalSessions")
    REQID_FIELD_NUMBER: _ClassVar[int]
    STARTDATETIME_FIELD_NUMBER: _ClassVar[int]
    ENDDATETIME_FIELD_NUMBER: _ClassVar[int]
    TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    HISTORICALSESSIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    startDateTime: str
    endDateTime: str
    timeZone: str
    historicalSessions: _containers.RepeatedCompositeFieldContainer[_HistoricalSession_pb2.HistoricalSession]
    def __init__(self, reqId: _Optional[int] = ..., startDateTime: _Optional[str] = ..., endDateTime: _Optional[str] = ..., timeZone: _Optional[str] = ..., historicalSessions: _Optional[_Iterable[_Union[_HistoricalSession_pb2.HistoricalSession, _Mapping]]] = ...) -> None: ...
