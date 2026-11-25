"""A refused cancel leaves the order as it was.

IBKR refuses a cancel with 136, 137, 161 or 10148 when the order cannot be
cancelled: it has filled, it is already being cancelled, or it is not in a
cancellable state. The refusal is about the cancel request, not the order:
the order keeps working, or it has ended and a status says how. The trade
keeps the status TWS last reported (or the local PendingCancel), logs the
refusal with its code, and fires no cancelledEvent.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

import ib_async as ibi
from ib_async import CommissionReport, OrderStatus, Trade
from ib_async.util import getLoop
from tests._sim import CONTRACT, EXECUTED, PlacedOrder, SimulatedTws

REFUSED_CANCEL = [136, 137, 161, 10148]


class Order:
    """A limit order for 5 shares, its events by name, the status events
    of the trade and of IB, and the error codes errorEvent reported."""

    def __init__(self, *, acknowledged: bool = True) -> None:
        self.tws = SimulatedTws(getLoop())
        self.trade: Trade = self.tws.ib.placeOrder(
            CONTRACT, ibi.LimitOrder("BUY", 5, 50.00)
        )
        self.tws.run()
        self.placed: PlacedOrder = self.tws.orders[self.trade.order.orderId]
        self.events: list[str] = []
        self.trade.cancelledEvent += lambda t: self.events.append("cancelled")
        self.trade.filledEvent += lambda t: self.events.append("filled")
        self.statuses: list[str] = []
        self.trade.statusEvent += lambda t: self.statuses.append("trade")
        self.tws.ib.orderStatusEvent += lambda t: self.statuses.append("ib")
        self.errors: list[int] = []
        self.tws.ib.errorEvent += lambda reqId, code, text, c: self.errors.append(code)
        if acknowledged:
            self.tws.acknowledge(self.placed)

    def cancel(self) -> None:
        self.tws.ib.cancelOrder(self.trade.order)
        self.tws.run()

    def execution(self, shares: Decimal) -> None:
        """An execution with no orderStatus after it; IBKR does not
        guarantee a status for every change."""
        execId = f"0000e9b5.{self.placed.orderId:04x}{len(self.trade.fills):04x}.01.01"
        execution = ibi.Execution(
            execId=execId,
            time=EXECUTED,
            shares=shares,
            price=Decimal(50),
            permId=self.placed.order.permId,
            clientId=self.placed.order.clientId,
            orderId=self.placed.orderId,
        )
        self.tws.wrapper.execDetails(-1, self.placed.contract, execution)
        self.tws.wrapper.commissionReport(
            CommissionReport(execId=execId, commissionAndFees=Decimal(1))
        )
        self.placed.filled += shares
        self.tws.run()

    @property
    def open(self) -> bool:
        return self.trade in self.tws.ib.openTrades()


@pytest.mark.parametrize("code", REFUSED_CANCEL)
def test_a_refusal_before_the_fill_status_fires_only_filled(code: int) -> None:
    o = Order()
    o.cancel()
    o.statuses.clear()
    o.tws.refuseCancel(o.placed, code)

    assert o.trade.orderStatus.status == OrderStatus.PendingCancel
    assert o.trade.log[-1].errorCode == code and o.errors == [code]
    assert sorted(o.statuses) == ["ib", "trade"]
    assert o.open and not o.trade.isDone()
    o.tws.fill(o.placed, Decimal(5))
    assert o.trade.orderStatus.status == OrderStatus.Filled
    assert o.events == ["filled"]


@pytest.mark.parametrize("code", REFUSED_CANCEL)
def test_a_refusal_after_the_fill_status_changes_nothing(code: int) -> None:
    o = Order()
    o.cancel()
    o.tws.fill(o.placed, Decimal(5))
    o.tws.refuseCancel(o.placed, code)

    assert o.trade.orderStatus.status == OrderStatus.Filled
    assert o.events == ["filled"] and o.errors == [code]


def test_executions_then_a_refusal_wait_for_the_fill_status() -> None:
    o = Order()
    o.cancel()
    o.execution(Decimal(5))
    o.tws.refuseCancel(o.placed, 10148)

    assert o.trade.orderStatus.status == OrderStatus.PendingCancel
    assert o.trade.filled() == Decimal(5)
    o.tws._orderStatus(o.placed, "Filled")
    o.tws.run()
    assert o.events == ["filled"]


def test_a_second_cancel_refused_leaves_the_first_pending() -> None:
    o = Order()
    o.cancel()
    o.cancel()
    o.tws.refuseCancel(o.placed, 10148)

    assert o.trade.orderStatus.status == OrderStatus.PendingCancel
    o.tws.cancelOrder(o.placed)
    assert o.trade.orderStatus.status == OrderStatus.Cancelled
    assert o.events == ["cancelled"]


def test_a_refused_cancel_leaves_the_order_working() -> None:
    o = Order()
    o.cancel()
    o.tws.refuseCancel(o.placed, 137)

    assert o.open and not o.trade.isDone()
    o.tws.fill(o.placed, Decimal(2))
    assert o.trade.orderStatus.status == OrderStatus.Submitted
    assert o.events == []


def test_a_refusal_after_a_partial_fill_keeps_its_status() -> None:
    o = Order()
    o.cancel()
    o.tws.fill(o.placed, Decimal(2))
    o.tws.refuseCancel(o.placed, 137)

    assert o.trade.orderStatus.status == OrderStatus.Submitted
    assert o.trade.log[-1].status == OrderStatus.Submitted
    assert o.trade.log[-1].errorCode == 137


def test_a_cancel_refused_before_the_acknowledgement() -> None:
    o = Order(acknowledged=False)
    o.cancel()
    o.tws.refuseCancel(o.placed, 161)

    assert o.trade.orderStatus.status == OrderStatus.PendingCancel
    o.tws.acknowledge(o.placed)
    assert o.trade.orderStatus.status == OrderStatus.Submitted
    assert o.events == []


def test_a_rejected_new_order_still_ends() -> None:
    o = Order(acknowledged=False)
    o.tws.rejectOrder(o.placed, 201)

    assert o.trade.orderStatus.status == OrderStatus.Cancelled
    assert o.events == ["cancelled"]


def test_a_cancel_tws_confirms_ends_once() -> None:
    o = Order()
    o.cancel()
    o.tws.wrapper.error(o.placed.orderId, 202, "Order cancelled - Reason:", "")
    o.tws.cancelOrder(o.placed)

    assert o.trade.orderStatus.status == OrderStatus.Cancelled
    assert o.events == ["cancelled"]
