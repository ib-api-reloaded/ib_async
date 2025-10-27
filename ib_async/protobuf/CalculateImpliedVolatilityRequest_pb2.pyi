import Contract_pb2 as _Contract_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class CalculateImpliedVolatilityRequest(_message.Message):
    __slots__ = ("reqId", "contract", "optionPrice", "underPrice", "impliedVolatilityOptions")
    class ImpliedVolatilityOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    OPTIONPRICE_FIELD_NUMBER: _ClassVar[int]
    UNDERPRICE_FIELD_NUMBER: _ClassVar[int]
    IMPLIEDVOLATILITYOPTIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contract: _Contract_pb2.Contract
    optionPrice: float
    underPrice: float
    impliedVolatilityOptions: _containers.ScalarMap[str, str]
    def __init__(self, reqId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., optionPrice: _Optional[float] = ..., underPrice: _Optional[float] = ..., impliedVolatilityOptions: _Optional[_Mapping[str, str]] = ...) -> None: ...
