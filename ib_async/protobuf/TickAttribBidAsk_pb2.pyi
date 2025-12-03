from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TickAttribBidAsk(_message.Message):
    __slots__ = ("bidPastLow", "askPastHigh")
    BIDPASTLOW_FIELD_NUMBER: _ClassVar[int]
    ASKPASTHIGH_FIELD_NUMBER: _ClassVar[int]
    bidPastLow: bool
    askPastHigh: bool
    def __init__(self, bidPastLow: bool = ..., askPastHigh: bool = ...) -> None: ...
