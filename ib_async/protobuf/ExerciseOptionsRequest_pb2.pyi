import Contract_pb2 as _Contract_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExerciseOptionsRequest(_message.Message):
    __slots__ = ("orderId", "contract", "exerciseAction", "exerciseQuantity", "account", "override", "manualOrderTime", "customerAccount", "professionalCustomer")
    ORDERID_FIELD_NUMBER: _ClassVar[int]
    CONTRACT_FIELD_NUMBER: _ClassVar[int]
    EXERCISEACTION_FIELD_NUMBER: _ClassVar[int]
    EXERCISEQUANTITY_FIELD_NUMBER: _ClassVar[int]
    ACCOUNT_FIELD_NUMBER: _ClassVar[int]
    OVERRIDE_FIELD_NUMBER: _ClassVar[int]
    MANUALORDERTIME_FIELD_NUMBER: _ClassVar[int]
    CUSTOMERACCOUNT_FIELD_NUMBER: _ClassVar[int]
    PROFESSIONALCUSTOMER_FIELD_NUMBER: _ClassVar[int]
    orderId: int
    contract: _Contract_pb2.Contract
    exerciseAction: int
    exerciseQuantity: int
    account: str
    override: bool
    manualOrderTime: str
    customerAccount: str
    professionalCustomer: bool
    def __init__(self, orderId: _Optional[int] = ..., contract: _Optional[_Union[_Contract_pb2.Contract, _Mapping]] = ..., exerciseAction: _Optional[int] = ..., exerciseQuantity: _Optional[int] = ..., account: _Optional[str] = ..., override: bool = ..., manualOrderTime: _Optional[str] = ..., customerAccount: _Optional[str] = ..., professionalCustomer: bool = ...) -> None: ...
