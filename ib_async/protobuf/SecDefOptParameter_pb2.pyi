from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SecDefOptParameter(_message.Message):
    __slots__ = ("reqId", "exchange", "underlyingConId", "tradingClass", "multiplier", "expirations", "strikes")
    REQID_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    UNDERLYINGCONID_FIELD_NUMBER: _ClassVar[int]
    TRADINGCLASS_FIELD_NUMBER: _ClassVar[int]
    MULTIPLIER_FIELD_NUMBER: _ClassVar[int]
    EXPIRATIONS_FIELD_NUMBER: _ClassVar[int]
    STRIKES_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    exchange: str
    underlyingConId: int
    tradingClass: str
    multiplier: str
    expirations: _containers.RepeatedScalarFieldContainer[str]
    strikes: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, reqId: _Optional[int] = ..., exchange: _Optional[str] = ..., underlyingConId: _Optional[int] = ..., tradingClass: _Optional[str] = ..., multiplier: _Optional[str] = ..., expirations: _Optional[_Iterable[str]] = ..., strikes: _Optional[_Iterable[float]] = ...) -> None: ...
