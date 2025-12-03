from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class DepthMarketDataDescription(_message.Message):
    __slots__ = ("exchange", "secType", "listingExch", "serviceDataType", "aggGroup")
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    SECTYPE_FIELD_NUMBER: _ClassVar[int]
    LISTINGEXCH_FIELD_NUMBER: _ClassVar[int]
    SERVICEDATATYPE_FIELD_NUMBER: _ClassVar[int]
    AGGGROUP_FIELD_NUMBER: _ClassVar[int]
    exchange: str
    secType: str
    listingExch: str
    serviceDataType: str
    aggGroup: int
    def __init__(self, exchange: _Optional[str] = ..., secType: _Optional[str] = ..., listingExch: _Optional[str] = ..., serviceDataType: _Optional[str] = ..., aggGroup: _Optional[int] = ...) -> None: ...
