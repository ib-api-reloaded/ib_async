from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TickNews(_message.Message):
    __slots__ = ("reqId", "timestamp", "providerCode", "articleId", "headline", "extraData")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    PROVIDERCODE_FIELD_NUMBER: _ClassVar[int]
    ARTICLEID_FIELD_NUMBER: _ClassVar[int]
    HEADLINE_FIELD_NUMBER: _ClassVar[int]
    EXTRADATA_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    timestamp: int
    providerCode: str
    articleId: str
    headline: str
    extraData: str
    def __init__(self, reqId: _Optional[int] = ..., timestamp: _Optional[int] = ..., providerCode: _Optional[str] = ..., articleId: _Optional[str] = ..., headline: _Optional[str] = ..., extraData: _Optional[str] = ...) -> None: ...
