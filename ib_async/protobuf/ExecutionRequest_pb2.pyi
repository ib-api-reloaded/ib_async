import ExecutionFilter_pb2 as _ExecutionFilter_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExecutionRequest(_message.Message):
    __slots__ = ("reqId", "executionFilter")
    REQID_FIELD_NUMBER: _ClassVar[int]
    EXECUTIONFILTER_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    executionFilter: _ExecutionFilter_pb2.ExecutionFilter
    def __init__(self, reqId: _Optional[int] = ..., executionFilter: _Optional[_Union[_ExecutionFilter_pb2.ExecutionFilter, _Mapping]] = ...) -> None: ...
