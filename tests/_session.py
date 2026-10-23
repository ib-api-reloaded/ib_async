"""Client sessions on a recording connection.

A recording connection replaces the socket and records every frame the
client sends. Tests pass server frames to the client's data handler. The
real Client, Decoder and Wrapper run, and no data leaves the process.
"""

from __future__ import annotations

import asyncio
import struct

import ib_async as ibi
from ib_async._pb import ErrorMessage_pb2, ManagedAccounts_pb2, NextValidId_pb2
from ib_async._pb_msgids import PROTOBUF_MSG_ID
from ib_async._server_versions import MAX_CLIENT_VER
from ib_async.client import Client
from ib_async.util import getLoop

ERROR, NEXT_VALID_ID, MANAGED_ACCOUNTS = 4, 9, 15


class RecordingConnection:
    """A fake connection. It accepts every connect call, records each frame
    sent and counts disconnect calls."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = 0

    async def connectAsync(self, host: str, port: int) -> None:
        return None

    def sendMsg(self, msg: bytes) -> None:
        self.sent.append(msg)

    def disconnect(self) -> None:
        self.closed += 1


class Session:
    """An IB instance whose client uses a recording connection. It counts
    the client's apiStart and apiEnd events and records apiError messages."""

    def __init__(self) -> None:
        self.ib = ibi.IB()
        self.client: Client = self.ib.client
        self.conn = RecordingConnection()
        self.client.conn = self.conn  # type: ignore[assignment]
        self.started = self.ended = 0
        self.errors: list[str] = []
        self.client.apiStart += lambda: setattr(self, "started", self.started + 1)
        self.client.apiEnd += lambda: setattr(self, "ended", self.ended + 1)
        self.client.apiError += self.errors.append
        self.loop = getLoop()

    def connect(self, clientId: int = 1) -> asyncio.Task[None]:
        task = self.loop.create_task(
            self.client.connectAsync("127.0.0.1", 7497, clientId, timeout=0)
        )
        self.run()
        return task

    def run(self) -> None:
        for _ in range(3):
            self.loop.run_until_complete(asyncio.sleep(0))

    def receive(self, *frames: bytes) -> None:
        for frame in frames:
            self.client._onSocketHasData(frame)
        self.run()


def frame(body: bytes) -> bytes:
    return struct.pack(">I", len(body)) + body


def handshake(version: int) -> bytes:
    return frame(b"%d\x0020261016 12:00:00 UTC\x00" % version)


def binaryFrame(msgId: int, *fields: str) -> bytes:
    body = struct.pack(">I", msgId) + "".join(f + "\0" for f in fields).encode()
    return frame(body)


def nextValidIdFrame(orderId: int, proto: bool) -> bytes:
    if not proto:
        return binaryFrame(NEXT_VALID_ID, "1", str(orderId))
    message = NextValidId_pb2.NextValidId(orderId=orderId)
    return frame(
        struct.pack(">I", PROTOBUF_MSG_ID + NEXT_VALID_ID) + message.SerializeToString()
    )


def managedAccountsFrame(accounts: list[str], proto: bool) -> bytes:
    joined = ",".join(accounts)
    if not proto:
        return binaryFrame(MANAGED_ACCOUNTS, "1", joined)
    message = ManagedAccounts_pb2.ManagedAccounts(accountsList=joined)
    return frame(
        struct.pack(">I", PROTOBUF_MSG_ID + MANAGED_ACCOUNTS)
        + message.SerializeToString()
    )


def errorFrame(reqId: int, errorCode: int, errorMsg: str, proto: bool) -> bytes:
    if not proto:
        return binaryFrame(ERROR, str(reqId), str(errorCode), errorMsg, "", "0")
    message = ErrorMessage_pb2.ErrorMessage(
        id=reqId, errorCode=errorCode, errorMsg=errorMsg
    )
    return frame(
        struct.pack(">I", PROTOBUF_MSG_ID + ERROR) + message.SerializeToString()
    )


def ready(
    session: Session, version: int = MAX_CLIENT_VER, orderId: int = 100
) -> asyncio.Task[None]:
    """Connect and complete the handshake with binary frames."""
    task = session.connect()
    session.receive(
        handshake(version),
        nextValidIdFrame(orderId, proto=False),
        managedAccountsFrame(["DU1"], proto=False),
    )
    assert task.done() and task.exception() is None
    return task
