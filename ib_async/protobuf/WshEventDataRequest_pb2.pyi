from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class WshEventDataRequest(_message.Message):
    __slots__ = ("reqId", "conId", "filter", "fillWatchlist", "fillPortfolio", "fillCompetitors", "startDate", "endDate", "totalLimit")
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONID_FIELD_NUMBER: _ClassVar[int]
    FILTER_FIELD_NUMBER: _ClassVar[int]
    FILLWATCHLIST_FIELD_NUMBER: _ClassVar[int]
    FILLPORTFOLIO_FIELD_NUMBER: _ClassVar[int]
    FILLCOMPETITORS_FIELD_NUMBER: _ClassVar[int]
    STARTDATE_FIELD_NUMBER: _ClassVar[int]
    ENDDATE_FIELD_NUMBER: _ClassVar[int]
    TOTALLIMIT_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    conId: int
    filter: str
    fillWatchlist: bool
    fillPortfolio: bool
    fillCompetitors: bool
    startDate: str
    endDate: str
    totalLimit: int
    def __init__(self, reqId: _Optional[int] = ..., conId: _Optional[int] = ..., filter: _Optional[str] = ..., fillWatchlist: bool = ..., fillPortfolio: bool = ..., fillCompetitors: bool = ..., startDate: _Optional[str] = ..., endDate: _Optional[str] = ..., totalLimit: _Optional[int] = ...) -> None: ...
