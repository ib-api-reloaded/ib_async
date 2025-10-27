from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class TickOptionComputation(_message.Message):
    __slots__ = ("reqId", "tickType", "tickAttrib", "impliedVol", "delta", "optPrice", "pvDividend", "gamma", "vega", "theta", "undPrice")
    REQID_FIELD_NUMBER: _ClassVar[int]
    TICKTYPE_FIELD_NUMBER: _ClassVar[int]
    TICKATTRIB_FIELD_NUMBER: _ClassVar[int]
    IMPLIEDVOL_FIELD_NUMBER: _ClassVar[int]
    DELTA_FIELD_NUMBER: _ClassVar[int]
    OPTPRICE_FIELD_NUMBER: _ClassVar[int]
    PVDIVIDEND_FIELD_NUMBER: _ClassVar[int]
    GAMMA_FIELD_NUMBER: _ClassVar[int]
    VEGA_FIELD_NUMBER: _ClassVar[int]
    THETA_FIELD_NUMBER: _ClassVar[int]
    UNDPRICE_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    tickType: int
    tickAttrib: int
    impliedVol: float
    delta: float
    optPrice: float
    pvDividend: float
    gamma: float
    vega: float
    theta: float
    undPrice: float
    def __init__(self, reqId: _Optional[int] = ..., tickType: _Optional[int] = ..., tickAttrib: _Optional[int] = ..., impliedVol: _Optional[float] = ..., delta: _Optional[float] = ..., optPrice: _Optional[float] = ..., pvDividend: _Optional[float] = ..., gamma: _Optional[float] = ..., vega: _Optional[float] = ..., theta: _Optional[float] = ..., undPrice: _Optional[float] = ...) -> None: ...
