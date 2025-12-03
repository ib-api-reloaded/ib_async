from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class SmartComponent(_message.Message):
    __slots__ = ("bitNumber", "exchange", "exchangeLetter")
    BITNUMBER_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    EXCHANGELETTER_FIELD_NUMBER: _ClassVar[int]
    bitNumber: int
    exchange: str
    exchangeLetter: str
    def __init__(self, bitNumber: _Optional[int] = ..., exchange: _Optional[str] = ..., exchangeLetter: _Optional[str] = ...) -> None: ...
