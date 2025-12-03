import Contract_pb2 as _Contract_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ScannerDataElement(_message.Message):
    __slots__ = ("rank", "contract", "marketName", "distance", "benchmark", "projection", "comboKey")
    RANK_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    MARKETNAME_FIELD_NUMBER: _ClassVar[int]
    DISTANCE_FIELD_NUMBER: _ClassVar[int]
    BENCHMARK_FIELD_NUMBER: _ClassVar[int]
    PROJECTION_FIELD_NUMBER: _ClassVar[int]
    COMBOKEY_FIELD_NUMBER: _ClassVar[int]
    rank: int
    contract: _Contract_pb2.Contract
    marketName: str
    distance: str
    benchmark: str
    projection: str
    comboKey: str
    def __init__(self, rank: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., marketName: _Optional[str] = ..., distance: _Optional[str] = ..., benchmark: _Optional[str] = ..., projection: _Optional[str] = ..., comboKey: _Optional[str] = ...) -> None: ...
