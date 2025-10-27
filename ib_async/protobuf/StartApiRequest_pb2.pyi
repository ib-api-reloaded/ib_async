from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class StartApiRequest(_message.Message):
    __slots__ = ("clientId", "optionalCapabilities")
    CLIENTID_FIELD_NUMBER: _ClassVar[int]
    OPTIONALCAPABILITIES_FIELD_NUMBER: _ClassVar[int]
    clientId: int
    optionalCapabilities: str
    def __init__(self, clientId: _Optional[int] = ..., optionalCapabilities: _Optional[str] = ...) -> None: ...
