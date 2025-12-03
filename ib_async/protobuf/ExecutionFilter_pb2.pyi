from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ExecutionFilter(_message.Message):
    __slots__ = ("clientId", "acctCode", "time", "symbol", "secType", "exchange", "side", "lastNDays", "specificDates")
    CLIENTID_FIELD_NUMBER: _ClassVar[int]
    ACCTCODE_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SECTYPE_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    LASTNDAYS_FIELD_NUMBER: _ClassVar[int]
    SPECIFICDATES_FIELD_NUMBER: _ClassVar[int]
    clientId: int
    acctCode: str
    time: str
    symbol: str
    secType: str
    exchange: str
    side: str
    lastNDays: int
    specificDates: _containers.RepeatedScalarFieldContainer[int]
    def __init__(self, clientId: _Optional[int] = ..., acctCode: _Optional[str] = ..., time: _Optional[str] = ..., symbol: _Optional[str] = ..., secType: _Optional[str] = ..., exchange: _Optional[str] = ..., side: _Optional[str] = ..., lastNDays: _Optional[int] = ..., specificDates: _Optional[_Iterable[int]] = ...) -> None: ...
