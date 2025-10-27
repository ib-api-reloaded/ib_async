import NewsProvider_pb2 as _NewsProvider_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class NewsProviders(_message.Message):
    __slots__ = ("newsProviders",)
    NEWSPROVIDERS_FIELD_NUMBER: _ClassVar[int]
    newsProviders: _containers.RepeatedCompositeFieldContainer[_NewsProvider_pb2.NewsProvider]
    def __init__(self, newsProviders: _Optional[_Iterable[_Union[_NewsProvider_pb2.NewsProvider, _Mapping]]] = ...) -> None: ...
