"""The master client sees every API client's orders live.

TWS sends a client live order messages only for its own client id, except
the one master client id set in TWS's API settings, which also receives
every other client's openOrder, statuses and executions, each with that
client's id. Executions fire events through the order's Trade, which
openOrder builds. So the master client learns at connect, from TWS's
config, that it is the master and fetches every API client's open orders,
and a fill that arrives before its order's Trade is taken in, with its
events, when the Trade appears.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

import ib_async as ibi
from ib_async import CommissionReport, Fill, StartupFetch, Trade
from ib_async._requests import ReqIdKey
from ib_async.util import getLoop
from tests._sim import CLIENT_ID, CONTRACT, EXECUTED, SimulatedTws

OTHER_CLIENT = 3


class Seen:
    """Every execution and commission event, as (event, execId)."""

    def __init__(self, ib: ibi.IB) -> None:
        self.events: list[tuple[str, str]] = []
        ib.execDetailsEvent += self.execDetails
        ib.commissionReportEvent += self.commission

    def execDetails(self, trade: Trade, fill: Fill) -> None:
        self.events.append(("execDetails", fill.execution.execId))

    def commission(self, trade: Trade, fill: Fill, report: CommissionReport) -> None:
        self.events.append(("commission", report.execId))


def connect(tws: SimulatedTws) -> None:
    """Connect, fetching open orders, and answer every startup request."""
    tws.client.connectAsync = AsyncMock()
    tws.client.getAccounts.return_value = ["DU1"]
    tws.client.serverVersion.return_value = 226
    tws.client.isReady.return_value = True
    task: asyncio.Future[ibi.IB] = tws.start(
        tws.ib.connectAsync(
            clientId=CLIENT_ID, timeout=0, fetchFields=StartupFetch.ORDERS_OPEN
        )
    )
    while asks := tws.openAsks():
        tws.answer(asks[0])
    assert task.done() and task.result() is tws.ib


def otherTrade(tws: SimulatedTws, orderId: int = 42) -> Trade | None:
    return tws.wrapper.trades.get((OTHER_CLIENT, orderId))


def test_other_clients_fill_fires_events_once_with_its_client_id() -> None:
    tws = SimulatedTws(getLoop())
    seen = Seen(tws.ib)
    placed = tws.otherClientOrder(OTHER_CLIENT, 42, ibi.LimitOrder("SELL", 2, 50.0))
    tws.acknowledge(placed)
    trade = otherTrade(tws)
    assert trade is not None and trade.order.clientId == OTHER_CLIENT

    execId = tws.fill(placed, Decimal(2))

    assert seen.events == [("execDetails", execId), ("commission", execId)]
    assert trade.fills[0].execution.clientId == OTHER_CLIENT
    assert trade.orderStatus.clientId == OTHER_CLIENT
    assert trade.orderStatus.status == "Filled"
    tws.repeatFill(execId)
    assert len(seen.events) == 2


def test_same_order_id_from_two_clients_makes_two_trades() -> None:
    tws = SimulatedTws(getLoop())
    own = tws.ib.placeOrder(CONTRACT, ibi.LimitOrder("BUY", 1, 50.0))
    tws.run()
    tws.acknowledge(tws.orders[own.order.orderId])
    other = tws.otherClientOrder(
        OTHER_CLIENT, own.order.orderId, ibi.LimitOrder("SELL", 3, 50.0)
    )
    tws.acknowledge(other)

    tws.fill(other, Decimal(3))

    trades = {t.order.clientId: t for t in tws.ib.trades()}
    assert set(trades) == {CLIENT_ID, OTHER_CLIENT}
    assert trades[CLIENT_ID] is own
    assert own.fills == [] and own.orderStatus.status == "Submitted"
    assert trades[OTHER_CLIENT].filled() == 3


def test_master_client_connect_learns_every_clients_working_order() -> None:
    """An order another client placed before this one connected fires
    events when it fills, though TWS sends no openOrder with the fill."""
    tws = SimulatedTws(getLoop())
    tws.masterClientId = CLIENT_ID
    placed = tws.otherClientOrder(OTHER_CLIENT, 42, ibi.LimitOrder("SELL", 2, 50.0))
    seen = Seen(tws.ib)

    connect(tws)

    assert "reqAllOpenOrders" in [a.kind for a in tws.asks]
    trade = otherTrade(tws)
    assert trade is not None and trade.orderStatus.status == "Submitted"
    execId = tws.fill(placed, Decimal(2))
    assert seen.events == [("execDetails", execId), ("commission", execId)]
    assert [f.execution.execId for f in trade.fills] == [execId]


def test_master_client_relearns_working_orders_after_a_reconnect() -> None:
    """A disconnect forgets every trade, as the daily gateway restart does;
    the reconnect fetches the other clients' working orders again."""
    tws = SimulatedTws(getLoop())
    tws.masterClientId = CLIENT_ID
    placed = tws.otherClientOrder(OTHER_CLIENT, 42, ibi.LimitOrder("SELL", 2, 50.0))
    connect(tws)
    tws.disconnect()
    tws.reconnect()
    seen = Seen(tws.ib)

    connect(tws)

    execId = tws.fill(placed, Decimal(1))
    assert seen.events == [("execDetails", execId), ("commission", execId)]


