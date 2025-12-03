from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class MarketRuleRequest(_message.Message):
    __slots__ = ("marketRuleId",)
    MARKETRULEID_FIELD_NUMBER: _ClassVar[int]
    marketRuleId: int
    def __init__(self, marketRuleId: _Optional[int] = ...) -> None: ...
