"""
Tests for base_converters
"""

from ib_async.contract import TagValue
from ib_async.objects import IBDefaults
from ib_async.protobuf.SetServerLogLevelRequest_pb2 import (
    SetServerLogLevelRequest as SetServerLogLevelRequestProto,
)
from ib_async.protobuf_converters import base_converters
from ib_async.protobuf_converters.base_converters import (
    ClientException,
    createSetServerLogLevelRequestProto,
    fillTagValueList,
)
from ib_async.util import UNSET_INTEGER


class TestBaseConverters:
    def test_set_ib_defaults(self):
        """
        Tests that the shared defaults instance is updated correctly.
        """
        original_unset_value = base_converters.ib_defaults.unset
        original_defaults = base_converters.ib_defaults

        new_defaults = IBDefaults()
        new_defaults.unset = float("inf")
        base_converters.set_ib_defaults(new_defaults)
        assert base_converters.ib_defaults.unset == float("inf")

        # Reset to original defaults to avoid side effects in other tests
        base_converters.set_ib_defaults(original_defaults)
        assert base_converters.ib_defaults.unset is original_unset_value

    def test_client_exception(self):
        """
        Tests the ClientException custom exception.
        """
        code = 123
        message = "Test error message"
        text = "Additional text"
        try:
            raise ClientException(code, message, text)
        except ClientException as e:
            assert e.code == code
            assert e.message == message
            assert e.text == text
            assert str(e) == f"Client request error: {code}: {message}, {text}"

    def test_fillTagValueList(self):
        """
        Tests that fillTagValueList correctly populates a dictionary from a list of 
        TagValue objects.
        """
        tag_value_list = [
            TagValue(tag="tag1", value="value1"),
            TagValue(tag="tag2", value="value2"),
            TagValue(tag="tag3", value=""),
        ]
        order_proto_map: dict = {}
        fillTagValueList(tag_value_list, order_proto_map)
        expected_map = {"tag1": "value1", "tag2": "value2", "tag3": ""}
        assert order_proto_map == expected_map

    def test_fillTagValueList_empty(self):
        """
        Tests that fillTagValueList handles an empty list correctly.
        """
        tag_value_list: list = []
        order_proto_map: dict = {}
        fillTagValueList(tag_value_list, order_proto_map)
        assert order_proto_map == {}

    def test_fillTagValueList_none(self):
        """
        Tests that fillTagValueList handles a None input correctly.
        """
        tag_value_list = None
        order_proto_map = {"existing": "value"}
        fillTagValueList(tag_value_list, order_proto_map)  # type: ignore
        assert order_proto_map == {"existing": "value"}

    def test_createSetServerLogLevelRequestProto(self):
        """
        Tests creating a SetServerLogLevelRequest protobuf message.
        """
        log_level = 4  # DETAIL
        proto = createSetServerLogLevelRequestProto(log_level)
        assert isinstance(proto, SetServerLogLevelRequestProto)
        assert proto.logLevel == log_level

    def test_createSetServerLogLevelRequestProto_invalid_value(self):
        """
        Tests creating a SetServerLogLevelRequest with an invalid log level.
        The underlying `isValidIntValue` check will cause the field to not be set.
        """

        proto = createSetServerLogLevelRequestProto(UNSET_INTEGER)
        assert isinstance(proto, SetServerLogLevelRequestProto)
        assert not proto.HasField("logLevel")
