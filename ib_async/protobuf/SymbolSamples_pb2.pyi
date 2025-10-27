import ContractDescription_pb2 as _ContractDescription_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SymbolSamples(_message.Message):
    __slots__ = ("reqId", "contractDescriptions")
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACTDESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contractDescriptions: _containers.RepeatedCompositeFieldContainer[_ContractDescription_pb2.ContractDescription]
    def __init__(self, reqId: _Optional[int] = ..., contractDescriptions: _Optional[_Iterable[_Union[_ContractDescription_pb2.ContractDescription, _Mapping]]] = ...) -> None: ...
