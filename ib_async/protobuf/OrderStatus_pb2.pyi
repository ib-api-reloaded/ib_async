from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class OrderStatus(_message.Message):
    __slots__ = ("orderId", "status", "filled", "remaining", "avgFillPrice", "permId", "parentId", "lastFillPrice", "clientId", "whyHeld", "mktCapPrice")
    ORDERID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    FILLED_FIELD_NUMBER: _ClassVar[int]
    REMAINING_FIELD_NUMBER: _ClassVar[int]
    AVGFILLPRICE_FIELD_NUMBER: _ClassVar[int]
    PERMID_FIELD_NUMBER: _ClassVar[int]
    PARENTID_FIELD_NUMBER: _ClassVar[int]
    LASTFILLPRICE_FIELD_NUMBER: _ClassVar[int]
    CLIENTID_FIELD_NUMBER: _ClassVar[int]
    WHYHELD_FIELD_NUMBER: _ClassVar[int]
    MKTCAPPRICE_FIELD_NUMBER: _ClassVar[int]
    orderId: int
    status: str
    filled: str
    remaining: str
    avgFillPrice: float
    permId: int
    parentId: int
    lastFillPrice: float
    clientId: int
    whyHeld: str
    mktCapPrice: float
    def __init__(self, orderId: _Optional[int] = ..., status: _Optional[str] = ..., filled: _Optional[str] = ..., remaining: _Optional[str] = ..., avgFillPrice: _Optional[float] = ..., permId: _Optional[int] = ..., parentId: _Optional[int] = ..., lastFillPrice: _Optional[float] = ..., clientId: _Optional[int] = ..., whyHeld: _Optional[str] = ..., mktCapPrice: _Optional[float] = ...) -> None: ...
