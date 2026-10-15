"""The version range ``connectAsync`` actually puts on the wire.

TWS negotiates ``min(server max, client max)`` from the ``v{Min}..{Max}``
banner, and IBKR has announced TWS API 10.51 (server version 226) as
the minimum it will accept. Other tests rebuild the banner format by
hand; these capture the bytes the real connect path sends, so a cap
that drifts from the protocol IBKR publishes shows up here.
"""

from __future__ import annotations

import asyncio
import struct

import pytest

import ib_async as ibi


class _RecordingConnection:
    """Accepts the connect, records every frame, never answers."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []

    async def connectAsync(self, host, port) -> None:
        return None

    def sendMsg(self, msg: bytes) -> None:
        self.sent.append(msg)

    def disconnect(self) -> None:
        return None


def _sentBanner() -> bytes:
    ib = ibi.IB()
    conn = _RecordingConnection()
    ib.client.conn = conn  # type: ignore[assignment]

    # No server answers, so the API-start wait times out once the
    # banner is out; only the banner matters here.
    with pytest.raises((asyncio.TimeoutError, TimeoutError)):
        ibi.util.getLoop().run_until_complete(
            ib.client.connectAsync("127.0.0.1", 7497, 1, timeout=0.01)
        )

    return conn.sent[0]


def test_banner_advertises_ibkr_10_51_server_version():
    body = b"v157..226"

    assert _sentBanner() == b"API\0" + struct.pack(">I", len(body)) + body
