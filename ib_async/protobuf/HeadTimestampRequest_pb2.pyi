import Contract_pb2 as _Contract_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HeadTimestampRequest(_message.Message):
    __slots__ = ("reqId", "contract", "useRTH", "whatToShow", "formatDate")
    REQID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    USERTH_FIELD_NUMBER: _ClassVar[int]
    WHATTOSHOW_FIELD_NUMBER: _ClassVar[int]
    FORMATDATE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    contract: _Contract_pb2.Contract
    useRTH: bool
    whatToShow: str
    formatDate: int
    def __init__(self, reqId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., useRTH: bool = ..., whatToShow: _Optional[str] = ..., formatDate: _Optional[int] = ...) -> None: ...
