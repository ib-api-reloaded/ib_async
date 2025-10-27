import Contract_pb2 as _Contract_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ContractDataRequest(_message.Message):
    __slots__ = ("reqId", "contract")
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contract: _Contract_pb2.Contract
    def __init__(self, reqId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ...) -> None: ...
