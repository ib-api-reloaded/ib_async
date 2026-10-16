"""Stateful test of the Watchdog against a fake IBC and a simulated TWS.

The Watchdog starts the app, waits for it to come up, and connects. It
restarts the app after a hard timeout, error 1100 or a disconnect. In
this test the app is a fake IBC that records start and terminate calls.
The sleep is a function that the test wakes manually. The connection is
the simulated TWS, which answers every startup request. No step waits
on a real clock.

After each step the test checks the following:

- start and terminate calls alternate;
- the started and stopped event counts match the connects and terminates;
- at most one wait is pending;
- the pending wait has the delay expected for the current phase.

At the end the Watchdog is stopped. Its task must then be finished and
the app terminated.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from unittest.mock import AsyncMock

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import ib_async as ibi
from ib_async.ibcontroller import Watchdog
from ib_async.util import getLoop
from tests._property import examples
from tests._sim import SimulatedTws

STARTUP, RETRY = 30.0, 2.0


@dataclass
class FakeIbc:
    """Records the Watchdog's start and terminate calls."""

    calls: list[str] = field(default_factory=list)

    async def startAsync(self) -> None:
        self.calls.append("start")

    async def terminateAsync(self) -> None:
        self.calls.append("terminate")


@dataclass
class ControlledSleep:
    """Sleep replacement that the test wakes manually.

    Each call waits on its own future.
    """

    pending: list[tuple[float, asyncio.Future]] = field(default_factory=list)

    async def __call__(self, delay: float) -> None:
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self.pending.append((delay, future))
        try:
            await future
        finally:
            self.pending = [p for p in self.pending if p[1] is not future]

    def wake(self) -> float:
        """Resolve the oldest pending sleep and return its delay."""
        delay, future = self.pending[0]
        future.set_result(None)
        return delay


class Counts:
    """Counts how many times each Watchdog event fired."""

    def __init__(self, watchdog: Watchdog) -> None:
        self.started = self.stopped = self.soft = self.hard = 0

        def bump(name: str):
            def on(*_: object) -> None:
                setattr(self, name, getattr(self, name) + 1)

            return on

        watchdog.startedEvent += bump("started")
        watchdog.stoppedEvent += bump("stopped")
        watchdog.softTimeoutEvent += bump("soft")
        watchdog.hardTimeoutEvent += bump("hard")


