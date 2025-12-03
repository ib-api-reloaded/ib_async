from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class OrderAllocation(_message.Message):
    __slots__ = ("account", "position", "positionDesired", "positionAfter", "desiredAllocQty", "allowedAllocQty", "isMonetary")
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    POSITIONDESIRED_FIELD_NUMBER: _ClassVar[int]
    POSITIONAFTER_FIELD_NUMBER: _ClassVar[int]
    DESIREDALLOCQTY_FIELD_NUMBER: _ClassVar[int]
    ALLOWEDALLOCQTY_FIELD_NUMBER: _ClassVar[int]
    ISMONETARY_FIELD_NUMBER: _ClassVar[int]
    account: str
    position: str
    positionDesired: str
    positionAfter: str
    desiredAllocQty: str
    allowedAllocQty: str
    isMonetary: bool
    def __init__(self, account: _Optional[str] = ..., position: _Optional[str] = ..., positionDesired: _Optional[str] = ..., positionAfter: _Optional[str] = ..., desiredAllocQty: _Optional[str] = ..., allowedAllocQty: _Optional[str] = ..., isMonetary: bool = ...) -> None: ...
