import SmartComponent_pb2 as _SmartComponent_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SmartComponents(_message.Message):
    __slots__ = ("reqId", "smartComponents")
    REQID_FIELD_NUMBER: _ClassVar[int]
    SMARTCOMPONENTS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    smartComponents: _containers.RepeatedCompositeFieldContainer[_SmartComponent_pb2.SmartComponent]
    def __init__(self, reqId: _Optional[int] = ..., smartComponents: _Optional[_Iterable[_Union[_SmartComponent_pb2.SmartComponent, _Mapping]]] = ...) -> None: ...
