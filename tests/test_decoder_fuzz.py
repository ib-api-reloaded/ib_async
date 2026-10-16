"""Fuzz tests for the decoder.

The decoder is fed random field lists for every binary message id and
random bytes for every protobuf message id. It must log and drop what it
cannot read, raise nothing, and still decode the next valid frame.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._requests import SingletonKey
from ib_async.decoder import _PROTO_MESSAGES, Decoder
from tests._property import examples

SERVER_VERSION = 226

fields = st.lists(
    st.one_of(
        st.just(""),
        st.integers(-5, 5).map(str),
        st.integers(0, 2**40).map(str),
        st.floats(allow_nan=False, allow_infinity=False).map(str),
        st.sampled_from(["abc", "1e400", "NaN", "1.7976931348623157E308", "-1", "?"]),
        st.text(max_size=4),
    ),
    max_size=30,
)


def decoder() -> tuple[ibi.IB, Decoder]:
    ib = ibi.IB()
    return ib, Decoder(ib.wrapper, SERVER_VERSION)


def assert_valid_frame_decodes(ib: ibi.IB, dec: Decoder) -> None:
    """Check that a current-time frame still answers a current-time request."""
    req = ib.wrapper.requests.open(SingletonKey("currentTime"))
    dec.interpret(["49", "1", "1700000000"])
    assert req.future.done() and not req.future.cancelled()
    assert req.future.result().timestamp() == 1700000000


MSG_IDS = sorted(Decoder(ibi.IB().wrapper, SERVER_VERSION).handlers)


@given(msgId=st.sampled_from(MSG_IDS), body=fields)
@examples()
def test_malformed_binary_frame_is_dropped(msgId, body):
    ib, dec = decoder()
    dec.interpret([str(msgId), *body])
    assert_valid_frame_decodes(ib, dec)


@given(msgId=st.sampled_from(sorted(_PROTO_MESSAGES)), payload=st.binary(max_size=64))
@examples()
def test_random_protobuf_bytes_are_dropped(msgId, payload):
    ib, dec = decoder()
    dec.processProtoBuf(msgId, payload)
    assert_valid_frame_decodes(ib, dec)


@pytest.mark.parametrize("msgId", sorted(_PROTO_MESSAGES))
def test_empty_protobuf_message_is_handled(msgId):
    """An empty message is valid protobuf with every field at its default."""
    ib, dec = decoder()
    dec.processProtoBuf(msgId, b"")
    assert_valid_frame_decodes(ib, dec)
