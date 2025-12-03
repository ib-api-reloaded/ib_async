import SoftDollarTier_pb2 as _SoftDollarTier_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SoftDollarTiers(_message.Message):
    __slots__ = ("reqId", "softDollarTiers")
    REQID_FIELD_NUMBER: _ClassVar[int]
    SOFTDOLLARTIERS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    softDollarTiers: _containers.RepeatedCompositeFieldContainer[_SoftDollarTier_pb2.SoftDollarTier]
    def __init__(self, reqId: _Optional[int] = ..., softDollarTiers: _Optional[_Iterable[_Union[_SoftDollarTier_pb2.SoftDollarTier, _Mapping]]] = ...) -> None: ...
