from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class Execution(_message.Message):
    __slots__ = ("orderId", "execId", "time", "acctNumber", "exchange", "side", "shares", "price", "permId", "clientId", "isLiquidation", "cumQty", "avgPrice", "orderRef", "evRule", "evMultiplier", "modelCode", "lastLiquidity", "isPriceRevisionPending", "submitter", "optExerciseOrLapseType")
    ORDERID_FIELD_NUMBER: _ClassVar[int]
    EXECID_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    ACCTNUMBER_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    SIDE_FIELD_NUMBER: _ClassVar[int]
    SHARES_FIELD_NUMBER: _ClassVar[int]
    PRICE_FIELD_NUMBER: _ClassVar[int]
    PERMID_FIELD_NUMBER: _ClassVar[int]
    CLIENTID_FIELD_NUMBER: _ClassVar[int]
    ISLIQUIDATION_FIELD_NUMBER: _ClassVar[int]
    CUMQTY_FIELD_NUMBER: _ClassVar[int]
    AVGPRICE_FIELD_NUMBER: _ClassVar[int]
    ORDERREF_FIELD_NUMBER: _ClassVar[int]
    EVRULE_FIELD_NUMBER: _ClassVar[int]
    EVMULTIPLIER_FIELD_NUMBER: _ClassVar[int]
    MODELCODE_FIELD_NUMBER: _ClassVar[int]
    LASTLIQUIDITY_FIELD_NUMBER: _ClassVar[int]
    ISPRICEREVISIONPENDING_FIELD_NUMBER: _ClassVar[int]
    SUBMITTER_FIELD_NUMBER: _ClassVar[int]
    OPTEXERCISEORLAPSETYPE_FIELD_NUMBER: _ClassVar[int]
    orderId: int
    execId: str
    time: str
    acctNumber: str
    exchange: str
    side: str
    shares: str
    price: float
    permId: int
    clientId: int
    isLiquidation: bool
    cumQty: str
    avgPrice: float
    orderRef: str
    evRule: str
    evMultiplier: float
    modelCode: str
    lastLiquidity: int
    isPriceRevisionPending: bool
    submitter: str
    optExerciseOrLapseType: int
    def __init__(self, orderId: _Optional[int] = ..., execId: _Optional[str] = ..., time: _Optional[str] = ..., acctNumber: _Optional[str] = ..., exchange: _Optional[str] = ..., side: _Optional[str] = ..., shares: _Optional[str] = ..., price: _Optional[float] = ..., permId: _Optional[int] = ..., clientId: _Optional[int] = ..., isLiquidation: bool = ..., cumQty: _Optional[str] = ..., avgPrice: _Optional[float] = ..., orderRef: _Optional[str] = ..., evRule: _Optional[str] = ..., evMultiplier: _Optional[float] = ..., modelCode: _Optional[str] = ..., lastLiquidity: _Optional[int] = ..., isPriceRevisionPending: bool = ..., submitter: _Optional[str] = ..., optExerciseOrLapseType: _Optional[int] = ...) -> None: ...
