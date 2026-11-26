"""Property test of the client's socket framing.

The client reads length-prefixed frames from the socket, which can split
the bytes into chunks at any position. For any sequence of frames and any
split of their bytes into chunks, the tests check that the client passes
exactly those frames to the decoder, in order, and holds no bytes after the
last chunk arrives. Each frame body opens with a 4-byte msgId, and carries
NUL-separated text or a protobuf payload.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._pb_msgids import PROTOBUF_MSG_ID
from ib_async._server_versions import MAX_CLIENT_VER
from ib_async.client import Client
from tests._property import examples

# A frame to send. It is ("text", msgId, fields) or
# ("proto", msgId, payload).
Frame = tuple[str, int, list[str]] | tuple[str, int, bytes]
# A message as the decoder receives it. It is ("text", fields) or
# ("proto", msgId, payload).
Decoded = tuple[str, list[str]] | tuple[str, int, bytes]


@dataclass
class RecordingDecoder:
    """Replaces the Decoder and records the frames the client passes to it."""

    frames: list[Decoded] = field(default_factory=list)

    def processText(self, fields: list[str]) -> None:
        self.frames.append(("text", list(fields)))

    def processProtoBuf(self, msgId: int, payload: bytes) -> None:
        self.frames.append(("proto", msgId, payload))


text = st.text(
    alphabet=st.characters(exclude_categories=("Cs",), exclude_characters="\x00"),
    max_size=8,
)
textFrame = st.tuples(st.integers(1, 200), st.lists(text, max_size=6)).map(
    lambda t: ("text", t[0], t[1])
)
protoFrame = st.tuples(st.integers(1, 120), st.binary(max_size=24)).map(
    lambda t: ("proto", t[0], t[1])
)


def encode(frame: Frame) -> bytes:
    """Return the bytes the server sends for ``frame``."""
    _, msgId, rest = frame
    # Every text field ends in a NUL, so a body with no fields is empty.
    if isinstance(rest, bytes):
        body = struct.pack(">I", PROTOBUF_MSG_ID + msgId) + rest
    else:
        body = struct.pack(">I", msgId) + "".join([f + "\0" for f in rest]).encode()
    return struct.pack(">I", len(body)) + body


def expected(frame: Frame) -> Decoded:
    _, msgId, rest = frame
    if isinstance(rest, bytes):
        return ("proto", msgId, rest)
    return ("text", [str(msgId), *rest])


def client() -> tuple[Client, RecordingDecoder]:
    c = Client(ibi.IB().wrapper)
    c._serverVersion = MAX_CLIENT_VER
    # Mark the handshake as done so the client does not look for ids or
    # accounts in the frames.
    c._apiReady = True
    decoder = RecordingDecoder()
    c.decoder = decoder  # type: ignore[assignment]
    return c, decoder


def chunks(data: bytes, cuts: list[int]) -> list[bytes]:
    """Split ``data`` at the positions in ``cuts`` (each 0 to len(data))."""
    points = sorted({c % (len(data) + 1) for c in cuts} | {0, len(data)})
    return [data[a:b] for a, b in zip(points, points[1:], strict=False)]


@given(
    frames=st.lists(st.one_of(textFrame, protoFrame), max_size=8),
    cuts=st.lists(st.integers(0, 10**6), max_size=12),
)
@examples()
def test_framing_is_independent_of_chunking(
    frames: list[Frame], cuts: list[int]
) -> None:
    c, decoder = client()
    data = b"".join([encode(f) for f in frames])
    for chunk in chunks(data, cuts):
        c._onSocketHasData(chunk)
    assert decoder.frames == [expected(f) for f in frames]
    assert c._data == b""
    transport = c.transportState()
    assert transport.framesReceived == len(frames)
    assert transport.bytesReceived == len(data)


@given(frames=st.lists(st.one_of(textFrame, protoFrame), min_size=1, max_size=4))
@examples()
def test_partial_frame_is_kept_until_complete(frames: list[Frame]) -> None:
    """The client keeps the bytes of an incomplete frame and does not decode
    it until the rest arrives."""
    c, decoder = client()
    data = b"".join([encode(f) for f in frames])
    head, tail = data[: len(data) - 1], data[len(data) - 1 :]
    c._onSocketHasData(head)
    assert len(decoder.frames) == len(frames) - 1
    assert c._data == encode(frames[-1])[:-1]
    c._onSocketHasData(tail)
    assert decoder.frames == [expected(f) for f in frames]
    assert c._data == b""
