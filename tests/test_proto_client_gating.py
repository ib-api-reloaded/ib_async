"""Send-side per-msgId gating tests.

For each Phase 1 ``Client`` send method, verify:

1. On a server below the per-family gate, the legacy NUL-separated
   binary frame goes out (no protobuf).
2. On a server at or above the gate, a protobuf-framed message goes
   out — 4-byte big-endian wire ``msgId = canonical + 200``, then a
   serializable proto body.
3. Round-tripping the proto body produces the right user-supplied
   values (the ``clientId`` regression for ``placeOrder``, the
   ``apiOnly`` flag for ``reqCompletedOrders``, etc.).

Per-family gating is the design point: a server at version 207 emits
protobuf for accounts/positions but binary for historical data, etc.
The ``useProtoBuf(canonicalMsgId)`` boolean encodes that exactly.
"""

from __future__ import annotations

import struct

import ib_async as ibi
from ib_async._pb import (
    AutoOpenOrdersRequest_pb2,
    CancelOrderRequest_pb2,
    CompletedOrdersRequest_pb2,
    ContractDataRequest_pb2,
    ExecutionRequest_pb2,
    PlaceOrderRequest_pb2,
)
from ib_async._pb_msgids import (
    CANCEL_ORDER,
    PLACE_ORDER,
    PROTOBUF_MSG_ID,
    REQ_ALL_OPEN_ORDERS,
    REQ_AUTO_OPEN_ORDERS,
    REQ_COMPLETED_ORDERS,
    REQ_CONTRACT_DATA,
    REQ_EXECUTIONS,
    REQ_GLOBAL_CANCEL,
    REQ_OPEN_ORDERS,
)


def _ibAtVersion(version: int):
    ib = ibi.IB()
    ib.client._serverVersion = version
    # Pretend the client is connected so binary ``send()`` doesn't raise
    # ConnectionError. We replace ``conn.sendMsg`` with a capture list
    # in the test, so no real socket I/O happens.
    ib.client.connState = ib.client.CONNECTED
    return ib


def _captureSend(ib):
    """Replace the connection's sendMsg with a capture list that the
    test can inspect. Returns the list of bytes written."""
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


# ---------------------------------------------------------------------------
# placeOrder — gates at 203, regression-proves clientId round-trip
# ---------------------------------------------------------------------------


def test_place_order_uses_binary_below_gate():
    ib = _ibAtVersion(202)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    order = ibi.LimitOrder("BUY", 100, 50.5)
    order.clientId = 7
    ib.client.placeOrder(orderId=42, contract=contract, order=order)
    # Binary frame body starts with NUL-separated text "3\x00..." not
    # 4-byte big-endian wire msgId.
    assert sent
    body = sent[0][4:]
    assert body.startswith(b"3\x00")  # canonical PLACE_ORDER as NUL-text


def test_place_order_uses_protobuf_at_gate_and_round_trips_clientId():
    ib = _ibAtVersion(203)  # MIN_SERVER_VER_PROTOBUF_PLACE_ORDER
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    order = ibi.LimitOrder("BUY", 100, 50.5)
    order.clientId = 7
    ib.client.placeOrder(orderId=42, contract=contract, order=order)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == PLACE_ORDER
    proto = PlaceOrderRequest_pb2.PlaceOrderRequest()
    proto.ParseFromString(body)
    # The clientId regression: must round-trip on the wire.
    assert proto.order.clientId == 7
    assert proto.order.totalQuantity == "100"
    assert proto.order.lmtPrice == 50.5


# ---------------------------------------------------------------------------
# cancelOrder — gates at 203
# ---------------------------------------------------------------------------


def test_cancel_order_uses_protobuf_at_gate():
    from ib_async.order import OrderCancel

    ib = _ibAtVersion(203)
    sent = _captureSend(ib)
    ib.client.cancelOrder(
        orderId=42,
        orderCancel=OrderCancel(manualOrderCancelTime="20300101 09:30:00"),
    )
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_ORDER
    proto = CancelOrderRequest_pb2.CancelOrderRequest()
    proto.ParseFromString(body)
    assert proto.orderId == 42
    assert proto.orderCancel.manualOrderCancelTime == "20300101 09:30:00"


