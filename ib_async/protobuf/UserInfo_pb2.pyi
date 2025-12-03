from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class UserInfo(_message.Message):
    __slots__ = ("reqId", "whiteBrandingId")
    REQID_FIELD_NUMBER: _ClassVar[int]
    WHITEBRANDINGID_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    whiteBrandingId: str
    def __init__(self, reqId: _Optional[int] = ..., whiteBrandingId: _Optional[str] = ...) -> None: ...
