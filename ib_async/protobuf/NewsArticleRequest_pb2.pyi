from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class NewsArticleRequest(_message.Message):
    __slots__ = ("reqId", "providerCode", "articleId", "newsArticleOptions")
    class NewsArticleOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REQID_FIELD_NUMBER: _ClassVar[int]
    PROVIDERCODE_FIELD_NUMBER: _ClassVar[int]
    ARTICLEID_FIELD_NUMBER: _ClassVar[int]
    NEWSARTICLEOPTIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    providerCode: str
    articleId: str
    newsArticleOptions: _containers.ScalarMap[str, str]
    def __init__(self, reqId: _Optional[int] = ..., providerCode: _Optional[str] = ..., articleId: _Optional[str] = ..., newsArticleOptions: _Optional[_Mapping[str, str]] = ...) -> None: ...