@pytest.mark.parametrize("masterClientId", [None, OTHER_CLIENT])
def test_other_client_fetches_only_its_own_open_orders(
    masterClientId: int | None,
) -> None:
    """A client that is not the master receives no live messages for
    other clients' orders, so a Trade for one would never update."""
    tws = SimulatedTws(getLoop())
    tws.masterClientId = masterClientId
    tws.otherClientOrder(OTHER_CLIENT, 42, ibi.LimitOrder("SELL", 2, 50.0))

    connect(tws)

    kinds = [a.kind for a in tws.asks]
    assert "reqOpenOrders" in kinds and "reqAllOpenOrders" not in kinds
    assert otherTrade(tws) is None


@pytest.mark.parametrize("reportFirst", [False, True])
def test_fill_before_its_open_order_fires_events_when_the_trade_appears(
    reportFirst: bool,
) -> None:
    tws = SimulatedTws(getLoop())
    seen = Seen(tws.ib)
    placed = tws.otherClientOrder(OTHER_CLIENT, 42, ibi.LimitOrder("SELL", 2, 50.0))

    execId = tws.fill(placed, Decimal(1), reportFirst=reportFirst)
    assert seen.events == []
    tws.acknowledge(placed)

    assert seen.events == [("execDetails", execId), ("commission", execId)]
    trade = otherTrade(tws)
    assert trade is not None
    assert [f.execution.execId for f in trade.fills] == [execId]
    assert trade.fills[0].commissionReport.commissionAndFees == Decimal(1)
    tws.repeatFill(execId)
    tws.acknowledge(placed)
    assert len(seen.events) == 2


def test_report_after_the_open_order_fires_once_for_an_earlier_fill() -> None:
    tws = SimulatedTws(getLoop())
    seen = Seen(tws.ib)
    placed = tws.otherClientOrder(OTHER_CLIENT, 42, ibi.LimitOrder("SELL", 2, 50.0))
    execution = ibi.Execution(
        execId="42.1",
        time=EXECUTED,
        shares=Decimal(1),
        price=Decimal(50),
        permId=placed.order.permId,
        clientId=OTHER_CLIENT,
        orderId=42,
    )
    tws.wrapper.execDetails(-1, CONTRACT, execution)
    tws.acknowledge(placed)
    assert seen.events == [("execDetails", "42.1")]

    tws.wrapper.commissionReport(
        ibi.CommissionReport(execId="42.1", commissionAndFees=Decimal(1))
    )

    assert seen.events == [("execDetails", "42.1"), ("commission", "42.1")]


def test_a_requested_execution_is_not_taken_in_as_live() -> None:
    """An execution answering reqExecutions is history, not a live fill."""
    tws = SimulatedTws(getLoop())
    seen = Seen(tws.ib)
    placed = tws.otherClientOrder(OTHER_CLIENT, 42, ibi.LimitOrder("SELL", 2, 50.0))
    future = tws.wrapper.requests.open(ReqIdKey(5)).future
    execution = ibi.Execution(
        execId="42.9",
        time=EXECUTED,
        shares=Decimal(1),
        price=Decimal(50),
        permId=placed.order.permId,
        clientId=OTHER_CLIENT,
        orderId=42,
    )
    tws.wrapper.execDetails(5, CONTRACT, execution)
    tws.wrapper.execDetailsEnd(5)
    assert future.done()

    tws.acknowledge(placed)

    assert seen.events == []
