from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CommissionAndFeesReport(_message.Message):
    __slots__ = ("execId", "commissionAndFees", "currency", "realizedPNL", "bondYield", "yieldRedemptionDate")
    EXECID_FIELD_NUMBER: _ClassVar[int]
    COMMISSIONANDFEES_FIELD_NUMBER: _ClassVar[int]
    CURRENCY_FIELD_NUMBER: _ClassVar[int]
    REALIZEDPNL_FIELD_NUMBER: _ClassVar[int]
    BONDYIELD_FIELD_NUMBER: _ClassVar[int]
    YIELDREDEMPTIONDATE_FIELD_NUMBER: _ClassVar[int]
    execId: str
    commissionAndFees: float
    currency: str
    realizedPNL: float
    bondYield: float
    yieldRedemptionDate: str
    def __init__(self, execId: _Optional[str] = ..., commissionAndFees: _Optional[float] = ..., currency: _Optional[str] = ..., realizedPNL: _Optional[float] = ..., bondYield: _Optional[float] = ..., yieldRedemptionDate: _Optional[str] = ...) -> None: ...