def test_cancel_order_uses_binary_below_gate():
    ib = _ibAtVersion(201)
    sent = _captureSend(ib)
    ib.client.cancelOrder(orderId=42)
    assert sent[0][4:].startswith(b"4\x00")  # CANCEL_ORDER as NUL-text


# ---------------------------------------------------------------------------
# Empty-body request envelopes
# ---------------------------------------------------------------------------


def test_req_open_orders_uses_protobuf_at_gate():
    # gate is REST_MESSAGES_2 (212) — actually REQ_OPEN_ORDERS is gated
    # at COMPLETED_ORDER (204) per the table.
    ib = _ibAtVersion(204)
    sent = _captureSend(ib)
    ib.client.reqOpenOrders()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_OPEN_ORDERS
    # Body for OpenOrdersRequest is empty.
    assert body == b""


def test_req_all_open_orders_uses_protobuf_at_gate():
    ib = _ibAtVersion(204)
    sent = _captureSend(ib)
    ib.client.reqAllOpenOrders()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_ALL_OPEN_ORDERS
    assert body == b""


def test_req_global_cancel_uses_protobuf_at_gate():
    ib = _ibAtVersion(203)
    sent = _captureSend(ib)
    ib.client.reqGlobalCancel()
    canonical, _ = _decodeProtoFrame(sent[0])
    assert canonical == REQ_GLOBAL_CANCEL


# ---------------------------------------------------------------------------
# Single-flag request envelopes
# ---------------------------------------------------------------------------


def test_req_auto_open_orders_carries_bool_flag():
    ib = _ibAtVersion(204)
    sent = _captureSend(ib)
    ib.client.reqAutoOpenOrders(True)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_AUTO_OPEN_ORDERS
    proto = AutoOpenOrdersRequest_pb2.AutoOpenOrdersRequest()
    proto.ParseFromString(body)
    assert proto.autoBind is True


def test_req_completed_orders_carries_api_only_flag():
    ib = _ibAtVersion(204)
    sent = _captureSend(ib)
    ib.client.reqCompletedOrders(apiOnly=False)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_COMPLETED_ORDERS
    proto = CompletedOrdersRequest_pb2.CompletedOrdersRequest()
    proto.ParseFromString(body)
    # Empty proto3 default for unset bool is False; we want explicit
    # round-trip when caller passes True.
    sent.clear()
    ib.client.reqCompletedOrders(apiOnly=True)
    _, body = _decodeProtoFrame(sent[0])
    proto.ParseFromString(body)
    assert proto.apiOnly is True


# ---------------------------------------------------------------------------
# reqContractDetails — gates at 205, contract envelope
# ---------------------------------------------------------------------------


def test_req_contract_details_uses_protobuf_at_gate():
    ib = _ibAtVersion(205)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqContractDetails(reqId=7, contract=contract)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_CONTRACT_DATA
    proto = ContractDataRequest_pb2.ContractDataRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.contract.symbol == "AAPL"
    assert proto.contract.secType == "STK"


def test_req_contract_details_below_gate_stays_binary():
    ib = _ibAtVersion(204)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqContractDetails(reqId=7, contract=contract)
    assert sent[0][4:].startswith(b"9\x00")  # canonical REQ_CONTRACT_DATA


# ---------------------------------------------------------------------------
# reqExecutions — gates at 201
# ---------------------------------------------------------------------------


def test_req_executions_uses_protobuf_at_gate():
    ib = _ibAtVersion(201)
    sent = _captureSend(ib)
    ef = ibi.ExecutionFilter(clientId=7, symbol="AAPL")
    ib.client.reqExecutions(reqId=42, execFilter=ef)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_EXECUTIONS
    proto = ExecutionRequest_pb2.ExecutionRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 42
    assert proto.executionFilter.clientId == 7
    assert proto.executionFilter.symbol == "AAPL"
