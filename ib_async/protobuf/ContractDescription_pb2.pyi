import Contract_pb2 as _Contract_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ContractDescription(_message.Message):
    __slots__ = ("contract", "derivativeSecTypes")
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    DERIVATIVESECTYPES_FIELD_NUMBER: _ClassVar[int]
    contract: _Contract_pb2.Contract
    derivativeSecTypes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., derivativeSecTypes: _Optional[_Iterable[str]] = ...) -> None: ...
