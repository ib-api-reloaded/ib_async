"""Protobuf wire framing: ``Client.sendProto`` framing, and the
receive-side ``_onSocketHasData`` discriminator. It strips the +200
sentinel and routes a protobuf frame to ``Decoder.processProtoBuf``, and
routes a text frame to ``Decoder.processText``.
"""

from __future__ import annotations

import struct
from unittest.mock import patch

import pytest

import ib_async as ibi
from ib_async._pb import ManagedAccounts_pb2, NextValidId_pb2
from ib_async._pb_msgids import PLACE_ORDER, PROTOBUF_MSG_ID
from ib_async._server_versions import MAX_CLIENT_VER

TICK_EFP = 47


def test_protobuf_msg_id_sentinel_is_200():
    assert PROTOBUF_MSG_ID == 200


def _client_at_version(version: int):
    ib = ibi.IB()
    ib.client._serverVersion = version
    return ib.client


# --- sendProto wire framing ----------------------------------------------


def test_send_proto_refuses_without_a_connection():
    """The socket drops a frame it cannot write without a word, so a
    request on a closed connection raises instead of vanishing."""
    client = _client_at_version(MAX_CLIENT_VER)
    sent: list[bytes] = []
    client.conn.sendMsg = sent.append  # type: ignore[method-assign]
    with pytest.raises(ConnectionError):
        client.placeOrder(
            1, ibi.Stock("SPY", "SMART", "USD"), ibi.MarketOrder("BUY", 1)
        )
    assert sent == []


def test_send_proto_adds_sentinel_and_length_prefix():
    client = _client_at_version(MAX_CLIENT_VER)
    client.connState = client.CONNECTED
    sent: list[bytes] = []
    client.conn.sendMsg = sent.append  # type: ignore[method-assign]

    payload = b"\x08\x01"  # arbitrary protobuf bytes
    client.sendProto(PLACE_ORDER, payload)

    assert len(sent) == 1
    framed = sent[0]
    # Layout: 4-byte BE length, 4-byte BE wire msgId, body.
    body_len = struct.unpack(">I", framed[:4])[0]
    assert body_len == 4 + len(payload)
    wire_msg_id = struct.unpack(">I", framed[4:8])[0]
    assert wire_msg_id == PLACE_ORDER + PROTOBUF_MSG_ID  # +200 sentinel
    assert framed[8:] == payload


# --- Receive-side framing detection ---------------------------------------


def _text_frame(msg_id: int, fields: list[str]) -> bytes:
    """Build a text frame: 4-byte BE wire msgId, then NUL-terminated
    fields. The wire msgId is the canonical id (no +200 sentinel)."""
    text = "".join([f + "\0" for f in fields]).encode()
    body = struct.pack(">I", msg_id) + text
    return struct.pack(">I", len(body)) + body


def _protobuf_frame(canonical_msg_id: int, payload: bytes) -> bytes:
    wire = struct.pack(">I", canonical_msg_id + PROTOBUF_MSG_ID) + payload
    return struct.pack(">I", len(wire)) + wire


def test_receive_routes_protobuf_message_to_processProtoBuf():
    client = _client_at_version(MAX_CLIENT_VER)

    seen: list[tuple[int, bytes]] = []
    client.decoder.processProtoBuf = lambda mid, p: seen.append((mid, p))  # type: ignore[method-assign]

    frame = _protobuf_frame(PLACE_ORDER, b"\x0a\x05hello")
    client._onSocketHasData(frame)

    assert seen == [(PLACE_ORDER, b"\x0a\x05hello")]


def test_receive_routes_text_message_to_processText():
    client = _client_at_version(MAX_CLIENT_VER)

    seen: list[list[str]] = []
    client.decoder.processText = seen.append  # type: ignore[method-assign]

    # A wire msgId of 200 or less is a text frame. The fields follow the
    # id, which leads the list.
    client._onSocketHasData(_text_frame(TICK_EFP, ["1", "5"]))
    client._onSocketHasData(_text_frame(53, []))

    assert seen == [["47", "1", "5"], ["53"]]


def test_receive_handles_proto_then_text_in_one_buffer():
    client = _client_at_version(MAX_CLIENT_VER)

    proto_seen: list[tuple[int, bytes]] = []
    text_seen: list[list[str]] = []
    client.decoder.processProtoBuf = lambda mid, p: proto_seen.append((mid, p))  # type: ignore[method-assign]
    client.decoder.processText = text_seen.append  # type: ignore[method-assign]

    frame_a = _protobuf_frame(PLACE_ORDER, b"\x08\x01")
    frame_b = _text_frame(TICK_EFP, ["1", "5"])
    client._onSocketHasData(frame_a + frame_b)

    assert proto_seen == [(PLACE_ORDER, b"\x08\x01")]
    assert text_seen == [["47", "1", "5"]]


def test_tick_efp_text_frame_reaches_the_wrapper():
    """TWS sends tickEFP only as text. The decoder reads it; any other
    text frame is counted as unknown."""
    client = _client_at_version(MAX_CLIENT_VER)
    fields = ["1", "5", "38", "2.5", "2.50", "101.25", "30", "20261218", "0.1", "0.2"]
    with patch.object(client.wrapper, "tickEFP") as tickEFP:
        client._onSocketHasData(_text_frame(TICK_EFP, fields))
        tickEFP.assert_called_once_with(
            5, 38, 2.5, "2.50", 101.25, 30, "20261218", 0.1, 0.2
        )
        assert client.tally.unknownMessages == 0

        # currentTime has a protobuf form; its text form is not read.
        client._onSocketHasData(_text_frame(49, ["1", "1700000000"]))
        tickEFP.assert_called_once()
    assert client.tally.unknownMessages == 1
    assert client.tally.decodeFailures == 0


# --- apiReady snoop on the protobuf receive path -------------------------


def test_proto_path_snoops_next_valid_id_and_managed_accounts_to_fire_api_start():
    # TWS sends ``nextValidId`` (msgId 9) and ``managedAccounts`` (msgId
    # 15) as protobuf. ``_onSocketHasData`` starts the API and fires
    # ``apiStart`` once both are in.

    ib = ibi.IB()
    ib.client._serverVersion = MAX_CLIENT_VER
    fired: list[bool] = []
    ib.client.apiStart += lambda: fired.append(True)

    next_valid_id = NextValidId_pb2.NextValidId()
    next_valid_id.orderId = 1000
    frame_next = _protobuf_frame(9, next_valid_id.SerializeToString())

    managed = ManagedAccounts_pb2.ManagedAccounts()
    managed.accountsList = "U1,U2"
    frame_managed = _protobuf_frame(15, managed.SerializeToString())

    ib.client._onSocketHasData(frame_next)
    assert ib.client._hasReqId is True
    assert ib.client._apiReady is False
    assert fired == []
    # ``wrapper.nextValidId`` must bump the client's reqId sequence so
    # subsequent requests don't collide with the server-side counter.
    assert ib.client._reqIdSeq >= 1000

    ib.client._onSocketHasData(frame_managed)
    assert ib.client._accounts == ["U1", "U2"]
    assert ib.client._apiReady is True
    assert fired == [True]
