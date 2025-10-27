import ComboLeg_pb2 as _ComboLeg_pb2
import DeltaNeutralContract_pb2 as _DeltaNeutralContract_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Contract(_message.Message):
    __slots__ = ("conId", "symbol", "secType", "lastTradeDateOrContractMonth", "strike", "right", "multiplier", "exchange", "primaryExch", "currency", "localSymbol", "tradingClass", "secIdType", "secId", "description", "issuerId", "deltaNeutralContract", "includeExpired", "comboLegsDescrip", "comboLegs", "lastTradeDate")
    CONID_FIELD_NUMBER: _ClassVar[int]
    SYMBOL_FIELD_NUMBER: _ClassVar[int]
    SECTYPE_FIELD_NUMBER: _ClassVar[int]
    LASTTRADEDATEORCONTRACTMONTH_FIELD_NUMBER: _ClassVar[int]
    STRIKE_FIELD_NUMBER: _ClassVar[int]
    RIGHT_FIELD_NUMBER: _ClassVar[int]
    MULTIPLIER_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    PRIMARYEXCH_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    LOCALSYMBOL_FIELD_NUMBER: _ClassVar[int]
    TRADINGCLASS_FIELD_NUMBER: _ClassVar[int]
    SECIDTYPE_FIELD_NUMBER: _ClassVar[int]
    SECID_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    ISSUERID_FIELD_NUMBER: _ClassVar[int]
    DELTANEUTRALCONTRACT_FIELD_NUMBER: _ClassVar[int]
    INCLUDEEXPIRED_FIELD_NUMBER: _ClassVar[int]
    COMBOLEGSDESCRIP_FIELD_NUMBER: _ClassVar[int]
    COMBOLEGS_FIELD_NUMBER: _ClassVar[int]
    LASTTRADEDATE_FIELD_NUMBER: _ClassVar[int]
    conId: int
    symbol: str
    secType: str
    lastTradeDateOrContractMonth: str
    strike: float
    right: str
    multiplier: float
    exchange: str
    primaryExch: str
    currency: str
    localSymbol: str
    tradingClass: str
    secIdType: str
    secId: str
    description: str
    issuerId: str
    deltaNeutralContract: _DeltaNeutralContract_pb2.DeltaNeutralContract
    includeExpired: bool
    comboLegsDescrip: str
    comboLegs: _containers.RepeatedCompositeFieldContainer[_ComboLeg_pb2.ComboLeg]
    lastTradeDate: str
    def __init__(self, conId: _Optional[int] = ..., symbol: _Optional[str] = ..., secType: _Optional[str] = ..., lastTradeDateOrContractMonth: _Optional[str] = ..., strike: _Optional[float] = ..., right: _Optional[str] = ..., multiplier: _Optional[float] = ..., exchange: _Optional[str] = ..., primaryExch: _Optional[str] = ..., currency: _Optional[str] = ..., localSymbol: _Optional[str] = ..., tradingClass: _Optional[str] = ..., secIdType: _Optional[str] = ..., secId: _Optional[str] = ..., description: _Optional[str] = ..., issuerId: _Optional[str] = ..., deltaNeutralContract: _Optional[_Union[_DeltaNeutralContract_pb2.DeltaNeutralContract, _Mapping]] = ..., includeExpired: bool = ..., comboLegsDescrip: _Optional[str] = ..., comboLegs: _Optional[_Iterable[_Union[_ComboLeg_pb2.ComboLeg, _Mapping]]] = ..., lastTradeDate: _Optional[str] = ...) -> None: ...
