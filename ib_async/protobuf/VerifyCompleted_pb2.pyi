from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class VerifyCompleted(_message.Message):
    __slots__ = ("isSuccessful", "errorText")
    ISSUCCESSFUL_FIELD_NUMBER: _ClassVar[int]
    ERRORTEXT_FIELD_NUMBER: _ClassVar[int]
    isSuccessful: bool
    errorText: str
    def __init__(self, isSuccessful: bool = ..., errorText: _Optional[str] = ...) -> None: ...
