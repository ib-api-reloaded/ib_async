import Contract_pb2 as _Contract_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class TickByTickRequest(_message.Message):
    __slots__ = ("reqId", "contract", "tickType", "numberOfTicks", "ignoreSize")
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    TICKTYPE_FIELD_NUMBER: _ClassVar[int]
    NUMBEROFTICKS_FIELD_NUMBER: _ClassVar[int]
    IGNORESIZE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contract: _Contract_pb2.Contract
    tickType: str
    numberOfTicks: int
    ignoreSize: bool
    def __init__(self, reqId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., tickType: _Optional[str] = ..., numberOfTicks: _Optional[int] = ..., ignoreSize: bool = ...) -> None: ...
