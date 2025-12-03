import DepthMarketDataDescription_pb2 as _DepthMarketDataDescription_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MarketDepthExchanges(_message.Message):
    __slots__ = ("depthMarketDataDescriptions",)
    DEPTHMARKETDATADESCRIPTIONS_FIELD_NUMBER: _ClassVar[int]
    depthMarketDataDescriptions: _containers.RepeatedCompositeFieldContainer[_DepthMarketDataDescription_pb2.DepthMarketDataDescription]
    def __init__(self, depthMarketDataDescriptions: _Optional[_Iterable[_Union[_DepthMarketDataDescription_pb2.DepthMarketDataDescription, _Mapping]]] = ...) -> None: ...
