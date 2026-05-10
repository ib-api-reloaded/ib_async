"""Shared test helpers for injecting trades and fills directly into a
Wrapper without going through the wire, and the small ``IB``-construction
helpers shared across the ``test_proto_*_dispatch`` suites.

Used by tests that exercise post-state behaviour (a late error, a
disconnect-driven teardown, a commissionReport callback for a known fill)
without setting up the full IB connection lifecycle.

Existing tests pre-date these helpers and use inline construction; new
tests should prefer ``inject_trade`` / ``inject_fill`` so the test layer
has one place to update if Wrapper's internal trade/fill maps ever
restructure.

``_ibAtVersion`` / ``_captureSend`` / ``_decodeProtoFrame`` live here
because every ``test_proto_*_dispatch.py`` defined the same body —
keeping one canonical implementation means a future tweak to the
``IB`` faux-connect dance happens in exactly one place.
"""

from __future__ import annotations

import struct

import ib_async as ibi
from ib_async._pb_msgids import PROTOBUF_MSG_ID
from ib_async.order import Order, OrderStatus, Trade


def inject_trade(
    ib: ibi.IB,
    *,
    orderId: int = 1,
    permId: int = 1,
    clientId: int | None = None,
    status: str = OrderStatus.Submitted,
    contract: ibi.Contract | None = None,
    conId: int | None = 12345,
) -> Trade:
    """Construct a Trade and register it on the wrapper's trades map.

    The trade is keyed by ``(clientId, orderId)`` exactly as the live
    ``openOrder`` callback would key it. ``clientId`` defaults to whatever
    is currently set on the wrapper, so callers in tests that pin
    ``ib.wrapper.clientId = 0`` can omit it.
    """
    if clientId is None:
        clientId = ib.wrapper.clientId
    if contract is None:
        contract = ibi.Stock("ABC", "SMART", "USD")
    if conId is not None:
        contract.conId = conId

    order = Order(orderId=orderId, clientId=clientId, permId=permId)
    orderStatus = OrderStatus(orderId=orderId, status=status)
    trade = Trade(contract, order, orderStatus, [], [])
    ib.wrapper.trades[(clientId, orderId)] = trade
    return trade


def inject_fill(
    ib: ibi.IB,
    *,
    execId: str,
    permId: int = 1,
    contract: ibi.Contract | None = None,
    time: object | None = None,
) -> ibi.Fill:
    """Construct a Fill and register it on the wrapper's fills map keyed
    by execId."""
    if contract is None:
        contract = ibi.Stock("AAPL")
    if time is None:
        time = ibi.util.EPOCH

    fill = ibi.Fill(
        contract=contract,
        execution=ibi.Execution(execId=execId, permId=permId),
        commissionReport=ibi.CommissionReport(),
        time=time,
    )
    ib.wrapper.fills[execId] = fill
    return fill


def _ibAtVersion(version: int) -> ibi.IB:
    """Construct an ``IB`` pinned to the given server version with the
    client pretend-connected.

    Tests that exercise gated send paths or proto dispatch need the
    client past the ``CONNECTED`` guard so ``Client.send`` doesn't raise
    ``ConnectionError`` and ``Decoder.processProtoBuf`` runs at the right
    serverVersion. No real socket I/O happens — tests replace
    ``conn.sendMsg`` via ``_captureSend``.
    """
    ib = ibi.IB()
    ib.client._serverVersion = version
    ib.client.connState = ib.client.CONNECTED
    return ib


def _captureSend(ib: ibi.IB) -> list[bytes]:
    """Replace the connection's ``sendMsg`` with a capture list the test
    can inspect. Returns the list of bytes written."""
    sent: list[bytes] = []
    ib.client.conn.sendMsg = sent.append  # type: ignore[method-assign]
    return sent


def _decodeProtoFrame(framed: bytes) -> tuple[int, bytes]:
    """Strip the 4-byte length prefix, then read the 4-byte BE wire
    msgId. Returns ``(canonicalMsgId, bodyBytes)`` where canonical is
    ``wire - PROTOBUF_MSG_ID``."""
    body_len = struct.unpack(">I", framed[:4])[0]
    body = framed[4 : 4 + body_len]
    wireMsgId = struct.unpack(">I", body[:4])[0]
    return wireMsgId - PROTOBUF_MSG_ID, body[4:]
