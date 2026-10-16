"""Tests of the client's connect handshake and its disconnect paths.

The tests replace the socket with a recording connection and pass the
server's frames to the client's data handler. The handshake property
covers every server version from MIN_SERVER_VER_PROTOBUF to
MAX_CLIENT_VER. It sends nextValidId and managedAccounts in either order,
each as a binary frame or a protobuf message, and then connects a second
session after a disconnect. The disconnect tests close the socket from
the peer side and disconnect from the client side in each connection
state.
"""

from __future__ import annotations

import asyncio
import struct
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._pb import ManagedAccounts_pb2, NextValidId_pb2
from ib_async._pb_msgids import PROTOBUF_MSG_ID
from ib_async._server_versions import MAX_CLIENT_VER, MIN_SERVER_VER_PROTOBUF
from ib_async.client import Client
from ib_async.util import getLoop
from tests._property import examples

NEXT_VALID_ID, MANAGED_ACCOUNTS = 9, 15


class RecordingConnection:
    """A fake connection. It accepts the connect, records every frame sent
    and counts calls to disconnect."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.closed = 0

    async def connectAsync(self, host, port) -> None:
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

    def connect(self, clientId: int = 1) -> asyncio.Task:
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


def ready(
    session: Session, version: int = MAX_CLIENT_VER, orderId: int = 100
) -> asyncio.Task:
    """Connect and complete the handshake with binary frames."""
    task = session.connect()
    session.receive(
        handshake(version),
        nextValidIdFrame(orderId, proto=False),
        managedAccountsFrame(["DU1"], proto=False),
    )
    assert task.done() and task.exception() is None
    return task


accountLists = st.lists(st.sampled_from(["DU1", "DU2", "DU3"]), min_size=1, unique=True)


@given(
    version=st.integers(MIN_SERVER_VER_PROTOBUF, MAX_CLIENT_VER),
    idFirst=st.booleans(),
    protoId=st.booleans(),
    protoAccounts=st.booleans(),
    orderId=st.integers(1, 10**6),
    accounts=accountLists,
    secondOrderId=st.integers(1, 10**6),
    secondAccounts=accountLists,
)
@examples(100)
def test_api_starts_after_next_valid_id_and_managed_accounts(
    version,
    idFirst,
    protoId,
    protoAccounts,
    orderId,
    accounts,
    secondOrderId,
    secondAccounts,
):
    session = Session()
    task = session.connect(clientId=7)
    client = session.client
    assert client.connState == Client.CONNECTING
    assert len(session.conn.sent) == 1  # the version banner

    session.receive(handshake(version))
    assert client.isConnected() and not client.isReady()
    assert client.serverVersion() == version == client.decoder.serverVersion
    assert len(session.conn.sent) == 2  # startApi went out
    assert session.started == 0 and not task.done()

    first = nextValidIdFrame(orderId, protoId)
    second = managedAccountsFrame(accounts, protoAccounts)
    if not idFirst:
        first, second = second, first
    session.receive(first)
    assert session.started == 0 and not client.isReady() and not task.done()
    with pytest.raises(ConnectionError):
        client.getReqId()

    session.receive(second)
    assert session.started == 1 and client.isReady()
    assert task.done() and task.exception() is None
    assert client.getAccounts() == accounts == session.ib.wrapper.accounts
    assert client.getReqId() == orderId
    assert client.getReqId() == orderId + 1

    # A later nextValidId does not lower the request id or restart the API.
    session.receive(nextValidIdFrame(1, protoId))
    assert client.getReqId() == orderId + 2
    assert session.started == 1

    # After a disconnect, a second session uses the new server's id and
    # accounts.
    client.disconnect()
    assert session.ended == 1 and not client.isReady()
    task = session.connect(clientId=7)
    session.receive(
        handshake(version),
        managedAccountsFrame(secondAccounts, protoAccounts),
        nextValidIdFrame(secondOrderId, protoId),
    )
    assert task.done() and task.exception() is None
    assert session.started == 2 and session.ended == 1
    assert client.getReqId() == secondOrderId
    assert client.getAccounts() == secondAccounts


def test_peer_close_before_connect_emits_no_events():
    session = Session()
    with patch.object(session.ib.wrapper, "connectionClosed") as closed:
        session.client._onSocketDisconnected("")
    closed.assert_not_called()
    assert session.ended == 0 and session.errors == []
    assert session.client.connState == Client.DISCONNECTED


def test_peer_close_before_api_ready_reports_client_id_in_use():
    session = Session()
    task = session.connect(clientId=3)
    session.receive(handshake(MAX_CLIENT_VER))
    with patch.object(session.ib.wrapper, "connectionClosed") as closed:
        session.client._onSocketDisconnected("")
    closed.assert_not_called()
    assert session.ended == 0
    assert session.errors == ["Peer closed connection. clientId 3 already in use?"]
    assert session.client.connState == Client.DISCONNECTED
    task.cancel()
    session.run()


def test_peer_close_after_api_ready_tears_down_once():
    session = Session()
    ready(session)
    with patch.object(
        session.ib.wrapper,
        "connectionClosed",
        wraps=session.ib.wrapper.connectionClosed,
    ) as closed:
        session.client._onSocketDisconnected("")
    closed.assert_called_once()
    assert session.ended == 1
    assert session.errors == ["Peer closed connection."]
    assert not session.client.isReady() and not session.client.isConnected()
    with pytest.raises(ConnectionError):
        session.client.send(1, 2)
    with pytest.raises(ConnectionError):
        session.client.getReqId()


def test_client_disconnect_tears_down_once():
    session = Session()
    ready(session)
    with patch.object(
        session.ib.wrapper,
        "connectionClosed",
        wraps=session.ib.wrapper.connectionClosed,
    ) as closed:
        session.client.disconnect()
        assert session.conn.closed == 1
        closed.assert_called_once()
        assert session.ended == 1
        # The connection then reports the close. This does not tear down
        # again.
        session.client._onSocketDisconnected("")
    closed.assert_called_once()
    assert session.ended == 1 and session.errors == []
    assert session.client.disconnect() is None  # already disconnected
    assert session.conn.closed == 2


def test_open_request_fails_when_peer_closes():
    session = Session()
    ready(session)
    ib = session.ib
    task = asyncio.ensure_future(ib.reqCurrentTimeAsync(), loop=session.loop)
    session.run()
    assert not task.done()
    session.client._onSocketDisconnected("")
    session.run()
    assert isinstance(task.exception(), ConnectionError)
