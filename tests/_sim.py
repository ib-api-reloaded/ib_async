"""A simulated TWS for driving :class:`ib_async.IB` without a server.

:class:`SimulatedTws` holds an IB whose client records requests and
cancels instead of sending them. It also acts as the server: it calls the
same wrapper callbacks the decoder would call.

- :meth:`SimulatedTws.answer` sends a request's rows and its end message.
- :meth:`SimulatedTws.refuse` sends an error for a request.
- :meth:`SimulatedTws.bust` sends a bust event (10225).
- :meth:`SimulatedTws.disconnect` simulates a dropped socket.

Each request the client sends is recorded as an :class:`Ask`. An ask is
open until the server answers it or the client cancels it. Tests use this
to run any order of requests, answers, cancels and disconnects and check
what the awaiting callers receive.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import functools
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TypeVar
from unittest.mock import MagicMock

import ib_async as ibi
from ib_async.wrapper import Wrapper

EXECUTED = dt.datetime(2026, 10, 14, 15, 30, tzinfo=dt.UTC)
CONTRACT = ibi.Stock("SIM", "SMART", "USD", conId=1)
CLIENT_ID = 7

T = TypeVar("T")

# The empty values (IBDefaults) the tests use that are not numbers.
TestEmpty = Enum | str | None

# The argument types the client's request methods receive.
ClientArg = (
    int
    | str
    | bool
    | float
    | Decimal
    | ibi.Contract
    | ibi.Order
    | ibi.ExecutionFilter
    | ibi.ScannerSubscription
    | ibi.WshEventData
    | ibi.OrderCancel
    | Sequence[ibi.TagValue]
    | None
)

# Client methods that send a request, mapped to whether their first
# argument is the reqId. Singleton requests have no reqId.
REQUESTS: dict[str, bool] = {
    "reqContractDetails": True,
    "reqExecutions": True,
    "reqHeadTimeStamp": True,
    "reqHistoricalData": True,
    "reqHistoricalTicks": True,
    "reqPositionsMulti": True,
    "reqPositions": False,
    "reqOpenOrders": False,
    "reqAllOpenOrders": False,
    "reqCompletedOrders": False,
    "reqAccountUpdates": False,
    "reqAccountUpdatesMulti": True,
    "reqAccountSummary": True,
    # Streaming requests stay open until cancelled. A market data snapshot
    # ends with tickSnapshotEnd.
    "reqMktData": True,
    "reqTickByTickData": True,
    "reqMktDepth": True,
    "reqRealTimeBars": True,
    "reqScannerSubscription": True,
    "reqPnL": True,
    "reqPnLSingle": True,
}
# Client cancel methods, mapped to the request each one cancels.
CANCELS: dict[str, str] = {
    "cancelHeadTimeStamp": "reqHeadTimeStamp",
    "cancelHistoricalData": "reqHistoricalData",
    "cancelHistoricalTicks": "reqHistoricalTicks",
    "cancelPositionsMulti": "reqPositionsMulti",
    "cancelContractData": "reqContractDetails",
    "cancelPositions": "reqPositions",
    "cancelAccountUpdatesMulti": "reqAccountUpdatesMulti",
    "cancelAccountSummary": "reqAccountSummary",
    "cancelMktData": "reqMktData",
    "cancelTickByTickData": "reqTickByTickData",
    "cancelMktDepth": "reqMktDepth",
    "cancelRealTimeBars": "reqRealTimeBars",
    "cancelScannerSubscription": "reqScannerSubscription",
    "cancelPnL": "reqPnL",
    "cancelPnLSingle": "reqPnLSingle",
}


@dataclass(eq=False)
class PlacedOrder:
    """An order the client placed, as the server sees it.

    A second placeOrder with the same orderId is a modification and updates
    this record."""

    orderId: int
    contract: ibi.Contract
    order: ibi.Order  # a copy, as sent
    acknowledged: bool = False
    filled: Decimal = Decimal(0)
    # How the order ended at the server: "filled", "cancelled", "rejected"
    # or "disconnected". Empty while the order is working.
    ended: str = ""
    cancelRequested: bool = False
    lastStatus: str = ""  # last status sent for this order

    @property
    def working(self) -> bool:
        return not self.ended


@dataclass(eq=False)
class Ask:
    """A request the client sent, as the server sees it."""

    kind: str  # name of the client method that sent it
    reqId: int | None  # None for a singleton request
    args: tuple[ClientArg, ...]
    answered: bool = False  # the server answered or refused it
    cancelled: bool = False  # the client cancelled it, or the socket dropped

    @property
    def open(self) -> bool:
        """True if the request is not yet answered or cancelled."""
        return not (self.answered or self.cancelled)


class SimulatedTws:
    """An IB instance and a simulated server, both in this process."""

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        defaults: ibi.IBDefaults[TestEmpty] | None = None,
    ) -> None:
        self.loop = loop
        # The IB's empty values (see IBDefaults); IBKR's -1 and 0 by default.
        self.ib = ibi.IB() if defaults is None else ibi.IB(defaults)
        self.client = MagicMock()
        self.client.isConnected.return_value = True
        self._reqIds = iter(range(1000, 10**6))
        self.client.getReqId.side_effect = self._reqId
        for name, hasReqId in REQUESTS.items():
            getattr(self.client, name).side_effect = functools.partial(
                self._asked, name, hasReqId
            )
        for name, kind in CANCELS.items():
            getattr(self.client, name).side_effect = functools.partial(
                self._cancelled, name, kind
            )
        self.client.placeOrder.side_effect = self._placed
        self.client.cancelOrder.side_effect = self._orderCancelled
        self.ib.client = self.client
        self.ib.wrapper.clientId = CLIENT_ID
        self.asks: list[Ask] = []
        # Every cancel the client sent, as (cancel method, reqId).
        self.cancels: list[tuple[str, int | None]] = []
        # Every order placed, by orderId. A modification replaces the copy.
        self.orders: dict[int, PlacedOrder] = {}
        self._execIds = iter(range(1, 10**6))
        # Executions sent, keyed by execId, with the order and commission report.
        self.executions: dict[
            str, tuple[PlacedOrder, ibi.Execution, ibi.CommissionReport]
        ] = {}
        self.connected = True

    @property
    def wrapper(self) -> Wrapper[None] | Wrapper[TestEmpty]:
        """The current wrapper. A disconnect resets its registries."""
        return self.ib.wrapper

    # -- client side -----------------------------------------------------

    def _reqId(self) -> int:
        if not self.connected:
            raise ConnectionError("Not connected")  # same as Client.getReqId
        return next(self._reqIds)

    def _asked(self, name: str, hasReqId: bool, *args: ClientArg) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")  # same as Client.send
        reqId = args[0] if hasReqId else None
        assert reqId is None or isinstance(reqId, int)
        self.asks.append(Ask(name, reqId, args))

    def _cancelled(
        self, name: str, kind: str, reqId: int | None = None, *_: ClientArg
    ) -> None:
        self.cancels.append((name, reqId))
        for ask in self.asks:
            if ask.kind == kind and ask.reqId == reqId and ask.open:
                ask.cancelled = True

    def _placed(self, orderId: int, contract: ibi.Contract, order: ibi.Order) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")
        placed = self.orders.get(orderId)
        # Store the order as TWS does: with the orderId it was sent with,
        # the sending clientId, and a permId assigned by TWS.
        copy = dataclasses.replace(
            order, orderId=orderId, clientId=CLIENT_ID, permId=1_000_000 + orderId
        )
        if placed is None:
            self.orders[orderId] = PlacedOrder(orderId, contract, copy)
        else:
            placed.order = copy  # a modification

    def _orderCancelled(
        self, orderId: int, orderCancel: ibi.OrderCancel | None = None
    ) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")
        placed = self.orders.get(orderId)
        if placed is not None:
            placed.cancelRequested = True

    def start(self, request: Awaitable[T]) -> asyncio.Future[T]:
        """Start a request and run the loop until the request is sent."""
        task = asyncio.ensure_future(request, loop=self.loop)
        self.run()
        return task

    def run(self) -> None:
        """Run the event loop until pending callbacks and awaits finish."""
        for _ in range(4):
            self.loop.run_until_complete(asyncio.sleep(0))

    def openAsks(self, kind: str | None = None) -> list[Ask]:
        """Open asks, oldest first."""
        return [a for a in self.asks if a.open and (kind is None or a.kind == kind)]

    # -- server side -----------------------------------------------------

    def answer(self, ask: Ask, rows: int = 1) -> None:
        """Answer ``ask`` with ``rows`` rows and the end message."""
        w = self.wrapper
        reqId = ask.reqId
        if ask.kind == "reqContractDetails":
            assert reqId is not None
            for _ in range(rows):
                w.contractDetails(reqId, ibi.ContractDetails(contract=CONTRACT))
            w.contractDetailsEnd(reqId)
        elif ask.kind == "reqExecutions":
            assert reqId is not None
            for i in range(rows):
                execution = ibi.Execution(
                    execId=f"{reqId}-{i}",
                    permId=1,
                    shares=Decimal(1),
                    price=Decimal(1),
                    time=EXECUTED,
                )
                w.execDetails(reqId, CONTRACT, execution)
            w.execDetailsEnd(reqId)
        elif ask.kind == "reqHeadTimeStamp":
            assert reqId is not None
            w.headTimestamp(reqId, "1609459200")
        elif ask.kind == "reqHistoricalData":
            assert reqId is not None
            for i in range(rows):
                bar = ibi.BarData(
                    date=str(1700000000 + 60 * i),
                    open=Decimal(1),
                    high=Decimal(2),
                    low=Decimal(1),
                    close=Decimal(2),
                    volume=Decimal(10),
                )
                w.historicalData(reqId, bar)
            w.historicalDataEnd(reqId, "", "")
        elif ask.kind == "reqPositionsMulti":
            assert reqId is not None
            for _ in range(rows):
                w.positionMulti(reqId, "DU1", "", CONTRACT, Decimal(1), Decimal(10))
            w.positionMultiEnd(reqId)
        elif ask.kind == "reqPositions":
            for _ in range(rows):
                w.position("DU1", CONTRACT, Decimal(1), Decimal(10))
            w.positionEnd()
        elif ask.kind in ("reqOpenOrders", "reqAllOpenOrders"):
            w.openOrderEnd()
        elif ask.kind == "reqCompletedOrders":
            w.completedOrdersEnd()
        elif ask.kind == "reqAccountUpdates":
            account = ask.args[1]
            for i in range(rows):
                w.updateAccountValue(f"Tag{i}", str(i), "USD", account)
            w.accountDownloadEnd(account)
        elif ask.kind == "reqAccountUpdatesMulti":
            assert reqId is not None
            account, modelCode = ask.args[1], ask.args[2]
            for i in range(rows):
                w.accountUpdateMulti(
                    reqId, account, modelCode, f"Tag{i}", str(i), "USD"
                )
            w.accountUpdateMultiEnd(reqId)
        elif ask.kind == "reqAccountSummary":
            assert reqId is not None
            for i in range(rows):
                w.accountSummary(reqId, "DU1", f"Tag{i}", str(i), "USD")
            w.accountSummaryEnd(reqId)
        elif ask.kind == "reqHistoricalTicks":
            assert reqId is not None
            ticks = [ibi.HistoricalTick(EXECUTED, 1.0, 1.0) for _ in range(rows)]
            w.historicalTicks(reqId, ticks, True)
        else:
            raise ValueError(f"the simulated server has no answer for {ask.kind}")
        ask.answered = True
        self.run()

    def answerContractDetails(
        self, ask: Ask, details: list[ibi.ContractDetails]
    ) -> None:
        """Answer a contract details request with exactly ``details``."""
        assert ask.kind == "reqContractDetails" and ask.reqId is not None
        for item in details:
            self.wrapper.contractDetails(ask.reqId, item)
        self.wrapper.contractDetailsEnd(ask.reqId)
        ask.answered = True
        self.run()

    def refuse(self, ask: Ask, code: int = 162) -> None:
        """Refuse ``ask`` with error ``code``."""
        assert ask.reqId is not None, "a singleton request is not refused by reqId"
        self.wrapper.error(ask.reqId, code, "refused by the simulated server", "")
        ask.answered = True
        self.run()

    def bust(self, ask: Ask) -> None:
        """Send a bust event (10225) for ``ask``.

        IBKR deactivates the request's subscription, and the client is
        expected to send the request again."""
        assert ask.reqId is not None
        self.wrapper.error(ask.reqId, 10225, "Bust event occurred", "")
        ask.answered = True
        self.run()

    # -- server side: streams --------------------------------------------

    def lastTick(self, ask: Ask, price: float, size: float = 1.0) -> None:
        """Send a last price tick for a market data stream.

        For a cancelled reqId this is a stray tick, which the wrapper drops."""
        assert ask.reqId is not None
        self.wrapper.priceSizeTick(ask.reqId, 4, price, size, ibi.TickAttrib())

    def quote(self, ask: Ask, bid: float, offer: float) -> None:
        assert ask.reqId is not None
        self.wrapper.priceSizeTick(ask.reqId, 1, bid, 1.0, ibi.TickAttrib())
        self.wrapper.priceSizeTick(ask.reqId, 2, offer, 1.0, ibi.TickAttrib())

    def snapshotEnd(self, ask: Ask) -> None:
        """Send the snapshot end message, which ends the subscription."""
        assert ask.reqId is not None
        self.wrapper.tickSnapshotEnd(ask.reqId)
        ask.answered = True

    def tickByTick(self, ask: Ask, tickType: str, price: float) -> None:
        assert ask.reqId is not None
        w, reqId = self.wrapper, ask.reqId
        if tickType in ("Last", "AllLast"):
            w.tickByTickAllLast(
                reqId, 1, 1700000000, price, 1.0, ibi.TickAttribLast(), "", ""
            )
        elif tickType == "BidAsk":
            w.tickByTickBidAsk(
                reqId, 1700000000, price, price + 1, 1.0, 1.0, ibi.TickAttribBidAsk()
            )
        else:
            w.tickByTickMidPoint(reqId, 1700000000, price)

    def depth(
        self, ask: Ask, position: int, operation: int, side: int, price: float
    ) -> None:
        assert ask.reqId is not None
        self.wrapper.updateMktDepthL2(
            ask.reqId, position, "SIM", operation, side, price, 1.0
        )

    def depthReset(self, ask: Ask) -> None:
        """Send error 317, which resets the depth book."""
        assert ask.reqId is not None
        self.wrapper.error(ask.reqId, 317, "Market depth data has been RESET", "")

    def refuseStream(self, ask: Ask, code: int = 354) -> None:
        """Send an error for a stream. Code 354 means not subscribed; the
        server serves nothing more for it."""
        assert ask.reqId is not None
        ask.answered = True
        self.wrapper.error(
            ask.reqId, code, "Requested market data is not subscribed", ""
        )

    def realTimeBar(self, ask: Ask, close: float) -> None:
        """Send one real-time bar closing at ``close``."""
        assert ask.reqId is not None
        price = Decimal(str(close))
        self.wrapper.realtimeBar(
            ask.reqId, 1700000000, price, price, price, price, Decimal(1), price, 1
        )

    def scanRows(self, ask: Ask, rows: int) -> None:
        """Send ``rows`` scanner rows with ranks from 0, then the end message."""
        assert ask.reqId is not None
        for rank in range(rows):
            self.wrapper.scannerData(
                ask.reqId, rank, ibi.ContractDetails(contract=CONTRACT), "", "", "", ""
            )
        self.wrapper.scannerDataEnd(ask.reqId)

    def scanHasNoResults(self, ask: Ask) -> None:
        """Send error 165, which means the scan no longer matches anything."""
        assert ask.reqId is not None
        self.wrapper.error(ask.reqId, 165, "Historical Market Data Service query", "")

    def pnlUpdate(self, ask: Ask, daily: float) -> None:
        """Send a PnL update with daily PnL ``daily``."""
        assert ask.reqId is not None
        self.wrapper.pnl(ask.reqId, daily, 0.0, 0.0)

    def pnlSingleUpdate(self, ask: Ask, position: int, daily: float) -> None:
        """Send a single-position PnL update with ``position`` and ``daily``."""
        assert ask.reqId is not None
        self.wrapper.pnlSingle(ask.reqId, Decimal(position), daily, 0.0, 0.0, 0.0)

    # -- server side: orders ---------------------------------------------

    def _orderStatus(self, placed: PlacedOrder, status: str) -> None:
        total = placed.order.totalQuantity or Decimal(0)
        placed.lastStatus = status
        self.wrapper.orderStatus(
            placed.orderId,
            status,
            placed.filled,
            total - placed.filled,
            Decimal(50) if placed.filled else None,
            placed.order.permId,
            0,
            Decimal(50) if placed.filled else None,
            CLIENT_ID,
            "",
        )

    def acknowledge(self, placed: PlacedOrder) -> None:
        """Accept the order or its modification.

        Sends openOrder with the order as TWS stores it, then a Submitted
        status."""
        self.wrapper.openOrder(
            placed.orderId,
            placed.contract,
            dataclasses.replace(placed.order),
            ibi.OrderState(status="Submitted"),
        )
        self._orderStatus(placed, "Submitted")
        placed.acknowledged = True
        self.run()

    def fill(
        self, placed: PlacedOrder, shares: Decimal, *, reportFirst: bool = False
    ) -> str:
        """Fill ``shares`` of the order and return the execId.

        Sends the execution, the new order status, and the commission
        report. With ``reportFirst`` the commission report is sent before
        the execution, as happens in a replay race."""
        execId = f"{placed.orderId}.{next(self._execIds)}"
        execution = ibi.Execution(
            execId=execId,
            time=EXECUTED,
            shares=shares,
            price=Decimal(50),
            permId=placed.order.permId,
            clientId=CLIENT_ID,
            orderId=placed.orderId,
        )
        report = ibi.CommissionReport(execId=execId, commissionAndFees=Decimal(1))
        self.executions[execId] = (placed, execution, report)
        if reportFirst:
            self.wrapper.commissionReport(report)
        self.wrapper.execDetails(-1, placed.contract, execution)
        placed.filled += shares
        total = placed.order.totalQuantity or Decimal(0)
        if placed.filled >= total:
            placed.ended = "filled"
            self._orderStatus(placed, "Filled")
        else:
            self._orderStatus(placed, "Submitted")
        if not reportFirst:
            self.wrapper.commissionReport(report)
        self.run()
        return execId

    def cancelOrder(self, placed: PlacedOrder) -> None:
        """Cancel the order, either on the client's request or unprompted."""
        placed.ended = "cancelled"
        self._orderStatus(placed, "Cancelled")
        self.run()

    def rejectOrder(self, placed: PlacedOrder, code: int = 201) -> None:
        """Reject the order with error ``code``."""
        placed.ended = "rejected"
        self.wrapper.error(placed.orderId, code, "Order rejected - reason:", "")
        self.run()

    def repeatFill(self, execId: str) -> None:
        """Send an execution and its commission report again."""
        placed, execution, report = self.executions[execId]
        self.wrapper.execDetails(-1, placed.contract, execution)
        self.wrapper.commissionReport(report)
        self.run()

    def repeatStatus(self, placed: PlacedOrder) -> None:
        """Send the last status of the order again."""
        assert placed.lastStatus
        self._orderStatus(placed, placed.lastStatus)
        self.run()

    def globalCancel(self) -> list[PlacedOrder]:
        """Cancel every working order, as TWS does after reqGlobalCancel.
        Return the cancelled orders."""
        cancelled = [p for p in self.orders.values() if p.working]
        for placed in cancelled:
            self.cancelOrder(placed)
        return cancelled

    # -- server side: historical data ----------------------------------------

    def barUpdate(self, ask: Ask, bar: ibi.BarData) -> None:
        """Send a bar update for a keepUpToDate subscription."""
        assert ask.kind == "reqHistoricalData" and ask.reqId is not None
        self.wrapper.historicalDataUpdate(ask.reqId, bar)

    def historicalTicks(
        self, ask: Ask, ticks: list[ibi.HistoricalTick], done: bool
    ) -> None:
        """Send one chunk of midpoint historical ticks. ``done`` marks the
        last chunk."""
        assert ask.kind == "reqHistoricalTicks" and ask.reqId is not None
        self.wrapper.historicalTicks(ask.reqId, ticks, done)
        self._chunkSent(ask, done)

    def historicalTicksBidAsk(
        self, ask: Ask, ticks: list[ibi.HistoricalTickBidAsk], done: bool
    ) -> None:
        """Send one chunk of bid/ask historical ticks."""
        assert ask.kind == "reqHistoricalTicks" and ask.reqId is not None
        self.wrapper.historicalTicksBidAsk(ask.reqId, ticks, done)
        self._chunkSent(ask, done)

    def historicalTicksLast(
        self, ask: Ask, ticks: list[ibi.HistoricalTickLast], done: bool
    ) -> None:
        """Send one chunk of last-trade historical ticks."""
        assert ask.kind == "reqHistoricalTicks" and ask.reqId is not None
        self.wrapper.historicalTicksLast(ask.reqId, ticks, done)
        self._chunkSent(ask, done)

    def _chunkSent(self, ask: Ask, done: bool) -> None:
        if done:
            ask.answered = True
        self.run()

    def headTimestamp(self, ask: Ask, text: str) -> None:
        """Answer a head timestamp request with ``text`` as TWS sends it."""
        assert ask.kind == "reqHeadTimeStamp" and ask.reqId is not None
        self.wrapper.headTimestamp(ask.reqId, text)
        ask.answered = True
        self.run()

    # -- server side: accounts and positions -------------------------------

    def accountValue(self, account: str, tag: str, value: str, currency: str) -> None:
        """Send an account value. Values keep arriving while an account
        updates subscription is open."""
        self.wrapper.updateAccountValue(tag, value, currency, account)

    def accountUpdatesEnd(self, ask: Ask) -> None:
        """End the first download of an account updates subscription."""
        assert ask.kind == "reqAccountUpdates"
        self.wrapper.accountDownloadEnd(ask.args[1])
        ask.answered = True
        self.run()

    def accountValueMulti(self, ask: Ask, tag: str, value: str, currency: str) -> None:
        """Send an account value for a model-level subscription."""
        assert ask.kind == "reqAccountUpdatesMulti" and ask.reqId is not None
        account, modelCode = ask.args[1], ask.args[2]
        self.wrapper.accountUpdateMulti(
            ask.reqId, account, modelCode, tag, value, currency
        )

    def summaryValue(
        self, ask: Ask, account: str, tag: str, value: str, currency: str
    ) -> None:
        assert ask.kind == "reqAccountSummary" and ask.reqId is not None
        self.wrapper.accountSummary(ask.reqId, account, tag, value, currency)

    def summaryEnd(self, ask: Ask) -> None:
        assert ask.kind == "reqAccountSummary" and ask.reqId is not None
        self.wrapper.accountSummaryEnd(ask.reqId)
        ask.answered = True
        self.run()

    def portfolioUpdate(
        self,
        account: str,
        contract: ibi.Contract,
        position: Decimal | None,
        marketPrice: Decimal | None,
        averageCost: Decimal | None,
    ) -> None:
        """Send a portfolio row. A zero or empty position closes it."""
        self.wrapper.updatePortfolio(
            contract, position, marketPrice, None, averageCost, None, None, account
        )

    def positionUpdate(
        self,
        account: str,
        contract: ibi.Contract,
        position: Decimal | None,
        avgCost: Decimal | None,
    ) -> None:
        """Send a position row. A zero or empty position closes it."""
        self.wrapper.position(account, contract, position, avgCost)

    def positionsEnd(self, ask: Ask) -> None:
        assert ask.kind == "reqPositions"
        self.wrapper.positionEnd()
        ask.answered = True
        self.run()

    # -- connection ------------------------------------------------------

    def disconnect(self) -> None:
        """Drop the socket.

        The wrapper fails every awaiting caller, closes every subscription
        and marks every live trade Disconnected. The server drops every
        open ask and working order."""
        self.client.isConnected.return_value = False
        self.connected = False
        self.wrapper.connectionClosed()
        for ask in self.asks:
            if ask.open:
                ask.cancelled = True
        for placed in self.orders.values():
            if placed.working:
                placed.ended = "disconnected"
        self.run()

    def reconnect(self) -> None:
        self.client.isConnected.return_value = True
        self.connected = True
        self.wrapper.clientId = CLIENT_ID  # connect sets this
