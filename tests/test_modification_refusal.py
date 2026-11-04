"""An order error ends the order only if it refers to the order.

TWS reports a refused modification through the error callback and sends no
status: the order keeps working on its old terms. Marking it Cancelled makes
an application replace an order that is still live.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

import ib_async as ibi
from ib_async import OrderStatus, Trade
from ib_async.util import getLoop
from tests._sim import CONTRACT, PlacedOrder, SimulatedTws

# Each ends an order that was not modified after TWS acknowledged it.
ENDS_UNMODIFIED_ORDER = [104, 134, 201, 422, 439, 440, 441, 442, 443, 444, 10241, 10242]

# Warnings for any order.
ALWAYS_WARNINGS = [105, 329, 2102]


class Scenario:
    """An order at a simulated TWS and the cancelled events it fired."""

    def __init__(self, *, acknowledged: bool = True) -> None:
        self.tws = SimulatedTws(getLoop())
        self.trade: Trade = self.tws.ib.placeOrder(
            CONTRACT, ibi.LimitOrder("BUY", 5, 50.00)
        )
        self.tws.run()
        self.placed: PlacedOrder = self.tws.orders[self.trade.order.orderId]
        self.cancelled: list[Trade] = []
        self.trade.cancelledEvent += self.cancelled.append
        if acknowledged:
            self.tws.acknowledge(self.placed)

    def modify(self) -> None:
        self.trade.order.lmtPrice = Decimal(51)
        self.tws.ib.placeOrder(CONTRACT, self.trade.order)
        self.tws.run()

    def assertStillWorking(self) -> None:
        assert self.trade.orderStatus.status == OrderStatus.ValidationError
        assert self.cancelled == []
        assert self.trade.isActive() and not self.trade.isDone()
        assert self.trade in self.tws.ib.openTrades()

    def assertCancelled(self) -> None:
        assert self.trade.orderStatus.status == OrderStatus.Cancelled
        assert self.cancelled == [self.trade]
        assert self.trade not in self.tws.ib.openTrades()


@pytest.mark.parametrize("code", ENDS_UNMODIFIED_ORDER)
def test_refused_modification_leaves_the_order_working(code: int) -> None:
    scenario = Scenario()
    scenario.modify()
    scenario.tws.refuseModification(scenario.placed, code)
    scenario.assertStillWorking()
    assert scenario.trade.log[-1].errorCode == code


@pytest.mark.parametrize("code", ALWAYS_WARNINGS)
def test_warning_code_leaves_any_order_working(code: int) -> None:
    scenario = Scenario()
    scenario.tws.rejectOrder(scenario.placed, code)
    scenario.assertStillWorking()


@pytest.mark.parametrize("code", ENDS_UNMODIFIED_ORDER)
def test_new_order_error_still_cancels(code: int) -> None:
    scenario = Scenario(acknowledged=False)
    scenario.tws.rejectOrder(scenario.placed, code)
    scenario.assertCancelled()


@pytest.mark.parametrize("code", ENDS_UNMODIFIED_ORDER)
def test_error_on_an_unmodified_working_order_still_cancels(code: int) -> None:
    scenario = Scenario()
    scenario.tws.rejectOrder(scenario.placed, code)
    scenario.assertCancelled()


def test_error_after_a_new_order_modified_before_its_acknowledgement_cancels() -> None:
    """The error may reject the order itself, which TWS has not accepted."""
    scenario = Scenario(acknowledged=False)
    scenario.modify()
    scenario.tws.rejectOrder(scenario.placed)
    scenario.assertCancelled()


@pytest.mark.parametrize("code", ENDS_UNMODIFIED_ORDER)
def test_repeated_status_does_not_answer_a_modification(code: int) -> None:
    """TWS often repeats a status, and a status carries no order terms."""
    scenario = Scenario()
    scenario.modify()
    scenario.tws.repeatStatus(scenario.placed)
    scenario.tws.refuseModification(scenario.placed, code)
    scenario.assertStillWorking()


def test_error_after_an_accepted_modification_waits_for_the_status() -> None:
    """The status for an accepted modification looks like a repeated one, so
    the order stays live until TWS reports that it ended."""
    scenario = Scenario()
    scenario.modify()
    scenario.tws.acknowledge(scenario.placed)
    scenario.tws.rejectOrder(scenario.placed)
    scenario.assertStillWorking()
    scenario.tws.cancelOrder(scenario.placed)
    scenario.assertCancelled()


def test_error_after_a_modification_sent_before_the_acknowledgement_cancels() -> None:
    """Only a modification of an acknowledged order can leave it working."""
    scenario = Scenario(acknowledged=False)
    scenario.modify()
    scenario.tws.acknowledge(scenario.placed)
    scenario.tws.rejectOrder(scenario.placed)
    scenario.assertCancelled()


def test_held_order_that_goes_inactive_fires_its_cancelled_event() -> None:
    """Without the hold, the error would have fired it."""
    scenario = Scenario()
    scenario.modify()
    scenario.tws.rejectOrder(scenario.placed)
    scenario.assertStillWorking()
    scenario.tws.deactivate(scenario.placed)
    assert scenario.trade.orderStatus.status == OrderStatus.Inactive
    assert scenario.cancelled == [scenario.trade]


def test_inactive_order_that_was_not_held_fires_no_cancelled_event() -> None:
    scenario = Scenario()
    scenario.tws.deactivate(scenario.placed)
    assert scenario.trade.orderStatus.status == OrderStatus.Inactive
    assert scenario.cancelled == []


def test_held_error_keeps_the_advanced_reject() -> None:
    scenario = Scenario()
    scenario.modify()
    scenario.tws.wrapper.error(
        scenario.placed.orderId, 201, "Order rejected - reason:", '{"reject": 1}'
    )
    assert scenario.trade.advancedError == '{"reject": 1}'


def test_modification_does_not_change_how_a_trade_prints_or_compares() -> None:
    scenario = Scenario()
    other = dataclasses.replace(scenario.trade)
    scenario.modify()
    assert scenario.trade.modifyUnconfirmed
    assert "modifyUnconfirmed" not in repr(scenario.trade)
    assert scenario.trade == other


def test_order_canceled_during_a_modification_cancels() -> None:
    scenario = Scenario()
    scenario.modify()
    scenario.tws.rejectOrder(scenario.placed, 202)
    scenario.assertCancelled()


def test_fill_does_not_answer_a_modification() -> None:
    """A partial fill's status can land between a modification and its
    refusal."""
    scenario = Scenario()
    scenario.modify()
    scenario.tws.fill(scenario.placed, Decimal(1))
    scenario.tws.refuseModification(scenario.placed)
    scenario.assertStillWorking()
    assert scenario.trade.filled() == 1


def test_open_order_does_not_answer_a_modification() -> None:
    """TWS can send openOrder with the requested values before refusing."""
    scenario = Scenario()
    scenario.modify()
    scenario.tws.wrapper.openOrder(
        scenario.placed.orderId,
        CONTRACT,
        scenario.placed.order,
        ibi.OrderState(status="PreSubmitted"),
    )
    scenario.tws.refuseModification(scenario.placed)
    scenario.assertStillWorking()


def test_two_errors_for_one_refusal_leave_the_order_working() -> None:
    scenario = Scenario()
    scenario.modify()
    scenario.tws.refuseModification(scenario.placed, 439)
    scenario.tws.refuseModification(scenario.placed, 201)
    scenario.assertStillWorking()


def test_order_recovers_from_a_refusal_and_cancels_once() -> None:
    scenario = Scenario()
    scenario.modify()
    scenario.tws.refuseModification(scenario.placed)
    scenario.tws.acknowledge(scenario.placed)
    assert scenario.trade.orderStatus.status == OrderStatus.Submitted
    assert scenario.cancelled == []
    scenario.tws.cancelOrder(scenario.placed)
    scenario.assertCancelled()


def test_refused_modification_can_be_sent_again() -> None:
    scenario = Scenario()
    scenario.modify()
    scenario.tws.refuseModification(scenario.placed)
    scenario.modify()
    scenario.tws.refuseModification(scenario.placed)
    scenario.assertStillWorking()
    scenario.tws.acknowledge(scenario.placed)
    assert scenario.trade.orderStatus.status == OrderStatus.Submitted
