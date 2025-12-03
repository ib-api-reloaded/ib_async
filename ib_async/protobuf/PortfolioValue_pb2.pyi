import Contract_pb2 as _Contract_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class PortfolioValue(_message.Message):
    __slots__ = ("contract", "position", "marketPrice", "marketValue", "averageCost", "unrealizedPNL", "realizedPNL", "accountName")
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    POSITION_FIELD_NUMBER: _ClassVar[int]
    MARKETPRICE_FIELD_NUMBER: _ClassVar[int]
    MARKETVALUE_FIELD_NUMBER: _ClassVar[int]
    AVERAGECOST_FIELD_NUMBER: _ClassVar[int]
    UNREALIZEDPNL_FIELD_NUMBER: _ClassVar[int]
    REALIZEDPNL_FIELD_NUMBER: _ClassVar[int]
    ACCOUNTNAME_FIELD_NUMBER: _ClassVar[int]
    contract: _Contract_pb2.Contract
    position: str
    marketPrice: float
    marketValue: float
    averageCost: float
    unrealizedPNL: float
    realizedPNL: float
    accountName: str
    def __init__(self, contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., position: _Optional[str] = ..., marketPrice: _Optional[float] = ..., marketValue: _Optional[float] = ..., averageCost: _Optional[float] = ..., unrealizedPNL: _Optional[float] = ..., realizedPNL: _Optional[float] = ..., accountName: _Optional[str] = ...) -> None: ...
