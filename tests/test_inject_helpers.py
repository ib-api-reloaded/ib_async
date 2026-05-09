"""Smoke tests for the test-injection helpers — guards against regressions
in the helper signature or in Wrapper's internal trade/fill keying that
would silently break dependent tests."""

import ib_async as ibi
from ib_async.order import OrderStatus
from tests._helpers import inject_fill, inject_trade


def test_inject_trade_uses_wrapper_clientId_by_default():
    ib = ibi.IB()
    ib.wrapper.clientId = 7

    trade = inject_trade(ib, orderId=42)

    assert ib.wrapper.trades[(7, 42)] is trade
    assert trade.order.clientId == 7
    assert trade.order.orderId == 42
    assert trade.orderStatus.status == OrderStatus.Submitted


def test_inject_trade_explicit_status_and_contract():
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = ibi.Stock("MSFT", "SMART", "USD")

    trade = inject_trade(
        ib, orderId=9, contract=contract, status=OrderStatus.Filled, conId=88
    )

    assert trade.contract is contract
    assert trade.contract.conId == 88
    assert trade.orderStatus.status == OrderStatus.Filled


def test_inject_fill_registers_on_wrapper_keyed_by_execId():
    ib = ibi.IB()

    fill = inject_fill(ib, execId="exec-xyz", permId=11)

    assert ib.wrapper.fills["exec-xyz"] is fill
    assert fill.execution.execId == "exec-xyz"
    assert fill.execution.permId == 11
