import FamilyCode_pb2 as _FamilyCode_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FamilyCodes(_message.Message):
    __slots__ = ("familyCodes",)
    FAMILYCODES_FIELD_NUMBER: _ClassVar[int]
    familyCodes: _containers.RepeatedCompositeFieldContainer[_FamilyCode_pb2.FamilyCode]
    def __init__(self, familyCodes: _Optional[_Iterable[_Union[_FamilyCode_pb2.FamilyCode, _Mapping]]] = ...) -> None: ...
