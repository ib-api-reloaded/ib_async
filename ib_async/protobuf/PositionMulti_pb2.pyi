import Contract_pb2 as _Contract_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PositionMulti(_message.Message):
    __slots__ = ("reqId", "account", "contract", "position", "avgCost", "modelCode")
    REQID_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    AVGCOST_FIELD_NUMBER: _ClassVar[int]
    MODELCODE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    account: str
    contract: _Contract_pb2.Contract
    position: str
    avgCost: float
    modelCode: str
    def __init__(self, reqId: _Optional[int] = ..., account: _Optional[str] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., position: _Optional[str] = ..., avgCost: _Optional[float] = ..., modelCode: _Optional[str] = ...) -> None: ...
