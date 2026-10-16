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
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import ib_async as ibi
from ib_async.wrapper import Wrapper

EXECUTED = dt.datetime(2026, 10, 14, 15, 30, tzinfo=dt.UTC)
CONTRACT = ibi.Stock("SIM", "SMART", "USD", conId=1)
CLIENT_ID = 7

# Client methods that send a request, mapped to whether their first
# argument is the reqId. Singleton requests have no reqId.
REQUESTS: dict[str, bool] = {
    "reqContractDetails": True,
    "reqExecutions": True,
    "reqHeadTimeStamp": True,
    "reqHistoricalData": True,
    "reqPositionsMulti": True,
    "reqPositions": False,
    # Streams stay open while they stream. A snapshot ends with tickSnapshotEnd.
    "reqMktData": True,
    "reqTickByTickData": True,
    "reqMktDepth": True,
}
# Client cancel methods, mapped to the request each one cancels.
CANCELS: dict[str, str] = {
    "cancelHeadTimeStamp": "reqHeadTimeStamp",
    "cancelHistoricalData": "reqHistoricalData",
    "cancelPositionsMulti": "reqPositionsMulti",
    "cancelContractData": "reqContractDetails",
    "cancelPositions": "reqPositions",
    "cancelMktData": "reqMktData",
    "cancelTickByTickData": "reqTickByTickData",
    "cancelMktDepth": "reqMktDepth",
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

    @property
    def working(self) -> bool:
        return not self.ended


@dataclass(eq=False)
class Ask:
    """A request the client sent, as the server sees it."""

    kind: str  # name of the client method that sent it
    reqId: int | None  # None for a singleton request
    args: tuple
    answered: bool = False  # the server answered or refused it
    cancelled: bool = False  # the client cancelled it, or the socket dropped

    @property
    def open(self) -> bool:
        """True if the request is not yet answered or cancelled."""
        return not (self.answered or self.cancelled)


class SimulatedTws:
    """An IB instance and a simulated server, both in this process."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.ib = ibi.IB()
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
        self.connected = True

    @property
    def wrapper(self) -> Wrapper:
        """The current wrapper. A disconnect resets its registries."""
        return self.ib.wrapper

    # -- client side -----------------------------------------------------

    def _reqId(self) -> int:
        if not self.connected:
            raise ConnectionError("Not connected")  # same as Client.getReqId
        return next(self._reqIds)

    def _asked(self, name: str, hasReqId: bool, *args: Any) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")  # same as Client.send
        self.asks.append(Ask(name, args[0] if hasReqId else None, args))

    def _cancelled(
        self, name: str, kind: str, reqId: int | None = None, *_: Any
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

    def _orderCancelled(self, orderId: int, orderCancel: Any = None) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")
        placed = self.orders.get(orderId)
        if placed is not None:
            placed.cancelRequested = True

    def start(self, coro: Any) -> asyncio.Task:
        """Start a request coroutine and run the loop until it has sent."""
        task = asyncio.ensure_future(coro, loop=self.loop)
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
        """Send an error for a stream. Code 354 means not subscribed."""
        assert ask.reqId is not None
        self.wrapper.error(
            ask.reqId, code, "Requested market data is not subscribed", ""
        )

    # -- server side: orders ---------------------------------------------

    def _orderStatus(self, placed: PlacedOrder, status: str) -> None:
        total = placed.order.totalQuantity or Decimal(0)
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
