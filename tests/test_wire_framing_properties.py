"""Property test of the client's socket framing.

The client reads length-prefixed frames from the socket, which can split
the bytes into chunks at any position. For any sequence of frames and any
split of their bytes into chunks, the tests check that the client passes
exactly those frames to the decoder, in order, and holds no bytes after the
last chunk arrives. The tests cover both framings: the 4-byte msgId framing
of servers from version 201 (binary and protobuf bodies), and the
NUL-separated text framing of older servers.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._pb_msgids import PROTOBUF_MSG_ID
from ib_async.client import Client
from tests._property import examples

NEW_FRAMING = 226  # server version with 4-byte msgId framing
OLD_FRAMING = 150  # NUL-separated text framing


@dataclass
class RecordingDecoder:
    """Replaces the Decoder and records the frames the client passes to it."""

    serverVersion: int = 0
    frames: list[tuple] = field(default_factory=list)

    def interpret(self, fields: list[str]) -> None:
        self.frames.append(("binary", list(fields)))

    def processProtoBuf(self, msgId: int, payload: bytes) -> None:
        self.frames.append(("proto", msgId, payload))


text = st.text(
    alphabet=st.characters(exclude_categories=("Cs",), exclude_characters="\x00"),
    max_size=8,
)
binaryFrame = st.tuples(st.integers(1, 200), st.lists(text, max_size=6)).map(
    lambda t: ("binary", t[0], t[1])
)
protoFrame = st.tuples(st.integers(1, 120), st.binary(max_size=24)).map(
    lambda t: ("proto", t[0], t[1])
)


def encode(frame: tuple, version: int) -> bytes:
    """Return the bytes a server at ``version`` sends for ``frame``."""
    kind, msgId, rest = frame
    # Every text field ends in a NUL, so a body with no fields is empty.
    if version >= 201:
        if kind == "proto":
            body = struct.pack(">I", PROTOBUF_MSG_ID + msgId) + rest
        else:
            body = struct.pack(">I", msgId) + "".join(f + "\0" for f in rest).encode()
    else:
        body = "".join(f + "\0" for f in [str(msgId), *rest]).encode()
    return struct.pack(">I", len(body)) + body


def expected(frame: tuple) -> tuple:
    kind, msgId, rest = frame
    if kind == "proto":
        return ("proto", msgId, rest)
    return ("binary", [str(msgId), *rest])


def client(version: int) -> tuple[Client, RecordingDecoder]:
    c = Client(ibi.IB().wrapper)
    c._serverVersion = version
    # Mark the handshake as done so the client does not look for ids or
    # accounts in the frames.
    c._apiReady = True
    decoder = RecordingDecoder(version)
    c.decoder = decoder  # type: ignore[assignment]
    return c, decoder


def chunks(data: bytes, cuts: list[int]) -> list[bytes]:
    """Split ``data`` at the positions in ``cuts`` (each 0 to len(data))."""
    points = sorted({c % (len(data) + 1) for c in cuts} | {0, len(data)})
    return [data[a:b] for a, b in zip(points, points[1:], strict=False)]


@given(
    frames=st.lists(st.one_of(binaryFrame, protoFrame), max_size=8),
    cuts=st.lists(st.integers(0, 10**6), max_size=12),
)
@examples()
def test_new_framing_is_independent_of_chunking(frames, cuts):
    c, decoder = client(NEW_FRAMING)
    data = b"".join(encode(f, NEW_FRAMING) for f in frames)
    for chunk in chunks(data, cuts):
        c._onSocketHasData(chunk)
    assert decoder.frames == [expected(f) for f in frames]
    assert c._data == b""
    assert c._numMsgRecv == len(frames)
    assert c._numBytesRecv == len(data)


@given(
    frames=st.lists(binaryFrame, max_size=8),
    cuts=st.lists(st.integers(0, 10**6), max_size=12),
)
@examples()
def test_old_framing_is_independent_of_chunking(frames, cuts):
    c, decoder = client(OLD_FRAMING)
    data = b"".join(encode(f, OLD_FRAMING) for f in frames)
    for chunk in chunks(data, cuts):
        c._onSocketHasData(chunk)
    assert decoder.frames == [expected(f) for f in frames]
    assert c._data == b""
    assert c._numMsgRecv == len(frames)


@given(frames=st.lists(st.one_of(binaryFrame, protoFrame), min_size=1, max_size=4))
@examples()
def test_partial_frame_is_kept_until_complete(frames):
    """The client keeps the bytes of an incomplete frame and does not decode
    it until the rest arrives."""
    c, decoder = client(NEW_FRAMING)
    data = b"".join(encode(f, NEW_FRAMING) for f in frames)
    head, tail = data[: len(data) - 1], data[len(data) - 1 :]
    c._onSocketHasData(head)
    assert len(decoder.frames) == len(frames) - 1
    assert c._data == encode(frames[-1], NEW_FRAMING)[:-1]
    c._onSocketHasData(tail)
    assert decoder.frames == [expected(f) for f in frames]
    assert c._data == b""
