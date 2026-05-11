"""Phase-0 protobuf plumbing tests.

These exercise the wire-framing seam without any real protobuf
converters wired up: gate-table sanity, ``Client.useProtoBuf`` boundary
behaviour, ``Client.sendProto`` framing, and the receive-side
``_onSocketHasData`` discriminator that strips the +200 sentinel and
routes to ``Decoder.processProtoBuf``.
"""

from __future__ import annotations

import struct

import ib_async as ibi
from ib_async._pb_msgids import (
    MIN_SERVER_VER_PROTOBUF,
    MIN_SERVER_VER_PROTOBUF_PLACE_ORDER,
    MIN_SERVER_VER_PROTOBUF_REST_MESSAGES_3,
    PLACE_ORDER,
    PROTOBUF_MSG_ID,
    PROTOBUF_MSG_IDS,
    REQ_CURRENT_TIME_IN_MILLIS,
    REQ_HISTORICAL_DATA,
)

# --- Gate-table sanity ----------------------------------------------------


def test_protobuf_msg_id_sentinel_is_200():
    assert PROTOBUF_MSG_ID == 200


def test_protobuf_msg_ids_table_covers_known_messages():
    # A few representative entries from each family.
    assert PROTOBUF_MSG_IDS[PLACE_ORDER] == MIN_SERVER_VER_PROTOBUF_PLACE_ORDER
    assert PROTOBUF_MSG_IDS[REQ_HISTORICAL_DATA] == 208
    assert (
        PROTOBUF_MSG_IDS[REQ_CURRENT_TIME_IN_MILLIS]
        == MIN_SERVER_VER_PROTOBUF_REST_MESSAGES_3
    )


def test_protobuf_msg_ids_table_size_matches_ibkr_reference():
    # IBKR's ibapi/common.py:55-136 ships 79 entries; if the upstream
    # adds a new message family, this test will fail loudly so we have
    # to make a deliberate decision about syncing.
    assert len(PROTOBUF_MSG_IDS) == 79


# --- useProtoBuf boundary behaviour --------------------------------------


def _client_at_version(version: int):
    ib = ibi.IB()
    ib.client._serverVersion = version
    return ib.client


def test_use_protobuf_returns_false_when_server_below_msgs_minimum():
    # PLACE_ORDER gate is 203; on a 200 server it must stay binary.
    client = _client_at_version(200)
    assert client.useProtoBuf(PLACE_ORDER) is False


def test_use_protobuf_returns_true_at_exact_gate():
    # Boundary case: server == gate.
    client = _client_at_version(MIN_SERVER_VER_PROTOBUF_PLACE_ORDER)
    assert client.useProtoBuf(PLACE_ORDER) is True


def test_use_protobuf_returns_true_above_gate():
    client = _client_at_version(225)
    assert client.useProtoBuf(PLACE_ORDER) is True


def test_use_protobuf_per_family_intermediate_server():
    # Server 207: accounts/positions are protobuf-eligible (gate 207),
    # historical data is NOT (gate 208), even though the same connection
    # is past the baseline 201 protobuf gate.
    client = _client_at_version(207)
    assert client.useProtoBuf(PLACE_ORDER) is True  # gate 203
    assert client.useProtoBuf(REQ_HISTORICAL_DATA) is False  # gate 208


def test_use_protobuf_returns_false_for_unknown_msg_id():
    client = _client_at_version(225)
    assert client.useProtoBuf(9999) is False


# --- sendProto wire framing ----------------------------------------------


def test_send_proto_adds_sentinel_and_length_prefix():
    client = _client_at_version(225)
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


def _binary_legacy_frame(fields: list[str]) -> bytes:
    """Build a legacy NUL-separated text frame as TWS would emit pre-201."""
    body = ("\0".join(fields) + "\0").encode()
    return struct.pack(">I", len(body)) + body


def _binary_v201_frame(canonical_msg_id: int, rest_fields: list[str]) -> bytes:
    """Build a v201+ binary frame: 4-byte BE wire msgId followed by NUL
    text. The wire msgId equals the canonical id (no +200 sentinel).
    With zero fields the body is just the 4-byte wire msgId — IBKR's
    convention is to trail NULs only when there's at least one field."""
    text = ("\0".join(rest_fields) + "\0").encode() if rest_fields else b""
    body = struct.pack(">I", canonical_msg_id) + text
    return struct.pack(">I", len(body)) + body


