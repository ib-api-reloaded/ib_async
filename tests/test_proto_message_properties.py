"""Property test for converting protobuf messages in the decoder.

Each protobuf message the decoder reads is built from its descriptor
with well-formed, typed values. Random bytes would only test the parse.
Numbers include IBKR's unset sentinels. Strings include numeric forms
that Decimal fields accept and forms they reject. Repeated fields hold a
few items. Nested messages are filled the same way. The test checks that
the decoder converts the message and passes it to the wrapper without
logging an exception, and that a valid frame still decodes afterwards.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from google.protobuf.descriptor import FieldDescriptor as FD
from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._requests import SingletonKey
from ib_async.decoder import _PROTO_MSG_CLASSES, Decoder, _initProtoMsgClasses
from tests._property import examples

SERVER_VERSION = 226
_initProtoMsgClasses()
MSG_IDS = sorted(_PROTO_MSG_CLASSES)
MAX_DEPTH = 3

UNSET_INT = 2**31 - 1
UNSET_DOUBLE = 1.7976931348623157e308

# Strings for Decimal-typed string fields. Some parse as numbers and some
# do not.
texts = st.one_of(
    st.just(""),
    st.sampled_from(["0", "1", "-1", "100", "0.0001", "-250.75", "1e400", "NaN"]),
    st.sampled_from(["Infinity", "abc", "DU1", "USD", "20261218", "1700000000"]),
    st.sampled_from([str(UNSET_INT), str(2**63 - 1), "1.7976931348623157E308"]),
    st.text(max_size=6),
)
doubles = st.one_of(
    st.sampled_from([0.0, -1.0, -2.0, 1.0, UNSET_DOUBLE, float("inf")]),
    st.floats(-1e6, 1e6, allow_nan=False),
)
int32s = st.one_of(
    st.sampled_from([0, -1, 1, UNSET_INT, -(2**31)]), st.integers(-(10**6), 10**6)
)
# int64 fields carry times in seconds or milliseconds. TWS does not send
# the int64 unset sentinel in them, so the range stays in epoch seconds.
int64s = st.one_of(
    st.sampled_from([0, -1, 1, 1_700_000_000]), st.integers(-(10**9), 2 * 10**9)
)
uint32s = st.one_of(st.sampled_from([0, 1, UNSET_INT]), st.integers(0, 10**6))
uint64s = st.one_of(st.sampled_from([0, 1, 1_700_000_000]), st.integers(0, 10**9))

SCALARS = {
    FD.TYPE_DOUBLE: doubles,
    FD.TYPE_FLOAT: st.floats(-1e6, 1e6, allow_nan=False, width=32),
    FD.TYPE_INT64: int64s,
    FD.TYPE_SINT64: int64s,
    FD.TYPE_SFIXED64: int64s,
    FD.TYPE_UINT64: uint64s,
    FD.TYPE_FIXED64: uint64s,
    FD.TYPE_INT32: int32s,
    FD.TYPE_SINT32: int32s,
    FD.TYPE_SFIXED32: int32s,
    FD.TYPE_UINT32: uint32s,
    FD.TYPE_FIXED32: uint32s,
    FD.TYPE_BOOL: st.booleans(),
    FD.TYPE_STRING: texts,
    FD.TYPE_BYTES: st.binary(max_size=8),
}


# Time and date string formats that IBKR sends on the wire.
ibDatetimes = st.sampled_from(
    [
        "20261016 12:00:00",
        "20261016-12:00:00",
        "20261016 12:00:00 US/Eastern",
        "1700000000",
        "20261016",
    ]
)


def isTimeField(field: FD) -> bool:
    name = field.name.lower()
    return field.type == FD.TYPE_STRING and ("time" in name or "date" in name)


def scalar(field: FD) -> st.SearchStrategy:
    if field.type == FD.TYPE_ENUM:
        return st.sampled_from([v.number for v in field.enum_type.values])
    if isTimeField(field):
        return ibDatetimes
    return SCALARS[field.type]


def fill(draw: st.DrawFn, message, depth: int) -> None:
    """Set a random subset of ``message``'s fields to random typed values.
    Time and date strings are always set, in one of IBKR's formats."""
    for field in message.DESCRIPTOR.fields:
        if isTimeField(field) and not field.is_repeated:
            setattr(message, field.name, draw(ibDatetimes))
            continue
        if not draw(st.booleans()):
            continue  # left unset
        repeated = field.is_repeated
        if field.type == FD.TYPE_MESSAGE:
            if field.message_type.GetOptions().map_entry:
                entry = field.message_type
                keyField, valueField = (
                    entry.fields_by_name["key"],
                    entry.fields_by_name["value"],
                )
                mapping = getattr(message, field.name)
                for _ in range(draw(st.integers(0, 2))):
                    key = draw(scalar(keyField))
                    if valueField.type == FD.TYPE_MESSAGE:
                        if depth < MAX_DEPTH:
                            fill(draw, mapping[key], depth + 1)
                    else:
                        mapping[key] = draw(scalar(valueField))
            elif depth < MAX_DEPTH:
                if repeated:
                    for _ in range(draw(st.integers(0, 2))):
                        fill(draw, getattr(message, field.name).add(), depth + 1)
                else:
                    fill(draw, getattr(message, field.name), depth + 1)
        elif repeated:
            getattr(message, field.name).extend(
                draw(st.lists(scalar(field), max_size=3))
            )
        else:
            setattr(message, field.name, draw(scalar(field)))


@st.composite
def messageFor(draw: st.DrawFn, msgId: int):
    message = _PROTO_MSG_CLASSES[msgId]()
    fill(draw, message, 0)
    return message


def decoder() -> tuple[ibi.IB, Decoder]:
    ib = ibi.IB()
    dec = Decoder(ib.wrapper, SERVER_VERSION)
    dec.logger = MagicMock()
    return ib, dec


def assert_valid_frame_decodes(ib: ibi.IB, dec: Decoder) -> None:
    req = ib.wrapper.requests.open(SingletonKey("currentTime"))
    dec.interpret(["49", "1", "1700000000"])
    assert req.future.done() and req.future.result().timestamp() == 1700000000


@given(msgId=st.sampled_from(MSG_IDS), data=st.data())
@examples()
def test_well_formed_message_converts_without_an_exception(msgId, data):
    message = data.draw(messageFor(msgId))
    ib, dec = decoder()
    dec.processProtoBuf(msgId, message.SerializeToString())
    dec.logger.exception.assert_not_called()
    assert_valid_frame_decodes(ib, dec)
