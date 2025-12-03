from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ErrorMessage(_message.Message):
    __slots__ = ("id", "errorTime", "errorCode", "errorMsg", "advancedOrderRejectJson")
    ID_FIELD_NUMBER: _ClassVar[int]
    ERRORTIME_FIELD_NUMBER: _ClassVar[int]
    ERRORCODE_FIELD_NUMBER: _ClassVar[int]
    ERRORMSG_FIELD_NUMBER: _ClassVar[int]
    ADVANCEDORDERREJECTJSON_FIELD_NUMBER: _ClassVar[int]
    id: int
    errorTime: int
    errorCode: int
    errorMsg: str
    advancedOrderRejectJson: str
    def __init__(self, id: _Optional[int] = ..., errorTime: _Optional[int] = ..., errorCode: _Optional[int] = ..., errorMsg: _Optional[str] = ..., advancedOrderRejectJson: _Optional[str] = ...) -> None: ...
