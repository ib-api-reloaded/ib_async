from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class NewsArticle(_message.Message):
    __slots__ = ("reqId", "articleType", "articleText")
    REQID_FIELD_NUMBER: _ClassVar[int]
    ARTICLETYPE_FIELD_NUMBER: _ClassVar[int]
    ARTICLETEXT_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    articleType: int
    articleText: str
    def __init__(self, reqId: _Optional[int] = ..., articleType: _Optional[int] = ..., articleText: _Optional[str] = ...) -> None: ...
