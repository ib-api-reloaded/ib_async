"""Base converters for protobuf messages."""

from typing import List
from ..contract import TagValue


class ClientException(Exception):
    def __init__(self, code, message, text):
        super().__init__(f"Client request error: {code}: {message}, {text}")
        self.code = code
        self.message = message
        self.text = text


def fillTagValueList(tagValueList: List[TagValue], orderProtoMap: dict):
    if tagValueList is not None and tagValueList:
        for tagValue in tagValueList:
            orderProtoMap[tagValue.tag] = tagValue.value
