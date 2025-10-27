import ScannerSubscription_pb2 as _ScannerSubscription_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ScannerSubscriptionRequest(_message.Message):
    __slots__ = ("reqId", "scannerSubscription")
    REQID_FIELD_NUMBER: _ClassVar[int]
    SCANNERSUBSCRIPTION_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    scannerSubscription: _ScannerSubscription_pb2.ScannerSubscription
    def __init__(self, reqId: _Optional[int] = ..., scannerSubscription: _Optional[_Union[_ScannerSubscription_pb2.ScannerSubscription, _Mapping]] = ...) -> None: ...