def _protobuf_frame(canonical_msg_id: int, payload: bytes) -> bytes:
    wire = struct.pack(">I", canonical_msg_id + PROTOBUF_MSG_ID) + payload
    return struct.pack(">I", len(wire)) + wire


def test_receive_routes_protobuf_message_to_processProtoBuf():
    client = _client_at_version(MIN_SERVER_VER_PROTOBUF)

    seen: list[tuple[int, bytes]] = []
    client.decoder.processProtoBuf = lambda mid, p: seen.append((mid, p))  # type: ignore[method-assign]

    frame = _protobuf_frame(PLACE_ORDER, b"\x0a\x05hello")
    client._onSocketHasData(frame)

    assert seen == [(PLACE_ORDER, b"\x0a\x05hello")]


def test_receive_routes_v201_binary_message_to_interpret():
    client = _client_at_version(MIN_SERVER_VER_PROTOBUF)

    seen: list[list[str]] = []
    client.decoder.interpret = lambda fields: seen.append(fields)  # type: ignore[method-assign]

    # Server emits a binary openOrderEnd (msgId 53, no +200) under the
    # v201 framing: 4-byte BE wire msgId followed by NUL-separated text.
    frame = _binary_v201_frame(53, [])
    client._onSocketHasData(frame)

    assert seen == [["53"]]


def test_receive_legacy_pre_handshake_routes_to_interpret():
    # Before the server-version handshake completes, _serverVersion is
    # 0; the receive-side falls back to legacy NUL-separated text. We
    # don't simulate the actual handshake here — just verify the
    # framing branch picks the legacy path.
    client = _client_at_version(0)
    seen: list[list[str]] = []

    def fake_interpret(fields):
        # Stop the handshake from kicking in by capturing the fields
        # before the server-version-set side effect.
        seen.append(fields)
        # Reset so repeated calls in this test don't trigger snoop logic.
        client._serverVersion = 0

    client.decoder.interpret = fake_interpret  # type: ignore[method-assign]

    # Synthetic post-handshake binary message: msgId 49 (currentTime)
    # carried in legacy NUL-separated form.
    frame = _binary_legacy_frame(["49", "1", "1700000000"])
    client._serverVersion = 100  # below MIN_SERVER_VER_PROTOBUF
    client._onSocketHasData(frame)

    assert seen == [["49", "1", "1700000000"]]


def test_receive_handles_split_proto_then_binary_in_one_buffer():
    client = _client_at_version(MIN_SERVER_VER_PROTOBUF)

    proto_seen: list[tuple[int, bytes]] = []
    bin_seen: list[list[str]] = []
    client.decoder.processProtoBuf = lambda mid, p: proto_seen.append((mid, p))  # type: ignore[method-assign]
    client.decoder.interpret = lambda fields: bin_seen.append(fields)  # type: ignore[method-assign]

    frame_a = _protobuf_frame(PLACE_ORDER, b"\x08\x01")
    frame_b = _binary_v201_frame(49, ["1", "1700000000"])
    client._onSocketHasData(frame_a + frame_b)

    assert proto_seen == [(PLACE_ORDER, b"\x08\x01")]
    assert bin_seen == [["49", "1", "1700000000"]]


# --- apiReady snoop on the protobuf receive path -------------------------


def test_proto_path_snoops_next_valid_id_and_managed_accounts_to_fire_api_start():
    # On a 207+ gateway TWS routes ``nextValidId`` (msgId 9) and
    # ``managedAccounts`` (msgId 15) through the protobuf receive path.
    # The handshake-completion snoop that flips ``_apiReady`` and fires
    # ``apiStart`` lives in ``_onSocketHasData`` and used to run only in
    # the binary branch, so the apiStart event never emitted on a fully
    # protobuf session — ``connectAsync`` timed out at ``apiStart``.
    from ib_async._pb import ManagedAccounts_pb2, NextValidId_pb2

    ib = ibi.IB()
    ib.client._serverVersion = 214
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
