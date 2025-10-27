import PriceIncrement_pb2 as _PriceIncrement_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MarketRule(_message.Message):
    __slots__ = ("marketRuleId", "priceIncrements")
    MARKETRULEID_FIELD_NUMBER: _ClassVar[int]
    PRICEINCREMENTS_FIELD_NUMBER: _ClassVar[int]
    marketRuleId: int
    priceIncrements: _containers.RepeatedCompositeFieldContainer[_PriceIncrement_pb2.PriceIncrement]
    def __init__(self, marketRuleId: _Optional[int] = ..., priceIncrements: _Optional[_Iterable[_Union[_PriceIncrement_pb2.PriceIncrement, _Mapping]]] = ...) -> None: ...
