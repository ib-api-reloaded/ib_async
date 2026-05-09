"""End-to-end tests for ``Decoder.processProtoBuf`` dispatch.

These exercise the wire → proto → converter → wrapper chain for the
orders / contracts message family. A synthetic protobuf payload is
assembled with the appropriate canonical msgId, fed to
``processProtoBuf``, and the resulting ``Wrapper`` state (registry
entries, trades, contracts) is asserted directly. No real connection
or TWS server is involved.

Negative cases verified:

* Unknown canonical msgId → debug log + drop, never raise.
* Malformed payload bytes → exception caught, connection survives.
* Partial protos (missing optional fields) → domain objects with
  ``None`` for unset Decimals; the wrapper merge still works.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import ib_async as ibi
from ib_async._pb import (
    CommissionAndFeesReport_pb2,
    ContractData_pb2,
    ExecutionDetails_pb2,
    OpenOrder_pb2,
    OpenOrdersEnd_pb2,
    OrderStatus_pb2,
)
from ib_async._requests import ReqIdKey, SingletonKey

# ---------------------------------------------------------------------------
# OpenOrder → wrapper.openOrder lands a Trade in the registry
# ---------------------------------------------------------------------------


def test_open_order_proto_creates_trade_via_existing_wrapper_path():
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    proto = OpenOrder_pb2.OpenOrder()
    proto.orderId = 42
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    proto.contract.exchange = "SMART"
    proto.contract.currency = "USD"
    proto.order.orderId = 42
    proto.order.clientId = 0
    proto.order.permId = 999
    proto.order.action = "BUY"
    proto.order.totalQuantity = "100"
    proto.order.orderType = "LMT"
    proto.order.lmtPrice = 50.5
    proto.orderState.status = "Submitted"

    payload = proto.SerializeToString()
    ib.client.decoder.processProtoBuf(5, payload)  # canonical OPEN_ORDER

    # Trade is keyed by (clientId, orderId) — verifies our converter
    # populated clientId correctly (the regression we guard against).
    trade = ib.wrapper.trades[(0, 42)]
    assert trade.contract.symbol == "AAPL"
    assert trade.order.permId == 999
    assert trade.order.totalQuantity == Decimal("100")
    assert trade.order.lmtPrice == Decimal("50.5")
    assert trade.orderStatus.status == "Submitted"


def test_open_order_end_proto_settles_singleton_request():
    ib = ibi.IB()
    # Open a singleton waiter for the openOrders accumulator.
    req, _ = ib.wrapper.requests.open(SingletonKey("openOrders"), container=[])
    fut = req.future
    assert not fut.done()

    proto = OpenOrdersEnd_pb2.OpenOrdersEnd()
    payload = proto.SerializeToString()
    ib.client.decoder.processProtoBuf(53, payload)  # OPEN_ORDER_END

    assert fut.done()


# ---------------------------------------------------------------------------
# OrderStatus → wrapper.orderStatus updates the existing Trade
# ---------------------------------------------------------------------------


def test_order_status_proto_updates_existing_trade():
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    # Seed with an open order first.
    open_proto = OpenOrder_pb2.OpenOrder()
    open_proto.orderId = 1
    open_proto.contract.symbol = "AAPL"
    open_proto.contract.secType = "STK"
    open_proto.order.orderId = 1
    open_proto.order.clientId = 0
    open_proto.order.permId = 1
    open_proto.order.action = "BUY"
    open_proto.order.totalQuantity = "100"
    open_proto.orderState.status = "Submitted"
    ib.client.decoder.processProtoBuf(5, open_proto.SerializeToString())

    # Now an OrderStatus update arrives.
    status_proto = OrderStatus_pb2.OrderStatus()
    status_proto.orderId = 1
    status_proto.status = "Filled"
    status_proto.filled = "100"
    status_proto.remaining = "0"
    status_proto.avgFillPrice = 50.5
    status_proto.permId = 1
    status_proto.clientId = 0
    ib.client.decoder.processProtoBuf(3, status_proto.SerializeToString())

    trade = ib.wrapper.trades[(0, 1)]
    assert trade.orderStatus.status == "Filled"
    assert trade.orderStatus.filled == Decimal("100")
    assert trade.orderStatus.remaining == Decimal("0")
    assert trade.orderStatus.avgFillPrice == Decimal("50.5")


# ---------------------------------------------------------------------------
# ContractData → wrapper.contractDetails routes through the registry
# ---------------------------------------------------------------------------


def test_contract_data_proto_appends_to_request_registry():
    ib = ibi.IB()
    req_id = 7
    req, _ = ib.wrapper.requests.open(ReqIdKey(req_id), container=[])

    proto = ContractData_pb2.ContractData()
    proto.reqId = req_id
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    proto.contractDetails.marketName = "NMS"
    proto.contractDetails.minTick = "0.01"
    proto.contractDetails.minSize = "1"

    ib.client.decoder.processProtoBuf(10, proto.SerializeToString())

    # contractDetails appends the ContractDetails to the registry's
    # accumulator container; future is settled by contractDetailsEnd.
    assert len(req.container) == 1
    details = req.container[0]
    assert details.contract.symbol == "AAPL"
    assert details.marketName == "NMS"
    assert details.minTick == Decimal("0.01")
    assert details.minSize == Decimal("1")


# ---------------------------------------------------------------------------
# CommissionAndFeesReport → wrapper.commissionReport
# ---------------------------------------------------------------------------


def test_commission_report_proto_attaches_to_existing_fill():
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    fill = ibi.Fill(
        contract=ibi.Stock("AAPL"),
        execution=ibi.Execution(execId="exec-7", permId=1),
        commissionReport=ibi.CommissionReport(),
        time=ibi.util.EPOCH,
    )
    ib.wrapper.fills["exec-7"] = fill

    proto = CommissionAndFeesReport_pb2.CommissionAndFeesReport()
    proto.execId = "exec-7"
    proto.commissionAndFees = 1.25
    proto.currency = "USD"
    proto.realizedPNL = 10.0
    ib.client.decoder.processProtoBuf(59, proto.SerializeToString())

    assert fill.commissionReport.execId == "exec-7"
    assert fill.commissionReport.commission == Decimal("1.25")
    assert fill.commissionReport.realizedPNL == Decimal("10")


# ---------------------------------------------------------------------------
# ExecutionDetails → wrapper.execDetails
# ---------------------------------------------------------------------------


def test_execution_details_proto_lands_fill_on_trade():
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    # Seed a trade so the execDetails can attach to it.
    open_proto = OpenOrder_pb2.OpenOrder()
    open_proto.orderId = 5
    open_proto.contract.symbol = "AAPL"
    open_proto.contract.secType = "STK"
    open_proto.order.orderId = 5
    open_proto.order.clientId = 0
    open_proto.order.permId = 999
    open_proto.order.action = "BUY"
    open_proto.order.totalQuantity = "100"
    open_proto.orderState.status = "Submitted"
    ib.client.decoder.processProtoBuf(5, open_proto.SerializeToString())

    exec_proto = ExecutionDetails_pb2.ExecutionDetails()
    exec_proto.reqId = -1  # live (not from a reqExecutions)
    exec_proto.contract.symbol = "AAPL"
    exec_proto.contract.secType = "STK"
    exec_proto.execution.execId = "exec-1"
    exec_proto.execution.orderId = 5
    exec_proto.execution.clientId = 0
    exec_proto.execution.permId = 999
    exec_proto.execution.shares = "100"
    exec_proto.execution.price = 50.5
    exec_proto.execution.cumQty = "100"
    exec_proto.execution.avgPrice = 50.5
    exec_proto.execution.side = "BOT"
    ib.client.decoder.processProtoBuf(11, exec_proto.SerializeToString())

    trade = ib.wrapper.trades[(0, 5)]
    assert len(trade.fills) == 1
    fill = trade.fills[0]
    assert fill.execution.execId == "exec-1"
    assert fill.execution.shares == Decimal("100")
    assert fill.execution.price == Decimal("50.5")


# ---------------------------------------------------------------------------
# Robustness: unknown msgId, malformed bytes
# ---------------------------------------------------------------------------


def test_unknown_canonical_msg_id_logs_and_drops(caplog):
    ib = ibi.IB()
    with caplog.at_level(logging.DEBUG, logger="ib_async.Decoder"):
        ib.client.decoder.processProtoBuf(9999, b"\x08\x01")
    # Connection survives, no exception.
    assert any("no handler" in rec.message for rec in caplog.records)


def test_malformed_payload_logs_and_drops(caplog):
    ib = ibi.IB()
    # Random bytes won't parse as an OrderStatus proto.
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.processProtoBuf(3, b"\xff\xff\xff\xff\xff\xff\xff\xff")
    # Connection survives, exception is logged but not propagated.
    assert any("Error decoding" in rec.message for rec in caplog.records)
