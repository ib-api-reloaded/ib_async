from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class HistoricalNews(_message.Message):
    __slots__ = ("reqId", "time", "providerCode", "articleId", "headline")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    PROVIDERCODE_FIELD_NUMBER: _ClassVar[int]
    ARTICLEID_FIELD_NUMBER: _ClassVar[int]
    HEADLINE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    time: str
    providerCode: str
    articleId: str
    headline: str
    def __init__(self, reqId: _Optional[int] = ..., time: _Optional[str] = ..., providerCode: _Optional[str] = ..., articleId: _Optional[str] = ..., headline: _Optional[str] = ...) -> None: ...
