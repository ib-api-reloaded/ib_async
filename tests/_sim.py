"""A simulated TWS for driving :class:`ib_async.IB` without a server.

:class:`SimulatedTws` wraps an IB whose client records every request and
cancel it is given instead of sending them, and plays IBKR on the other
side: :meth:`SimulatedTws.answer` delivers a request's rows and end
through the wrapper callbacks the decoder would call, :meth:`refuse` an
error for it, :meth:`bust` a bust event (10225), :meth:`disconnect` a
dropped socket. Each request the client sends is an :class:`Ask`, open
until the server answers it or the client cancels it, so a test can drive
any interleaving of asks, answers, cancels and disconnects and check what
the awaiters see.
"""

from __future__ import annotations

import asyncio
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

# The client methods that send a request the server answers, and whether
# their first argument is the reqId (a singleton request has none).
REQUESTS: dict[str, bool] = {
    "reqContractDetails": True,
    "reqExecutions": True,
    "reqHeadTimeStamp": True,
    "reqHistoricalData": True,
    "reqPositionsMulti": True,
    "reqPositions": False,
}
# Each cancel the client may send, and the request it cancels.
CANCELS: dict[str, str] = {
    "cancelHeadTimeStamp": "reqHeadTimeStamp",
    "cancelHistoricalData": "reqHistoricalData",
    "cancelPositionsMulti": "reqPositionsMulti",
    "cancelContractData": "reqContractDetails",
    "cancelPositions": "reqPositions",
}


@dataclass(eq=False)
class Ask:
    """One request the client sent, as the server sees it."""

    kind: str  # the client method that sent it
    reqId: int | None  # None for a singleton request
    args: tuple
    answered: bool = False  # the server answered (or refused) it
    cancelled: bool = False  # the client cancelled it, or the socket dropped

    @property
    def open(self) -> bool:
        """Still awaiting the server's answer."""
        return not (self.answered or self.cancelled)


class SimulatedTws:
    """An IB and the server it talks to, both in this process."""

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
        self.ib.client = self.client
        self.asks: list[Ask] = []
        # Every cancel the client sent: (the cancel method, the reqId).
        self.cancels: list[tuple[str, int | None]] = []
        self.connected = True

    @property
    def wrapper(self) -> Wrapper:
        """The wrapper now (a disconnect resets its registries)."""
        return self.ib.wrapper

    # -- the client's side -----------------------------------------------

    def _reqId(self) -> int:
        if not self.connected:
            raise ConnectionError("Not connected")  # as Client.getReqId
        return next(self._reqIds)

    def _asked(self, name: str, hasReqId: bool, *args: Any) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")  # as Client.send
        self.asks.append(Ask(name, args[0] if hasReqId else None, args))

    def _cancelled(self, name: str, kind: str, reqId: int | None = None) -> None:
        self.cancels.append((name, reqId))
        for ask in self.asks:
            if ask.kind == kind and ask.reqId == reqId and ask.open:
                ask.cancelled = True

    def start(self, coro: Any) -> asyncio.Task:
        """Start a request method and run the loop until it has sent."""
        task = asyncio.ensure_future(coro, loop=self.loop)
        self.run()
        return task

    def run(self) -> None:
        """Run the event loop long enough for callbacks and awaits to settle."""
        for _ in range(4):
            self.loop.run_until_complete(asyncio.sleep(0))

    def openAsks(self, kind: str | None = None) -> list[Ask]:
        """The asks still awaiting an answer, oldest first."""
        return [a for a in self.asks if a.open and (kind is None or a.kind == kind)]

    # -- the server's side -----------------------------------------------

    def answer(self, ask: Ask, rows: int = 1) -> None:
        """Answer ``ask`` with ``rows`` rows and its end, as IBKR would."""
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

    def refuse(self, ask: Ask, code: int = 162) -> None:
        """Refuse ``ask`` with error ``code``, as IBKR refuses a request."""
        assert ask.reqId is not None, "a singleton request is not refused by reqId"
        self.wrapper.error(ask.reqId, code, "refused by the simulated server", "")
        ask.answered = True
        self.run()

    def bust(self, ask: Ask) -> None:
        """A bust event (10225) on ``ask``: IBKR deactivates the request's
        subscription; the client is expected to send it again."""
        assert ask.reqId is not None
        self.wrapper.error(ask.reqId, 10225, "Bust event occurred", "")
        ask.answered = True
        self.run()

    def disconnect(self) -> None:
        """The socket drops: every awaiter is failed, every subscription
        closed, and the server forgets every open ask."""
        self.client.isConnected.return_value = False
        self.connected = False
        self.wrapper.connectionClosed()
        for ask in self.asks:
            if ask.open:
                ask.cancelled = True
        self.run()

    def reconnect(self) -> None:
        self.client.isConnected.return_value = True
        self.connected = True
