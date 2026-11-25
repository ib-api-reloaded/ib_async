"""An execution that looks like IBKR's correction of an earlier one is logged.

IBKR documents a correction as the same execution sent again with an execId
that differs only in the digits after the final period (".02" corrects
".01"). What else a correction carries (its commission, a changed price or
quantity) and how combo leg ids interact with it are not documented, so
ib_async keeps every execution as received and logs a warning naming both
execIds. Trade.filled() counts both; orderStatus.filled is TWS's total.
"""

from __future__ import annotations

import logging
from decimal import Decimal

import pytest

import ib_async as ibi
from ib_async import Trade
from ib_async.util import getLoop
from tests._sim import CONTRACT, EXECUTED, PlacedOrder, SimulatedTws


class Order:
    def __init__(self, quantity: int = 5) -> None:
        self.tws = SimulatedTws(getLoop())
        self.trade: Trade = self.tws.ib.placeOrder(
            CONTRACT, ibi.LimitOrder("BUY", quantity, 50.00)
        )
        self.tws.run()
        self.placed: PlacedOrder = self.tws.orders[self.trade.order.orderId]
        self.tws.acknowledge(self.placed)


def corrections(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if "correction" in r.getMessage()]


def test_a_correction_is_logged_and_kept_as_received(
    caplog: pytest.LogCaptureFixture,
) -> None:
    o = Order()
    execId = o.tws.fill(o.placed, Decimal(2))

    with caplog.at_level(logging.WARNING):
        correctionId = o.tws.correctFill(execId)

    assert correctionId == execId[:-2] + "02"
    [message] = corrections(caplog)
    assert correctionId in message and execId in message
    # Kept as received: both count until IBKR documents what a correction
    # replaces. TWS's own total is unchanged.
    assert o.trade.filled() == Decimal(4)
    assert o.trade.orderStatus.filled == Decimal(2)


def test_two_executions_of_an_order_are_not_corrections(
    caplog: pytest.LogCaptureFixture,
) -> None:
    o = Order()
    with caplog.at_level(logging.WARNING):
        o.tws.fill(o.placed, Decimal(2))
        o.tws.fill(o.placed, Decimal(2))

    assert corrections(caplog) == []
    assert o.trade.filled() == Decimal(4) == o.trade.orderStatus.filled


def test_the_same_execution_sent_again_is_not_a_correction(
    caplog: pytest.LogCaptureFixture,
) -> None:
    o = Order()
    execId = o.tws.fill(o.placed, Decimal(2))
    with caplog.at_level(logging.WARNING):
        o.tws.repeatFill(execId)

    assert corrections(caplog) == []
    assert o.trade.filled() == Decimal(2)


BAG = ibi.Contract(
    secType="BAG",
    symbol="SPY",
    exchange="SMART",
    currency="USD",
    comboLegs=[
        ibi.ComboLeg(conId=101, ratio=1, action="BUY", exchange="SMART"),
        ibi.ComboLeg(conId=102, ratio=1, action="BUY", exchange="SMART"),
    ],
)
LEGS = [
    ibi.Stock("A", "SMART", "USD", conId=101),
    ibi.Stock("B", "SMART", "USD", conId=102),
]


class Combo:
    """A combo order for one unit of two 1:1 legs at a simulated TWS."""

    def __init__(self) -> None:
        self.tws = SimulatedTws(getLoop())
        self.trade: Trade = self.tws.ib.placeOrder(BAG, ibi.LimitOrder("BUY", 1, 1.0))
        self.tws.run()
        self.placed: PlacedOrder = self.tws.orders[self.trade.order.orderId]
        self.tws.acknowledge(self.placed)

    def execution(self, contract: ibi.Contract, execId: str) -> None:
        """One unit filled: every leg of a 1:1 combo has the same side,
        shares and cumulative quantity."""
        execution = ibi.Execution(
            execId=execId,
            time=EXECUTED,
            side="BOT",
            shares=Decimal(1),
            price=Decimal(1),
            permId=self.placed.order.permId,
            clientId=self.placed.order.clientId,
            orderId=self.placed.orderId,
            cumQty=Decimal(1),
        )
        self.tws.wrapper.execDetails(-1, contract, execution)
        self.tws.run()


# Two layouts of leg execIds: in a fifth segment under the bag's id, or
# sharing the bag's first three segments.
LEG_IDS = [
    ["0000e9b5.000000aa.01.01", "0000e9b5.000000aa.01.01.01", "0000e9b5.000000aa.01.01.02"],
    ["0000e9b5.000000aa.01.01", "0000e9b5.000000aa.01.02", "0000e9b5.000000aa.01.03"],
]  # fmt: skip


@pytest.mark.parametrize("ids", LEG_IDS)
def test_combo_leg_executions_are_not_corrections(
    caplog: pytest.LogCaptureFixture, ids: list[str]
) -> None:
    """The legs of a combo filled together differ only in contract."""
    combo = Combo()
    bagId, *legIds = ids
    with caplog.at_level(logging.WARNING):
        combo.execution(combo.placed.contract, bagId)
        for leg, legId in zip(LEGS, legIds, strict=True):
            combo.execution(leg, legId)

    assert corrections(caplog) == []
    assert combo.trade.filled() == Decimal(1)


def test_a_corrected_leg_is_found_among_its_siblings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Leg executions sharing an execId base are each kept, so a correction
    of the first leg is noticed after the second leg arrived."""
    combo = Combo()
    first, second = LEGS
    combo.execution(first, "0000e9b5.000000aa.01.02")
    combo.execution(second, "0000e9b5.000000aa.01.03")
    with caplog.at_level(logging.WARNING):
        combo.execution(first, "0000e9b5.000000aa.01.04")

    [message] = corrections(caplog)
    assert "0000e9b5.000000aa.01.04" in message
    assert "0000e9b5.000000aa.01.02" in message
