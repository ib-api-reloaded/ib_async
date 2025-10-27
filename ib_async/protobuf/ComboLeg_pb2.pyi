from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ComboLeg(_message.Message):
    __slots__ = ("conId", "ratio", "action", "exchange", "openClose", "shortSalesSlot", "designatedLocation", "exemptCode", "perLegPrice")
    CONID_FIELD_NUMBER: _ClassVar[int]
    RATIO_FIELD_NUMBER: _ClassVar[int]
    ACTION_FIELD_NUMBER: _ClassVar[int]
    EXCHANGE_FIELD_NUMBER: _ClassVar[int]
    OPENCLOSE_FIELD_NUMBER: _ClassVar[int]
    SHORTSALESSLOT_FIELD_NUMBER: _ClassVar[int]
    DESIGNATEDLOCATION_FIELD_NUMBER: _ClassVar[int]
    EXEMPTCODE_FIELD_NUMBER: _ClassVar[int]
    PERLEGPRICE_FIELD_NUMBER: _ClassVar[int]
    conId: int
    ratio: int
    action: str
    exchange: str
    openClose: int
    shortSalesSlot: int
    designatedLocation: str
    exemptCode: int
    perLegPrice: float
    def __init__(self, conId: _Optional[int] = ..., ratio: _Optional[int] = ..., action: _Optional[str] = ..., exchange: _Optional[str] = ..., openClose: _Optional[int] = ..., shortSalesSlot: _Optional[int] = ..., designatedLocation: _Optional[str] = ..., exemptCode: _Optional[int] = ..., perLegPrice: _Optional[float] = ...) -> None: ...
