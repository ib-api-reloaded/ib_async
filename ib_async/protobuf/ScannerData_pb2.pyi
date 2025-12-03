import ScannerDataElement_pb2 as _ScannerDataElement_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ScannerData(_message.Message):
    __slots__ = ("reqId", "scannerDataElement")
    REQID_FIELD_NUMBER: _ClassVar[int]
    SCANNERDATAELEMENT_FIELD_NUMBER: _ClassVar[int]
    reqId: int
    scannerDataElement: _containers.RepeatedCompositeFieldContainer[_ScannerDataElement_pb2.ScannerDataElement]
    def __init__(self, reqId: _Optional[int] = ..., scannerDataElement: _Optional[_Iterable[_Union[_ScannerDataElement_pb2.ScannerDataElement, _Mapping]]] = ...) -> None: ...
