from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class AutoOpenOrdersRequest(_message.Message):
    __slots__ = ("autoBind",)
    AUTOBIND_FIELD_NUMBER: _ClassVar[int]
    autoBind: bool
    def __init__(self, autoBind: bool = ...) -> None: ...
