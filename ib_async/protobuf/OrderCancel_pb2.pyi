from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class OrderCancel(_message.Message):
    __slots__ = ("manualOrderCancelTime", "extOperator", "manualOrderIndicator")
    MANUALORDERCANCELTIME_FIELD_NUMBER: _ClassVar[int]
    EXTOPERATOR_FIELD_NUMBER: _ClassVar[int]
    MANUALORDERINDICATOR_FIELD_NUMBER: _ClassVar[int]
    manualOrderCancelTime: str
    extOperator: str
    manualOrderIndicator: int
    def __init__(self, manualOrderCancelTime: _Optional[str] = ..., extOperator: _Optional[str] = ..., manualOrderIndicator: _Optional[int] = ...) -> None: ...
