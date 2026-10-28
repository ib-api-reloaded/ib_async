"""Stateful test of IB request methods against a simulated TWS.

Hypothesis starts these request methods: contract details, executions,
head timestamp, historical bars with and without keepUpToDate, positions
(shared among callers), and positions by model. It mixes them with server
answers in request order, refusals, bust events, cancelled callers, a
dropped socket, and a reconnect.

After each step the test checks that:

- each caller is in the expected state: waiting, answered, cancelled, or
  failed by the disconnect;
- the client sent each cancel to IBKR at most once;
- the request registry holds exactly the requests still awaited, plus any
  bust-event resends that no caller awaits.

At the end the server answers every open request. Every caller must then
be done and the registry must be empty.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from ib_async._requests import ReqIdKey, RequestKey, SingletonKey
from ib_async._subscriptions import HistoricalBarsSub
from ib_async.util import getLoop
from tests._property import machine
from tests._sim import CONTRACT, Ask, SimulatedTws

PENDING, RESULT, CANCELLED, DISCONNECTED = "pending", "result", "cancelled", "gone"

REQ_ID_KINDS = [
    "reqContractDetails",
    "reqExecutions",
    "reqHeadTimeStamp",
    "reqHistoricalData",
    "reqPositionsMulti",
]
# Requests that IB always cancels with IBKR when they end, mapped to the
# cancel method.
CANCELLED_ON_ENDING = {
    "reqHeadTimeStamp": "cancelHeadTimeStamp",
    "reqPositionsMulti": "cancelPositionsMulti",
}


@dataclass(eq=False)
class Started:
    """A request started by the test, and its expected state.

    ``ask`` is the request as the server sees it. A bust event replaces it
    with the resent request."""

    kind: str
    task: asyncio.Task
    ask: Ask
    keepUpToDate: bool = False
    expect: str = PENDING
    epoch: int = 0  # which connection the request was made on
    endedConnected: bool = True  # the socket was up when the request ended
    refused: bool = False  # IBKR refused the request or its bars resend


class RequestSimulation(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = getLoop()
        self.tws = SimulatedTws(self.loop)
        self.started: list[Started] = []
        # Bars resent after a bust event on an answered request. No caller
        # awaits these.
        self.refills: list[Ask] = []
        self.epoch = 0

    # -- client operations -----------------------------------------------

    def _start(
        self, kind: str, request: Callable[[], Any], keepUpToDate: bool = False
    ) -> None:
        """Start a request if connected.

        The client raises immediately when not connected, so requests are
        only started on a live connection."""
        if not self.tws.connected:
            return
        before = len(self.tws.asks)
        task = self.tws.start(request())
        if len(self.tws.asks) > before:
            ask = self.tws.asks[-1]
        else:
            # The call joined an open request of the same kind.
            ask = self.tws.openAsks(kind)[-1]
        self.started.append(Started(kind, task, ask, keepUpToDate, epoch=self.epoch))

    @rule()
    def contract_details(self) -> None:
        self._start(
            "reqContractDetails", lambda: self.ib.reqContractDetailsAsync(CONTRACT)
        )

    @rule()
    def executions(self) -> None:
        self._start("reqExecutions", lambda: self.ib.reqExecutionsAsync())

    @rule()
    def head_timestamp(self) -> None:
        self._start(
            "reqHeadTimeStamp",
            lambda: self.ib.reqHeadTimeStampAsync(CONTRACT, "TRADES", True, 2),
        )

    @rule(keepUpToDate=st.booleans())
    def historical_bars(self, keepUpToDate: bool) -> None:
        self._start(
            "reqHistoricalData",
            lambda: self.ib.reqHistoricalDataAsync(
                CONTRACT,
                "",
                "1 D",
                "1 min",
                "TRADES",
                True,
                keepUpToDate=keepUpToDate,
                timeout=0,
            ),
            keepUpToDate,
        )

    @rule()
    def positions(self) -> None:
        self._start("reqPositions", lambda: self.ib.reqPositionsAsync())

    @rule()
    def positions_by_model(self) -> None:
        self._start(
            "reqPositionsMulti", lambda: self.ib.reqPositionsMultiAsync("DU1", "")
        )

    @rule(data=st.data())
    def cancel_caller(self, data: st.DataObject) -> None:
        """Cancel a waiting caller's task, as a timeout does."""
        pending = [s for s in self.started if s.expect == PENDING]
        if not pending:
            return
        started = pending[data.draw(st.integers(0, len(pending) - 1))]
        started.task.cancel()
        started.expect = CANCELLED
        started.endedConnected = self.tws.connected
        self.tws.run()

    @rule(data=st.data())
    def cancel_with_ibkr(self, data: st.DataObject) -> None:
        """Cancel a waiting head timestamp request with IBKR by its reqId
        (IB.cancelHeadTimeStamp). Its caller gets CancelledError and IBKR
        sends no answer."""
        if not self.tws.connected:
            return
        pending = [
            s
            for s in self.started
            if s.expect == PENDING and s.kind == "reqHeadTimeStamp"
        ]
        if not pending:
            return
        started = pending[data.draw(st.integers(0, len(pending) - 1))]
        assert started.ask.reqId is not None
        self.ib.cancelHeadTimeStamp(started.ask.reqId)
        started.expect = CANCELLED
        started.endedConnected = True
        self.tws.run()

    # -- server messages -------------------------------------------------

    @rule(kind=st.sampled_from([*REQ_ID_KINDS, "reqPositions"]), rows=st.integers(0, 3))
    def server_answers(self, kind: str, rows: int) -> None:
        asks = self.tws.openAsks(kind)
        if not asks:
            return
        ask = asks[0]
        self.tws.answer(ask, rows)
        self._answered(ask)

    @rule(kind=st.sampled_from(REQ_ID_KINDS))
    def server_refuses(self, kind: str) -> None:
        asks = self.tws.openAsks(kind)
        if not asks:
            return
        ask = asks[0]
        self.tws.refuse(ask)
        self._answered(ask, refused=True)

    def _answered(self, ask: Ask, refused: bool = False) -> None:
        for s in self.started:
            if s.ask is not ask:
                continue
            if refused:
                # The request, or its bars resend after a bust event, was
                # refused. IBKR sends nothing more for it.
                s.refused = True
            if s.expect == PENDING:
                s.expect = RESULT
                s.endedConnected = self.tws.connected
        if ask in self.refills:
            self.refills.remove(ask)

    @rule(data=st.data())
    def bust_event(self, data: st.DataObject) -> None:
        """Send a bust event for a historical bars subscription.

        The subscription may be answered or not. The client resends the
        request under a new reqId."""
        subscribed = [
            a
            for a in self.tws.asks
            if a.kind == "reqHistoricalData"
            and not a.cancelled
            and isinstance(
                self.tws.wrapper.subscriptions.get_sub(a.reqId), HistoricalBarsSub
            )
        ]
        if not subscribed:
            return
        ask = subscribed[data.draw(st.integers(0, len(subscribed) - 1))]
        before = len(self.tws.asks)
        self.tws.bust(ask)
        assert len(self.tws.asks) == before + 1, "the bars were not sent again"
        resent = self.tws.asks[-1]
        assert ("cancelHistoricalData", ask.reqId) in self.tws.cancels
        moved = [s for s in self.started if s.ask is ask]
        for s in moved:
            s.ask = resent
        if not any(s.expect == PENDING for s in moved):
            self.refills.append(resent)
        if ask in self.refills:
            self.refills.remove(ask)

    @rule()
    def disconnect(self) -> None:
        if not self.tws.connected:
            return
        self.tws.disconnect()
        for s in self.started:
            if s.expect == PENDING:
                s.expect = DISCONNECTED
                s.endedConnected = False
        self.refills.clear()
        self.epoch += 1

    @rule()
    def reconnect(self) -> None:
        self.tws.reconnect()

    # -- invariants ------------------------------------------------------

    @property
    def ib(self):
        return self.tws.ib

    @invariant()
    def each_end_is_counted_once(self) -> None:
        self.tws.assertEachEndCountedOnce()

    @invariant()
    def callers_in_expected_state(self) -> None:
        for s in self.started:
            task = s.task
            if s.expect == PENDING:
                assert not task.done(), s
            elif s.expect == RESULT:
                assert task.done() and not task.cancelled(), s
                assert task.exception() is None, s
            elif s.expect == CANCELLED:
                assert task.cancelled(), s
            else:
                assert task.done() and not task.cancelled(), s
                assert isinstance(task.exception(), ConnectionError), s

    @invariant()
    def cancel_sent_at_most_once(self) -> None:
        cancels = self.tws.cancels
        assert len(cancels) == len(set(cancels)), cancels
        for s in self.started:
            cancel = CANCELLED_ON_ENDING.get(s.kind)
            if cancel is None or s.expect == PENDING:
                continue
            sent = (cancel, s.ask.reqId) in cancels
            # A request that ended while connected was cancelled exactly
            # once (checked above). One that ended while disconnected was
            # not cancelled.
            assert sent == s.endedConnected, s

    @invariant()
    def registry_holds_awaited_requests(self) -> None:
        expected: set[RequestKey] = set()
        for s in self.started:
            if s.expect == PENDING:
                expected.add(
                    SingletonKey("positions")
                    if s.kind == "reqPositions"
                    else ReqIdKey(s.ask.reqId)
                )
        for refill in self.refills:
            expected.add(ReqIdKey(refill.reqId))
        assert {req.key for req in self.tws.wrapper.requests} == expected

    @invariant()
    def bars_stream_for_live_keep_up_to_date_requests(self) -> None:
        """Only live keepUpToDate requests have a bars subscription.

        The subscription exists while the request is awaited and after it
        is answered. A refused request has none, and a cancelled request's
        subscription is closed."""
        streaming = {
            sub.reqId
            for sub in self.tws.wrapper.subscriptions
            if isinstance(sub, HistoricalBarsSub)
        }
        expected = {
            s.ask.reqId
            for s in self.started
            if s.kind == "reqHistoricalData"
            and s.keepUpToDate
            and s.epoch == self.epoch
            and s.expect in (PENDING, RESULT)
            and not s.refused
        }
        assert streaming == expected

    @invariant()
    def abandoned_request_expects_answer_until_it_arrives(self) -> None:
        for s in self.started:
            if s.kind not in ("reqContractDetails", "reqExecutions"):
                continue
            if s.expect == CANCELLED and s.epoch == self.epoch:
                key = ReqIdKey(s.ask.reqId)
                assert self.tws.wrapper.requests.answering(key) == s.ask.open, s

    def teardown(self) -> None:
        """Answer every open request and check that nothing is left."""
        for ask in list(self.tws.asks):
            if ask.open:
                self.tws.answer(ask)
                self._answered(ask)
        self.tws.run()
        self.callers_in_expected_state()
        assert all(s.task.done() for s in self.started)
        requests = self.tws.wrapper.requests
        assert len(requests) == 0
        for ask in self.tws.asks:
            if ask.reqId is not None:
                assert not requests.answering(ReqIdKey(ask.reqId)), ask
        assert not requests.answering(SingletonKey("positions"))
        assert not requests._owed


TestRequestSimulation = RequestSimulation.TestCase
TestRequestSimulation.settings = machine()
