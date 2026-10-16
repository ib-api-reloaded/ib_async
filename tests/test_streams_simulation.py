"""Stateful test of bar, PnL and scanner subscriptions against a simulated TWS.

Hypothesis subscribes to real-time bars, PnL by account and model, PnL for
single positions, and market scans, and cancels and resubscribes them. The
simulated TWS sends bars, PnL updates and scan results on live and
cancelled reqIds, sends bust events for bars, reports a scan with no
results, and drops the socket.

After each step the test checks the following:

- The subscription registry holds exactly the live subscriptions.
- ``ib.pnl()``, ``ib.pnlSingle()`` and ``ib.realtimeBars()`` list exactly
  the live subscriptions.
- An update reaches its object only while its subscription is live.
- Each subscription is cancelled with IBKR at most once, under its current
  reqId.
- A bust event moves the bars to a new reqId and cancels the old one.
- The update event of a cancelled or disconnected subscription is done.

At the end the test cancels every subscription and checks that the
registry is empty.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import ib_async as ibi
from ib_async.util import getLoop
from tests._property import machine
from tests._sim import Ask, SimulatedTws

# The types of object a stream subscription returns. The client keeps the
# object updated.
StreamObject = ibi.RealTimeBarList | ibi.PnL | ibi.PnLSingle | ibi.ScanDataList

STOCK_A = ibi.Stock("A", "SMART", "USD", conId=10)
STOCK_B = ibi.Stock("B", "SMART", "USD", conId=11)
CONTRACTS = [STOCK_A, STOCK_B]
ACCOUNTS = ["DU1", "DU2"]
MODELS = ["", "M1"]
CON_IDS = [10, 11]
SCAN = ibi.ScannerSubscription(
    instrument="STK", locationCode="STK.US", scanCode="TOP_PERC_GAIN"
)


@dataclass(eq=False)
class Stream:
    """A subscription the test made, with its expected state."""

    kind: str  # "bars", "pnl", "pnlSingle" or "scan"
    key: tuple[
        str | int, ...
    ]  # key IB uses to reuse a live subscription; empty if none
    obj: StreamObject
    ask: Ask
    epoch: int
    live: bool = True
    updates: int = 0  # updateEvent emissions seen (bars and scans)


class StreamSimulation(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = getLoop()
        self.tws = SimulatedTws(self.loop)
        self.streams: list[Stream] = []
        self.epoch = 0

    @property
    def ib(self) -> ibi.IB:
        return self.tws.ib

    def live(self, kind: str | None = None) -> list[Stream]:
        return [s for s in self.streams if s.live and (kind is None or s.kind == kind)]

    def pick(self, data: st.DataObject, candidates: list[Stream]) -> Stream:
        return candidates[data.draw(st.integers(0, len(candidates) - 1))]

    def _track(
        self, kind: str, key: tuple[str | int, ...], obj: StreamObject, ask: Ask
    ) -> Stream:
        stream = Stream(kind, key, obj, ask, self.epoch)
        # Bars and scans have an update event. PnL objects have none. They
        # are updated in place.
        if isinstance(obj, ibi.RealTimeBarList | ibi.ScanDataList):

            def count(*_: ibi.RealTimeBarList | ibi.ScanDataList | bool) -> None:
                stream.updates += 1

            obj.updateEvent += count
        self.streams.append(stream)
        return stream

    # -- client operations -----------------------------------------------

    @rule(which=st.integers(0, len(CONTRACTS) - 1))
    def subscribe_bars(self, which: int) -> None:
        if not self.tws.connected:
            return
        before = len(self.tws.asks)
        bars = self.ib.reqRealTimeBars(CONTRACTS[which], 5, "TRADES", True)
        self.tws.run()
        assert len(self.tws.asks) == before + 1
        assert bars.reqId == self.tws.asks[-1].reqId
        self._track("bars", (), bars, self.tws.asks[-1])

    @rule(data=st.data())
    def cancel_bars(self, data: st.DataObject) -> None:
        candidates = self.live("bars")
        if not candidates or not self.tws.connected:
            return
        stream = self.pick(data, candidates)
        before = len(self.tws.cancels)
        self.ib.cancelRealTimeBars(stream.obj)  # type: ignore[arg-type]
        self.tws.run()
        assert self.tws.cancels[before:] == [("cancelRealTimeBars", stream.ask.reqId)]
        stream.live = False

    @rule(
        account=st.sampled_from(ACCOUNTS),
        model=st.sampled_from(MODELS),
        conId=st.sampled_from([None, *CON_IDS]),
    )
    def subscribe_pnl(self, account: str, model: str, conId: int | None) -> None:
        """If a live subscription has the same key, reqPnL and reqPnLSingle
        return its object and send no new request."""
        if not self.tws.connected:
            return
        kind = "pnl" if conId is None else "pnlSingle"
        key = (account, model) if conId is None else (account, model, conId)
        existing = [s for s in self.live(kind) if s.key == key]
        before = len(self.tws.asks)
        if conId is None:
            obj = self.ib.reqPnL(account, model)
        else:
            obj = self.ib.reqPnLSingle(account, model, conId)
        self.tws.run()
        if existing:
            assert obj is existing[0].obj
            assert len(self.tws.asks) == before
            return
        assert len(self.tws.asks) == before + 1
        self._track(kind, key, obj, self.tws.asks[-1])

    @rule(
        account=st.sampled_from(ACCOUNTS),
        model=st.sampled_from(MODELS),
        conId=st.sampled_from([None, *CON_IDS]),
    )
    def cancel_pnl(self, account: str, model: str, conId: int | None) -> None:
        if not self.tws.connected:
            return
        kind = "pnl" if conId is None else "pnlSingle"
        key = (account, model) if conId is None else (account, model, conId)
        existing = [s for s in self.live(kind) if s.key == key]
        before = len(self.tws.cancels)
        if conId is None:
            self.ib.cancelPnL(account, model)
        else:
            self.ib.cancelPnLSingle(account, model, conId)
        self.tws.run()
        if not existing:
            # No live subscription: IB logs an error and sends no cancel.
            assert len(self.tws.cancels) == before
            return
        cancel = "cancelPnL" if conId is None else "cancelPnLSingle"
        assert self.tws.cancels[before:] == [(cancel, existing[0].ask.reqId)]
        existing[0].live = False

    @rule()
    def subscribe_scan(self) -> None:
        if not self.tws.connected:
            return
        before = len(self.tws.asks)
        dataList = self.ib.reqScannerSubscription(SCAN)
        self.tws.run()
        assert len(self.tws.asks) == before + 1
        self._track("scan", (), dataList, self.tws.asks[-1])

    @rule(data=st.data())
    def cancel_scan(self, data: st.DataObject) -> None:
        candidates = self.live("scan")
        if not candidates or not self.tws.connected:
            return
        stream = self.pick(data, candidates)
        before = len(self.tws.cancels)
        self.ib.cancelScannerSubscription(stream.obj)  # type: ignore[arg-type]
        self.tws.run()
        assert self.tws.cancels[before:] == [
            ("cancelScannerSubscription", stream.ask.reqId)
        ]
        stream.live = False

    # -- server messages -------------------------------------------------

    @rule(data=st.data(), value=st.integers(1, 100))
    def send_update(self, data: st.DataObject, value: int) -> None:
        """Send an update for a subscription. The object receives it only if
        the subscription is live. An update for a cancelled reqId is
        dropped."""
        if not self.streams:
            return
        stream = self.pick(data, self.streams)
        alive = stream.live and stream.epoch == self.epoch
        if stream.kind == "bars":
            bars = stream.obj
            assert isinstance(bars, ibi.RealTimeBarList)
            count, updates = len(bars), stream.updates
            self.tws.realTimeBar(stream.ask, float(value))
            assert len(bars) == count + (1 if alive else 0)
            assert stream.updates == updates + (1 if alive else 0)
        elif stream.kind == "pnl":
            pnl = stream.obj
            assert isinstance(pnl, ibi.PnL)
            previous = pnl.dailyPnL
            self.tws.pnlUpdate(stream.ask, float(value))
            assert pnl.dailyPnL == (float(value) if alive else previous)
        elif stream.kind == "pnlSingle":
            single = stream.obj
            assert isinstance(single, ibi.PnLSingle)
            previous = (single.position, single.dailyPnL)
            self.tws.pnlSingleUpdate(stream.ask, value, float(value))
            expected = (ibi.util.Decimal(value), float(value)) if alive else previous
            assert (single.position, single.dailyPnL) == expected
        else:
            scan = stream.obj
            assert isinstance(scan, ibi.ScanDataList)
            rows, updates = list(scan), stream.updates
            count = value % 4
            self.tws.scanRows(stream.ask, count)
            if alive:
                # A row with rank 0 starts a new result set. An end
                # message with no rows keeps the previous results.
                expected = list(range(count)) if count else [r.rank for r in rows]
                assert [row.rank for row in scan] == expected
                assert stream.updates == updates + 1
            else:
                assert list(scan) == rows and stream.updates == updates

    @rule(data=st.data())
    def bust_bars(self, data: st.DataObject) -> None:
        """Send a bust event for live bars. The client cancels the old reqId
        and sends the request again under a new one, and the bars list
        takes the new reqId."""
        candidates = self.live("bars")
        if not candidates:
            return
        stream = self.pick(data, candidates)
        bars = stream.obj
        assert isinstance(bars, ibi.RealTimeBarList)
        before = len(self.tws.asks)
        old = stream.ask.reqId
        self.tws.bust(stream.ask)
        assert len(self.tws.asks) == before + 1
        resent = self.tws.asks[-1]
        assert resent.kind == "reqRealTimeBars" and resent.reqId != old
        assert ("cancelRealTimeBars", old) in self.tws.cancels
        assert bars.reqId == resent.reqId
        stream.ask = resent

    @rule(data=st.data())
    def scan_has_no_results(self, data: st.DataObject) -> None:
        candidates = self.live("scan")
        if not candidates:
            return
        stream = self.pick(data, candidates)
        self.tws.scanHasNoResults(stream.ask)
        assert list(stream.obj) == []  # type: ignore[call-overload]

    @rule()
    def disconnect(self) -> None:
        if not self.tws.connected:
            return
        self.tws.disconnect()
        for stream in self.streams:
            stream.live = False
        self.epoch += 1

    @rule()
    def reconnect(self) -> None:
        self.tws.reconnect()

    # -- invariants ------------------------------------------------------

    @invariant()
    def registry_holds_live_subscriptions(self) -> None:
        registry = self.tws.wrapper.subscriptions
        assert {sub.reqId for sub in registry} == {s.ask.reqId for s in self.live()}

    @invariant()
    def ib_lists_live_subscriptions(self) -> None:
        assert set(map(id, self.ib.pnl())) == {id(s.obj) for s in self.live("pnl")}
        assert set(map(id, self.ib.pnlSingle())) == {
            id(s.obj) for s in self.live("pnlSingle")
        }
        assert set(map(id, self.ib.realtimeBars())) == {
            id(s.obj) for s in self.live("bars")
        }
        # An empty account or model code means "any" in these filters.
        for account in ACCOUNTS:
            for model in MODELS:
                expected = {
                    id(s.obj)
                    for s in self.live("pnl")
                    if s.key[0] == account and (not model or s.key[1] == model)
                }
                assert set(map(id, self.ib.pnl(account, model))) == expected
                for conId in CON_IDS:
                    expected = {
                        id(s.obj)
                        for s in self.live("pnlSingle")
                        if s.key[0] == account
                        and (not model or s.key[1] == model)
                        and s.key[2] == conId
                    }
                    found = self.ib.pnlSingle(account, model, conId)
                    assert set(map(id, found)) == expected

    @invariant()
    def cancels_are_unique(self) -> None:
        assert len(self.tws.cancels) == len(set(self.tws.cancels))

    @invariant()
    def ended_bars_and_scans_are_done(self) -> None:
        for s in self.streams:
            event = getattr(s.obj, "updateEvent", None)
            if event is not None:
                assert event.done() == (not s.live), s.kind

    def teardown(self) -> None:
        for s in self.live():
            if s.kind == "bars":
                self.ib.cancelRealTimeBars(s.obj)  # type: ignore[arg-type]
            elif s.kind == "pnl":
                self.ib.cancelPnL(*s.key)
            elif s.kind == "pnlSingle":
                self.ib.cancelPnLSingle(*s.key)
            else:
                self.ib.cancelScannerSubscription(s.obj)  # type: ignore[arg-type]
            s.live = False
        self.tws.run()
        self.registry_holds_live_subscriptions()
        self.cancels_are_unique()
        self.ended_bars_and_scans_are_done()
        assert len(self.tws.wrapper.subscriptions) == 0


TestStreamSimulation = StreamSimulation.TestCase
TestStreamSimulation.settings = machine()
