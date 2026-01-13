"""Base converters for protobuf messages."""

from ..contract import TagValue
from ..objects import IBDefaults
from ..protobuf.SetServerLogLevelRequest_pb2 import (
    SetServerLogLevelRequest as SetServerLogLevelRequestProto,
)
from ..util import isValidIntValue

# This module-level variable will be updated by the IB instance on connection.
ib_defaults = IBDefaults()


def set_ib_defaults(new_defaults: IBDefaults):
    """
    Updates the shared defaults instance used by the protobuf converters.
    """
    global ib_defaults
    ib_defaults = new_defaults


class ClientException(Exception):
    def __init__(self, code, message, text):
        super().__init__(f"Client request error: {code}: {message}, {text}")
        self.code = code
        self.message = message
        self.text = text


def fillTagValueList(tagValueList: list[TagValue], orderProtoMap: dict):
    if tagValueList is not None and tagValueList:
        for tagValue in tagValueList:
            orderProtoMap[tagValue.tag] = tagValue.value


def createSetServerLogLevelRequestProto(logLevel: int) -> SetServerLogLevelRequestProto:
    setServerLogLevelRequestProto = SetServerLogLevelRequestProto()
    if isValidIntValue(logLevel):
        setServerLogLevelRequestProto.logLevel = logLevel
    return setServerLogLevelRequestProto
