"""Tests of the client's connect handshake and its disconnect paths.

The tests replace the socket with a recording connection and pass the
server's frames to the client's data handler. The handshake property
runs at server version 226, the only one the client accepts. It sends
nextValidId and managedAccounts in either order as protobuf messages, and
then connects a second session after a disconnect. The disconnect tests close the socket from
the peer side and disconnect from the client side in each connection
state.
"""

from __future__ import annotations

import asyncio
import gc
import logging
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ib_async._server_versions import MAX_CLIENT_VER
from ib_async.client import Client
from tests._property import examples
from tests._session import (
    RecordingConnection,
    Session,
    errorFrame,
    frame,
    handshake,
    managedAccountsFrame,
    nextValidIdFrame,
    ready,
)

accountLists = st.lists(st.sampled_from(["DU1", "DU2", "DU3"]), min_size=1, unique=True)


@given(
    idFirst=st.booleans(),
    orderId=st.integers(1, 10**6),
    accounts=accountLists,
    secondOrderId=st.integers(1, 10**6),
    secondAccounts=accountLists,
)
@examples()
def test_api_starts_after_next_valid_id_and_managed_accounts(
    idFirst,
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

    session.receive(handshake(MAX_CLIENT_VER))
    assert client.isConnected() and not client.isReady()
    assert client.serverVersion() == MAX_CLIENT_VER
    assert len(session.conn.sent) == 2  # startApi went out
    assert session.started == 0 and not task.done()

    first = nextValidIdFrame(orderId)
    second = managedAccountsFrame(accounts)
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
    session.receive(nextValidIdFrame(1))
    assert client.getReqId() == orderId + 2
    assert session.started == 1

    # After a disconnect, a second session uses the new server's id and
    # accounts.
    client.disconnect()
    assert session.ended == 1 and not client.isReady()
    task = session.connect(clientId=7)
    session.receive(
        handshake(MAX_CLIENT_VER),
        managedAccountsFrame(secondAccounts),
        nextValidIdFrame(secondOrderId),
    )
    assert task.done() and task.exception() is None
    assert session.started == 2 and session.ended == 1
    assert client.getReqId() == secondOrderId
    assert client.getAccounts() == secondAccounts


@given(cuts=st.lists(st.integers(0, 1000), max_size=8))
@examples()
def test_the_handshake_and_api_start_survive_any_split_of_the_bytes(cuts):
    """TCP may deliver the handshake answer, nextValidId and
    managedAccounts in any chunks, a frame split or several together."""
    session = Session()
    task = session.connect(clientId=7)
    data = (
        handshake(MAX_CLIENT_VER)
        + nextValidIdFrame(500)
        + managedAccountsFrame(["DU1", "DU2"])
    )
    points = sorted({c % (len(data) + 1) for c in cuts} | {0, len(data)})
    for start, end in zip(points, points[1:], strict=False):
        session.receive(data[start:end])

    assert task.done() and task.exception() is None
    assert session.client.getReqId() == 500
    assert session.client.getAccounts() == ["DU1", "DU2"]


def test_a_frame_that_is_not_a_handshake_answer_is_logged_and_skipped(
    caplog: pytest.LogCaptureFixture,
):
    session = Session()
    task = session.connect()
    with caplog.at_level(logging.ERROR, logger="ib_async.client"):
        session.receive(frame(b"not\x00a\x00handshake\x00"))
    assert "Not a handshake answer" in caplog.text
    assert not session.client.isConnected()

    session.receive(
        handshake(MAX_CLIENT_VER), nextValidIdFrame(1), managedAccountsFrame(["DU1"])
    )
    assert task.done() and task.exception() is None


def test_peer_close_before_connect_emits_no_events():
    session = Session()
    with patch.object(session.ib.wrapper, "connectionClosed") as closed:
        session.client._onSocketDisconnected("")
    closed.assert_not_called()
    assert session.ended == 0 and session.errors == []
    assert session.client.connState == Client.DISCONNECTED


def test_peer_close_before_api_ready_fails_connect():
    session = Session()
    task = session.connect(clientId=3)
    session.receive(handshake(MAX_CLIENT_VER))
    with patch.object(session.ib.wrapper, "connectionClosed") as closed:
        session.client._onSocketDisconnected("")
        session.run()
    closed.assert_not_called()
    assert session.ended == 0
    reason = "Peer closed connection. clientId 3 already in use?"
    assert session.errors[0] == reason
    assert session.client.connState == Client.DISCONNECTED
    error = task.exception()
    assert isinstance(error, ConnectionError) and str(error) == reason


CLIENT_ID_IN_USE = (
    "Unable to connect as the client id is already in use. "
    "Retry with a unique client id."
)


def test_client_id_in_use_fails_connect_with_the_server_error():
    # TWS answers startApi with error 326 and closes the socket. connect
    # has no timeout here, so only the close can end it.
    session = Session()
    task = session.connect(clientId=3)
    session.receive(handshake(MAX_CLIENT_VER), errorFrame(-1, 326, CLIENT_ID_IN_USE))
    assert not task.done()
    session.client._onSocketDisconnected("")
    session.run()
    error = task.exception()
    assert isinstance(error, ConnectionError)
    assert str(error) == f"Error 326: {CLIENT_ID_IN_USE}"
    assert (
        session.errors[0]
        == f"Peer closed connection after Error 326: {CLIENT_ID_IN_USE}"
    )
    assert session.started == 0 and not session.client.isConnected()


def test_peer_close_during_handshake_fails_connect():
    session = Session()
    task = session.connect()
    session.client._onSocketDisconnected("")
    session.run()
    error = task.exception()
    assert isinstance(error, ConnectionError)
    assert str(error) == "Peer closed connection during the handshake"


def test_client_disconnect_while_connecting_fails_connect():
    session = Session()
    task = session.connect()
    session.receive(handshake(MAX_CLIENT_VER))
    session.client.disconnect()
    session.run()
    error = task.exception()
    assert isinstance(error, ConnectionError)
    assert str(error) == "Disconnected before the API started"


class RefusingConnection(RecordingConnection):
    """A fake connection whose socket connect is refused, as while TWS
    restarts and its API port is closed."""

    async def connectAsync(self, host: str, port: int) -> None:
        raise ConnectionRefusedError(111, "Connect call failed")


def test_refused_socket_connect_reports_nothing_to_the_loop():
    # A caller retries while the port refuses. Each attempt raises from
    # connectAsync and leaves no unread future failure for the loop's
    # exception handler, which an interactive app shows as a crash.
    session = Session()
    session.client.conn = RefusingConnection()  # type: ignore[assignment]
    # Free what earlier tests left on the shared loop before the handler is
    # installed, so only this test's own futures can reach it. Without
    # reference counting (PyPy) a dropped future is freed only when the
    # garbage collector runs.
    session.run()
    gc.collect()
    reported: list[dict[str, object]] = []
    session.loop.set_exception_handler(lambda loop, context: reported.append(context))
    try:
        for _ in range(2):
            task = session.connect()
            assert isinstance(task.exception(), ConnectionRefusedError)
            del task
        gc.collect()
    finally:
        session.loop.set_exception_handler(None)
    assert reported == []
    assert session.client._apiStarting is None


def test_server_too_old_fails_connect():
    session = Session()
    task = session.connect()
    session.receive(handshake(Client.MinClientVersion - 1))
    error = task.exception()
    assert isinstance(error, ConnectionError)
    assert str(error) == (
        "TWS / IB Gateway server version 225 is older than 226 (TWS API 10.51), "
        "the oldest ib_async supports"
    )
    assert session.conn.closed >= 1


def test_error_after_api_start_does_not_mark_a_refusal():
    session = Session()
    ready(session)
    session.receive(errorFrame(-1, 1100, "Connectivity between IBKR and TWS lost."))
    session.client._onSocketDisconnected("")
    assert session.errors == ["Peer closed connection."]


def test_ib_connect_raises_client_id_in_use():
    session = Session()
    task = session.loop.create_task(
        session.ib.connectAsync("127.0.0.1", 7497, clientId=3, timeout=0)
    )
    session.run()
    session.receive(handshake(MAX_CLIENT_VER), errorFrame(-1, 326, CLIENT_ID_IN_USE))
    session.client._onSocketDisconnected("")
    session.run()
    error = task.exception()
    assert isinstance(error, ConnectionError)
    assert str(error) == f"Error 326: {CLIENT_ID_IN_USE}"
    assert not session.ib.isConnected()


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
        session.client.reqCurrentTime()
    with pytest.raises(ConnectionError):
        session.client.getReqId()


def test_a_request_from_a_peer_close_handler_raises() -> None:
    """The socket is gone while the close's events run, so a request a
    handler sends raises instead of being dropped."""
    session = Session()
    ready(session)
    sent = len(session.conn.sent)
    raised: list[str] = []

    def requestOnError(_message: str) -> None:
        try:
            session.client.reqCurrentTime()
        except ConnectionError as error:
            raised.append(str(error))

    session.client.apiError += requestOnError
    session.client._onSocketDisconnected("")

    assert raised == ["Not connected"]
    assert len(session.conn.sent) == sent


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
