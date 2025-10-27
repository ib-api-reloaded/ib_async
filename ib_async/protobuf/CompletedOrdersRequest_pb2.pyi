from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CompletedOrdersRequest(_message.Message):
    __slots__ = ("apiOnly",)
    APIONLY_FIELD_NUMBER: _ClassVar[int]
    apiOnly: bool
    def __init__(self, apiOnly: bool = ...) -> None: ...
