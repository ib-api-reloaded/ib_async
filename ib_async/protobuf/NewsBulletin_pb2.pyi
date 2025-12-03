from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class NewsBulletin(_message.Message):
    __slots__ = ("newsMsgId", "newsMsgType", "newsMessage", "originatingExch")
    NEWSMSGID_FIELD_NUMBER: _ClassVar[int]
    NEWSMSGTYPE_FIELD_NUMBER: _ClassVar[int]
    NEWSMESSAGE_FIELD_NUMBER: _ClassVar[int]
    ORIGINATINGEXCH_FIELD_NUMBER: _ClassVar[int]
    newsMsgId: int
    newsMsgType: int
    newsMessage: str
    originatingExch: str
    def __init__(self, newsMsgId: _Optional[int] = ..., newsMsgType: _Optional[int] = ..., newsMessage: _Optional[str] = ..., originatingExch: _Optional[str] = ...) -> None: ...
