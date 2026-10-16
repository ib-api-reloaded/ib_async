"""Stateful test of order handling against a simulated TWS.

Hypothesis places, modifies and cancels orders. In any order, the
simulated TWS acknowledges, fills, cancels and rejects them, and the
socket drops and reconnects. Fills can be partial or full, and the
commission report can arrive before or after the execution.

After each step, every trade's status, fills, log and events must match
what happened to it. At the end the server fills every working order, and
no trade may be left open.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import ib_async as ibi
from ib_async import OrderStatus, Trade
from ib_async.util import getLoop
from tests._property import examples
from tests._sim import CONTRACT, PlacedOrder, SimulatedTws


@dataclass(eq=False)
class Counts:
    """Number of times each trade event fired."""

    status: int = 0
    fill: int = 0
    commission: int = 0
    filled: int = 0
    cancelled: int = 0


@dataclass(eq=False)
class Tracked:
    """An order placed by the test, and its expected state."""

    trade: Trade
    placed: PlacedOrder
    quantity: Decimal
    counts: Counts
    epoch: int
    fills: list[Decimal] = field(default_factory=list)
    reports: int = 0  # commission reports delivered
    clientCancelled: bool = False
    # The status TWS last reported. None before the first report, and None
    # again after the client sends a cancel.
    serverStatus: str | None = None
    ended: str = ""  # "filled", "cancelled", "rejected", "disconnected"

    @property
    def expectedStatus(self) -> str:
        if self.ended == "filled":
            return OrderStatus.Filled
        if self.ended in ("cancelled", "rejected"):
            return OrderStatus.Cancelled
        if self.ended == "disconnected":
            return OrderStatus.Disconnected
        if self.serverStatus is not None:
            return self.serverStatus
        if self.clientCancelled:
            return OrderStatus.PendingCancel
        return OrderStatus.PendingSubmit


def track(trade: Trade) -> Counts:
    counts = Counts()

    def bump(name: str):
        def on(*_: object) -> None:
            setattr(counts, name, getattr(counts, name) + 1)

        return on

    trade.statusEvent += bump("status")
    trade.fillEvent += bump("fill")
    trade.commissionReportEvent += bump("commission")
    trade.filledEvent += bump("filled")
    trade.cancelledEvent += bump("cancelled")
    return counts


class OrderSimulation(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = getLoop()
        self.tws = SimulatedTws(self.loop)
        self.tracked: list[Tracked] = []
        self.epoch = 0

    @property
    def ib(self) -> ibi.IB:
        return self.tws.ib

    def live(self) -> list[Tracked]:
        """Orders still working at the server on the current connection."""
        return [t for t in self.tracked if t.epoch == self.epoch and not t.ended]

    def pick(self, data: st.DataObject, candidates: list[Tracked]) -> Tracked:
        return candidates[data.draw(st.integers(0, len(candidates) - 1))]

    # -- client operations -----------------------------------------------

    @rule(limit=st.booleans(), quantity=st.integers(1, 6))
    def place(self, limit: bool, quantity: int) -> None:
        if not self.tws.connected:
            return
        order = (
            ibi.LimitOrder("BUY", quantity, 50.00)
            if limit
            else ibi.MarketOrder("BUY", quantity)
        )
        trade = self.ib.placeOrder(CONTRACT, order)
        self.tws.run()
        placed = self.tws.orders[trade.order.orderId]
        self.tracked.append(
            Tracked(trade, placed, Decimal(quantity), track(trade), self.epoch)
        )

    @rule(data=st.data(), price=st.integers(40, 60))
    def modify(self, data: st.DataObject, price: int) -> None:
        candidates = [t for t in self.live() if t.trade.order.orderType == "LMT"]
        if not candidates or not self.tws.connected:
            return
        tracked = self.pick(data, candidates)
        tracked.trade.order.lmtPrice = Decimal(price)
        self.ib.placeOrder(CONTRACT, tracked.trade.order)
        self.tws.run()

    @rule(data=st.data())
    def cancel(self, data: st.DataObject) -> None:
        candidates = [t for t in self.live() if not t.clientCancelled]
        if not candidates or not self.tws.connected:
            return
        tracked = self.pick(data, candidates)
        self.ib.cancelOrder(tracked.trade.order)
        self.tws.run()
        tracked.clientCancelled = True
        tracked.serverStatus = None  # the cancel is now the latest change

    # -- server messages -------------------------------------------------

    @rule(data=st.data())
    def tws_acknowledges(self, data: st.DataObject) -> None:
        candidates = self.live()
        if not candidates:
            return
        tracked = self.pick(data, candidates)
        self.tws.acknowledge(tracked.placed)
        tracked.serverStatus = OrderStatus.Submitted

    @rule(data=st.data(), portion=st.floats(0, 1), reportFirst=st.booleans())
    def tws_fills(self, data: st.DataObject, portion: float, reportFirst: bool) -> None:
        candidates = self.live()
        if not candidates:
            return
        tracked = self.pick(data, candidates)
        remaining = tracked.quantity - sum(tracked.fills, Decimal(0))
        shares = max(Decimal(1), Decimal(int(portion * int(remaining))))
        shares = min(shares, remaining)
        self.tws.fill(tracked.placed, shares, reportFirst=reportFirst)
        tracked.fills.append(shares)
        tracked.reports += 1
        if sum(tracked.fills, Decimal(0)) >= tracked.quantity:
            tracked.ended = "filled"
        else:
            tracked.serverStatus = OrderStatus.Submitted

    @rule(data=st.data())
    def tws_cancels(self, data: st.DataObject) -> None:
        candidates = self.live()
        if not candidates:
            return
        tracked = self.pick(data, candidates)
        self.tws.cancelOrder(tracked.placed)
        tracked.ended = "cancelled"

    @rule(data=st.data())
    def tws_rejects(self, data: st.DataObject) -> None:
        candidates = [t for t in self.live() if not t.placed.acknowledged]
        if not candidates:
            return
        tracked = self.pick(data, candidates)
        self.tws.rejectOrder(tracked.placed)
        tracked.ended = "rejected"

    @rule()
    def disconnect(self) -> None:
        if not self.tws.connected:
            return
        self.tws.disconnect()
        for tracked in self.tracked:
            if not tracked.ended:
                tracked.ended = "disconnected"
        self.epoch += 1

    @rule()
    def reconnect(self) -> None:
        self.tws.reconnect()

    # -- invariants ------------------------------------------------------

    @invariant()
    def trades_in_expected_state(self) -> None:
        for t in self.tracked:
            trade = t.trade
            assert trade.orderStatus.status == t.expectedStatus, (
                t.expectedStatus,
                trade,
            )
            assert trade.isDone() == (t.ended in ("filled", "cancelled", "rejected"))
            assert trade.isUncertain() == (t.ended == "disconnected")
            assert trade.log, trade
            assert trade.log[-1].status == trade.orderStatus.status, trade.log[-1]

    @invariant()
    def fills_match_and_are_delivered_once(self) -> None:
        for t in self.tracked:
            trade = t.trade
            delivered = sum(t.fills, Decimal(0))
            assert trade.filled() == delivered, trade
            assert trade.remaining() == t.quantity - delivered, trade
            assert len(trade.fills) == len(t.fills), trade
            execIds = [f.execution.execId for f in trade.fills]
            assert len(set(execIds)) == len(execIds)
            # Every fill has its commission report, whichever arrived first.
            for f in trade.fills:
                assert f.commissionReport.execId == f.execution.execId, f
                assert f.commissionReport.commissionAndFees == Decimal(1), f
            assert t.counts.fill == len(t.fills), t.counts
            assert t.counts.commission == t.reports, t.counts
            assert t.counts.filled <= 1 and t.counts.cancelled <= 1, t.counts
            assert (t.counts.filled == 1) == (t.ended == "filled"), t.counts

    @invariant()
    def ib_views_match_trades(self) -> None:
        current = [t for t in self.tracked if t.epoch == self.epoch]
        assert set(map(id, self.ib.trades())) == {id(t.trade) for t in current}
        assert set(map(id, self.ib.openTrades())) == {
            id(t.trade) for t in current if not t.trade.isDone()
        }
        execIds = {f.execution.execId for t in current for f in t.trade.fills}
        assert {f.execution.execId for f in self.ib.fills()} == execIds

    def teardown(self) -> None:
        """Fill every working order and check that no trade is left open."""
        for t in self.live():
            if not t.placed.acknowledged:
                self.tws_acknowledges_one(t)
            remaining = t.quantity - sum(t.fills, Decimal(0))
            if remaining > 0:
                self.tws.fill(t.placed, remaining)
                t.fills.append(remaining)
                t.reports += 1
            t.ended = "filled"
        self.trades_in_expected_state()
        self.fills_match_and_are_delivered_once()
        self.ib_views_match_trades()
        assert all(t.trade.isDone() or t.trade.isUncertain() for t in self.tracked)
        assert self.ib.openTrades() == []

    def tws_acknowledges_one(self, tracked: Tracked) -> None:
        self.tws.acknowledge(tracked.placed)
        tracked.serverStatus = OrderStatus.Submitted


TestOrderSimulation = OrderSimulation.TestCase
TestOrderSimulation.settings = examples(100, stateful_step_count=40)


def test_fill_before_open_order_gets_commission_event():
    """A fill can arrive before the order's openOrder.

    The fill finds the trade by its order ids, and its commission report
    must find the trade the same way."""
    tws = SimulatedTws(getLoop())
    trade = tws.ib.placeOrder(CONTRACT, ibi.MarketOrder("BUY", 1))
    counts = track(trade)
    tws.fill(tws.orders[trade.order.orderId], Decimal(1))
    assert (counts.fill, counts.commission, counts.filled) == (1, 1, 1)
    assert trade.fills[0].commissionReport.commissionAndFees == Decimal(1)
