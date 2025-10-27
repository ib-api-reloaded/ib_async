from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class MarketDataTypeRequest(_message.Message):
    __slots__ = ("marketDataType",)
    MARKETDATATYPE_FIELD_NUMBER: _ClassVar[int]
    marketDataType: int
    def __init__(self, marketDataType: _Optional[int] = ...) -> None: ...
