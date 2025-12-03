import Contract_pb2 as _Contract_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class RealTimeBarsRequest(_message.Message):
    __slots__ = ("reqId", "contract", "barSize", "whatToShow", "useRTH", "realTimeBarsOptions")
    class RealTimeBarsOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    BARSIZE_FIELD_NUMBER: _ClassVar[int]
    WHATTOSHOW_FIELD_NUMBER: _ClassVar[int]
    USERTH_FIELD_NUMBER: _ClassVar[int]
    REALTIMEBARSOPTIONS_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contract: _Contract_pb2.Contract
    barSize: int
    whatToShow: str
    useRTH: bool
    realTimeBarsOptions: _containers.ScalarMap[str, str]
    def __init__(self, reqId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., barSize: _Optional[int] = ..., whatToShow: _Optional[str] = ..., useRTH: bool = ..., realTimeBarsOptions: _Optional[_Mapping[str, str]] = ...) -> None: ...
