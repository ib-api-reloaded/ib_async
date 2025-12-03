from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class MarketDepthData(_message.Message):
    __slots__ = ("position", "operation", "side", "price", "size", "marketMaker", "isSmartDepth")
    POSITION_FIELD_NUMBER: _ClassVar[int]
    OPERATION_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    SIZE_FIELD_NUMBER: _ClassVar[int]
    MARKETMAKER_FIELD_NUMBER: _ClassVar[int]
    ISSMARTDEPTH_FIELD_NUMBER: _ClassVar[int]
    position: int
    operation: int
    side: int
    price: float
    size: str
    marketMaker: str
    isSmartDepth: bool
    def __init__(self, position: _Optional[int] = ..., operation: _Optional[int] = ..., side: _Optional[int] = ..., price: _Optional[float] = ..., size: _Optional[str] = ..., marketMaker: _Optional[str] = ..., isSmartDepth: bool = ...) -> None: ...
