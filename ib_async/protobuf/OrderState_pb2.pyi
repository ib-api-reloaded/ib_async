import OrderAllocation_pb2 as _OrderAllocation_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class OrderState(_message.Message):
    __slots__ = ("status", "initMarginBefore", "maintMarginBefore", "equityWithLoanBefore", "initMarginChange", "maintMarginChange", "equityWithLoanChange", "initMarginAfter", "maintMarginAfter", "equityWithLoanAfter", "commissionAndFees", "minCommissionAndFees", "maxCommissionAndFees", "commissionAndFeesCurrency", "marginCurrency", "initMarginBeforeOutsideRTH", "maintMarginBeforeOutsideRTH", "equityWithLoanBeforeOutsideRTH", "initMarginChangeOutsideRTH", "maintMarginChangeOutsideRTH", "equityWithLoanChangeOutsideRTH", "initMarginAfterOutsideRTH", "maintMarginAfterOutsideRTH", "equityWithLoanAfterOutsideRTH", "suggestedSize", "rejectReason", "orderAllocations", "warningText", "completedTime", "completedStatus")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    INITMARGINBEFORE_FIELD_NUMBER: _ClassVar[int]
    MAINTMARGINBEFORE_FIELD_NUMBER: _ClassVar[int]
    EQUITYWITHLOANBEFORE_FIELD_NUMBER: _ClassVar[int]
    INITMARGINCHANGE_FIELD_NUMBER: _ClassVar[int]
    MAINTMARGINCHANGE_FIELD_NUMBER: _ClassVar[int]
    EQUITYWITHLOANCHANGE_FIELD_NUMBER: _ClassVar[int]
    INITMARGINAFTER_FIELD_NUMBER: _ClassVar[int]
    MAINTMARGINAFTER_FIELD_NUMBER: _ClassVar[int]
    EQUITYWITHLOANAFTER_FIELD_NUMBER: _ClassVar[int]
    COMMISSIONANDFEES_FIELD_NUMBER: _ClassVar[int]
    MINCOMMISSIONANDFEES_FIELD_NUMBER: _ClassVar[int]
    MAXCOMMISSIONANDFEES_FIELD_NUMBER: _ClassVar[int]
    COMMISSIONANDFEESCURRENCY_FIELD_NUMBER: _ClassVar[int]
    MARGINCURRENCY_FIELD_NUMBER: _ClassVar[int]
    INITMARGINBEFOREOUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    MAINTMARGINBEFOREOUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    EQUITYWITHLOANBEFOREOUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    INITMARGINCHANGEOUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    MAINTMARGINCHANGEOUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    EQUITYWITHLOANCHANGEOUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    INITMARGINAFTEROUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    MAINTMARGINAFTEROUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    EQUITYWITHLOANAFTEROUTSIDERTH_FIELD_NUMBER: _ClassVar[int]
    SUGGESTEDSIZE_FIELD_NUMBER: _ClassVar[int]
    REJECTREASON_FIELD_NUMBER: _ClassVar[int]
    ORDERALLOCATIONS_FIELD_NUMBER: _ClassVar[int]
    WARNINGTEXT_FIELD_NUMBER: _ClassVar[int]
    COMPLETEDTIME_FIELD_NUMBER: _ClassVar[int]
    COMPLETEDSTATUS_FIELD_NUMBER: _ClassVar[int]
    status: str
    initMarginBefore: float
    maintMarginBefore: float
    equityWithLoanBefore: float
    initMarginChange: float
    maintMarginChange: float
    equityWithLoanChange: float
    initMarginAfter: float
    maintMarginAfter: float
    equityWithLoanAfter: float
    commissionAndFees: float
    minCommissionAndFees: float
    maxCommissionAndFees: float
    commissionAndFeesCurrency: str
    marginCurrency: str
    initMarginBeforeOutsideRTH: float
    maintMarginBeforeOutsideRTH: float
    equityWithLoanBeforeOutsideRTH: float
    initMarginChangeOutsideRTH: float
    maintMarginChangeOutsideRTH: float
    equityWithLoanChangeOutsideRTH: float
    initMarginAfterOutsideRTH: float
    maintMarginAfterOutsideRTH: float
    equityWithLoanAfterOutsideRTH: float
    suggestedSize: str
    rejectReason: str
    orderAllocations: _containers.RepeatedCompositeFieldContainer[_OrderAllocation_pb2.OrderAllocation]
    warningText: str
    completedTime: str
    completedStatus: str
    def __init__(self, status: _Optional[str] = ..., initMarginBefore: _Optional[float] = ..., maintMarginBefore: _Optional[float] = ..., equityWithLoanBefore: _Optional[float] = ..., initMarginChange: _Optional[float] = ..., maintMarginChange: _Optional[float] = ..., equityWithLoanChange: _Optional[float] = ..., initMarginAfter: _Optional[float] = ..., maintMarginAfter: _Optional[float] = ..., equityWithLoanAfter: _Optional[float] = ..., commissionAndFees: _Optional[float] = ..., minCommissionAndFees: _Optional[float] = ..., maxCommissionAndFees: _Optional[float] = ..., commissionAndFeesCurrency: _Optional[str] = ..., marginCurrency: _Optional[str] = ..., initMarginBeforeOutsideRTH: _Optional[float] = ..., maintMarginBeforeOutsideRTH: _Optional[float] = ..., equityWithLoanBeforeOutsideRTH: _Optional[float] = ..., initMarginChangeOutsideRTH: _Optional[float] = ..., maintMarginChangeOutsideRTH: _Optional[float] = ..., equityWithLoanChangeOutsideRTH: _Optional[float] = ..., initMarginAfterOutsideRTH: _Optional[float] = ..., maintMarginAfterOutsideRTH: _Optional[float] = ..., equityWithLoanAfterOutsideRTH: _Optional[float] = ..., suggestedSize: _Optional[str] = ..., rejectReason: _Optional[str] = ..., orderAllocations: _Optional[_Iterable[_Union[_OrderAllocation_pb2.OrderAllocation, _Mapping]]] = ..., warningText: _Optional[str] = ..., completedTime: _Optional[str] = ..., completedStatus: _Optional[str] = ...) -> None: ...