class WatchdogSimulation(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = getLoop()
        self.tws = SimulatedTws(self.loop)
        client = self.tws.client
        client.connectAsync = AsyncMock(side_effect=self._connect)
        client.getAccounts.return_value = ["DU1"]
        client.serverVersion.return_value = 226
        client.isReady.return_value = False
        client.connectionStats.return_value = ibi.ConnectionStats(0, 0, 0, 0, 0, 0)
        client.disconnect.side_effect = self._disconnected
        self.ibc = FakeIbc()
        self.sleep = ControlledSleep()
        self.watchdog = Watchdog(
            self.ibc,  # type: ignore[arg-type]
            self.tws.ib,
            appStartupTime=STARTUP,
            retryDelay=RETRY,
            sleep=self.sleep,
        )
        self.counts = Counts(self.watchdog)
        self.refuseConnections = False
        self.runner: asyncio.Task | None = None
        # "idle", "starting", "connected", "retry" or "stopped"
        self.phase = "idle"
        self.expectedStarted = self.expectedStopped = 0
        self.expectedSoft = self.expectedHard = 0

    # -- the fake connection -------------------------------------------

    def _connect(self, *args: object, **kwargs: object) -> None:
        if self.refuseConnections:
            raise ConnectionRefusedError("refused")
        self.tws.client.isReady.return_value = True

    def _disconnected(self) -> None:
        self.tws.client.isReady.return_value = False
        self.tws.wrapper.connectionClosed()
        self.tws.ib.disconnectedEvent.emit()

    def _answerStartup(self) -> None:
        """Answer every startup request.

        The executions request is sent only after the other requests are
        answered, so this answers in several rounds.
        """
        for _ in range(4):
            for ask in self.tws.openAsks():
                self.tws.answer(ask)
            self.tws.run()

    def _restarted(self) -> None:
        """Record that the app was terminated and the retry wait started."""
        self.expectedStopped += 1
        self.phase = "retry"

    # -- rules: user actions and external events -------------------------

    @rule()
    def start(self) -> None:
        if self.phase != "idle":
            return
        self.runner = self.watchdog.start()
        self.tws.run()
        self.phase = "starting"

    @rule(refuse=st.booleans())
    def set_connections_refused(self, refuse: bool) -> None:
        self.refuseConnections = refuse

    @rule()
    def end_wait(self) -> None:
        """End the pending startup or retry wait."""
        if self.phase not in ("starting", "retry"):
            return
        delay = self.sleep.wake()
        self.tws.run()
        if self.phase == "retry":
            assert delay == RETRY
            self.phase = "starting"
            return
        assert delay == STARTUP
        if self.refuseConnections:
            self._restarted()
        else:
            self._answerStartup()
            self.expectedStarted += 1
            self.phase = "connected"

    @rule(probeAnswered=st.booleans())
    def idle_timeout(self, probeAnswered: bool) -> None:
        """Simulate appTimeout seconds with no traffic.

        The Watchdog sends a historical data request as a probe. If the
        probe is answered, the app keeps running. If it is refused, the
        Watchdog restarts the app.
        """
        if self.phase != "connected":
            return
        self.tws.ib.timeoutEvent.emit(1.0)
        self.tws.run()
        self.expectedSoft += 1
        probes = self.tws.openAsks("reqHistoricalData")
        assert len(probes) == 1
        if probeAnswered:
            self.tws.answer(probes[0], rows=1)
        else:
            self.tws.refuse(probes[0])
            self.expectedHard += 1
            self._restarted()
        self.tws.run()

    @rule(code=st.sampled_from([100, 1100]))
    def connectivity_error(self, code: int) -> None:
        if self.phase != "connected":
            return
        self.tws.ib.errorEvent.emit(-1, code, "connectivity lost", None)
        self.tws.run()
        self._restarted()

    @rule()
    def socket_drops(self) -> None:
        if self.phase != "connected":
            return
        self.tws.disconnect()
        self.tws.ib.disconnectedEvent.emit()
        self.tws.run()
        self.tws.reconnect()
        self._restarted()

    @rule()
    def stop(self) -> None:
        if self.phase in ("idle", "stopped"):
            return
        self.watchdog.stop()
        self.tws.run()
        if self.phase in ("starting", "connected"):
            self.expectedStopped += 1  # stop() terminates the running app
        self.phase = "stopped"

    # -- invariants ------------------------------------------------------

    @invariant()
    def starts_and_terminates_alternate(self) -> None:
        calls = self.ibc.calls
        for first, second in zip(calls, calls[1:], strict=False):
            assert first != second, calls
        if calls:
            assert calls[0] == "start"
        running = calls.count("start") - calls.count("terminate")
        assert running == (1 if self.phase in ("starting", "connected") else 0)

    @invariant()
    def event_counts_match_expected(self) -> None:
        assert self.counts.started == self.expectedStarted
        assert self.counts.stopped == self.expectedStopped
        assert self.counts.soft == self.expectedSoft
        assert self.counts.hard == self.expectedHard

    @invariant()
    def pending_wait_matches_phase(self) -> None:
        assert len(self.sleep.pending) <= 1
        waiting = self.phase in ("starting", "retry")
        assert bool(self.sleep.pending) == waiting, self.phase
        if self.sleep.pending:
            delay = self.sleep.pending[0][0]
            assert delay == (STARTUP if self.phase == "starting" else RETRY)

    @invariant()
    def runner_done_only_when_stopped(self) -> None:
        if self.runner is not None:
            assert self.runner.done() == (self.phase == "stopped")

    def teardown(self) -> None:
        if self.phase not in ("idle", "stopped"):
            self.stop()
        self.tws.run()
        if self.runner is not None:
            assert self.runner.done() and self.runner.result() is None
        self.starts_and_terminates_alternate()
        self.event_counts_match_expected()
        assert not self.sleep.pending


TestWatchdogSimulation = WatchdogSimulation.TestCase
TestWatchdogSimulation.settings = examples(100, stateful_step_count=40)
