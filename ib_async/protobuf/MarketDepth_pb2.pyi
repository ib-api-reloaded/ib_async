import MarketDepthData_pb2 as _MarketDepthData_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MarketDepth(_message.Message):
    __slots__ = ("reqId", "marketDepthData")
    REQID_FIELD_NUMBER: _ClassVar[int]
    MARKETDEPTHDATA_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    marketDepthData: _MarketDepthData_pb2.MarketDepthData
    def __init__(self, reqId: _Optional[int] = ..., marketDepthData: _Optional[_Union[_MarketDepthData_pb2.MarketDepthData, _Mapping]] = ...) -> None: ...
