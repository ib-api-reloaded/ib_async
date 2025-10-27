import Contract_pb2 as _Contract_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class FundamentalsDataRequest(_message.Message):
    __slots__ = ("reqId", "contract", "reportType", "fundamentalsDataOptions")
    class FundamentalsDataOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    REPORTTYPE_FIELD_NUMBER: _ClassVar[int]
    FUNDAMENTALSDATAOPTIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contract: _Contract_pb2.Contract
    reportType: str
    fundamentalsDataOptions: _containers.ScalarMap[str, str]
    def __init__(self, reqId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., reportType: _Optional[str] = ..., fundamentalsDataOptions: _Optional[_Mapping[str, str]] = ...) -> None: ...
