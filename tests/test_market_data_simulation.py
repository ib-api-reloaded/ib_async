"""Stateful test of market data subscriptions against a simulated TWS.

Hypothesis subscribes to streaming market data, snapshots, each
tick-by-tick type and market depth, then cancels and resubscribes. The
contracts share identities as real ones do: a continuous future and its
front month share a conId, two spreads share IBKR's combo conId, and one
stock is unqualified. Meanwhile the simulated TWS sends ticks for live and
cancelled reqIds, ends snapshots, resets depth books, refuses streams and
drops the socket.

After each step the test checks that:

- the subscription registry holds exactly the live streams;
- all streams on the same contract share one pooled Ticker;
- a tick updates its ticker only while its stream is live;
- each stream is cancelled with IBKR at most once, and a snapshot never.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import ib_async as ibi
from ib_async.depth import DepthOperation
from ib_async.ticker import Ticker
from ib_async.util import getLoop
from tests._property import examples
from tests._sim import Ask, SimulatedTws

STOCK_A = ibi.Stock("A", "SMART", "USD", conId=10)
STOCK_B = ibi.Stock("B", "SMART", "USD", conId=11)
FRONT = ibi.Future("ES", "202612", "CME", conId=20)
CONTINUOUS = ibi.Contract(
    secType="CONTFUT", symbol="ES", exchange="CME", currency="USD", conId=20
)
COMBO_CON_ID = 28812380  # IBKR's conId for many different spreads
SPREAD_AB = ibi.Bag(
    symbol="A",
    exchange="SMART",
    currency="USD",
    conId=COMBO_CON_ID,
    comboLegs=[
        ibi.ComboLeg(conId=10, ratio=1, action="BUY", exchange="SMART"),
        ibi.ComboLeg(conId=11, ratio=1, action="SELL", exchange="SMART"),
    ],
)
SPREAD_AES = ibi.Bag(
    symbol="A",
    exchange="SMART",
    currency="USD",
    conId=COMBO_CON_ID,
    comboLegs=[
        ibi.ComboLeg(conId=10, ratio=1, action="BUY", exchange="SMART"),
        ibi.ComboLeg(conId=20, ratio=1, action="SELL", exchange="CME"),
    ],
)
UNQUALIFIED = ibi.Stock("U", "SMART", "USD")
CONTRACTS = [STOCK_A, STOCK_B, FRONT, CONTINUOUS, SPREAD_AB, SPREAD_AES, UNQUALIFIED]

SNAPSHOT = "snapshot"
TICK_BY_TICK = ("Last", "AllLast", "BidAsk", "MidPoint")
KINDS = ["mktData", SNAPSHOT, *TICK_BY_TICK, "mktDepth"]


def identity(contract: ibi.Contract) -> int | None:
    """The registry's index key for a contract: its hash, or None."""
    return hash(contract) if contract.isHashable() else None


@dataclass(eq=False)
class Stream:
    """A subscription made by the test, and its expected state."""

    kind: str  # "mktData", "snapshot", a tick-by-tick type or "mktDepth"
    contract: ibi.Contract
    ask: Ask
    ticker: Ticker
    epoch: int
    live: bool = True

    @property
    def indexKind(self) -> str:
        return "mktData" if self.kind == SNAPSHOT else self.kind


class MarketDataSimulation(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = getLoop()
        self.tws = SimulatedTws(self.loop)
        self.streams: list[Stream] = []
        # The pooled ticker for each contract identity on this connection.
        self.pool: dict[int, Ticker] = {}
        self.epoch = 0

    @property
    def ib(self) -> ibi.IB:
        return self.tws.ib

    def liveStreams(self) -> list[Stream]:
        return [s for s in self.streams if s.live]

    def indexed(self, contract: ibi.Contract, kind: str) -> Stream | None:
        """The live indexed stream for ``contract`` and ``kind``, or None.

        This is the stream the registry should find by contract."""
        key = identity(contract)
        if key is None:
            return None
        for s in self.liveStreams():
            if (
                s.kind != SNAPSHOT
                and s.indexKind == kind
                and identity(s.contract) == key
            ):
                return s
        return None

    def pick(self, data: st.DataObject, candidates: list) -> object:
        return candidates[data.draw(st.integers(0, len(candidates) - 1))]

    # -- client operations -----------------------------------------------

    @rule(kind=st.sampled_from(KINDS), which=st.integers(0, len(CONTRACTS) - 1))
    def subscribe(self, kind: str, which: int) -> None:
        contract = CONTRACTS[which]
        if not self.tws.connected:
            return
        indexKind = "mktData" if kind == SNAPSHOT else kind
        joined = self.indexed(contract, indexKind)
        if kind != SNAPSHOT and identity(contract) is None:
            # A stream needs a qualified contract. Its ticker is pooled by
            # the contract's hash, and an unqualified contract has none.
            with pytest.raises(ValueError, match="can't be hashed"):
                self._subscribe(kind, contract)
            return
        before = len(self.tws.asks)
        ticker = self._subscribe(kind, contract)
        self.tws.run()
        if joined is not None:
            # The open stream is reused: no second request, same ticker.
            assert len(self.tws.asks) == before
            assert ticker is joined.ticker
            return
        assert len(self.tws.asks) == before + 1
        ask = self.tws.asks[-1]
        if kind == SNAPSHOT:
            assert ticker not in self.pool.values()
        else:
            key = identity(contract)
            assert key is not None
            assert ticker is self.pool.setdefault(key, ticker)
        self.streams.append(Stream(kind, contract, ask, ticker, self.epoch))

    def _subscribe(self, kind: str, contract: ibi.Contract) -> Ticker:
        if kind == "mktData":
            return self.ib.reqMktData(contract)
        if kind == SNAPSHOT:
            return self.ib.reqMktData(contract, snapshot=True)
        if kind == "mktDepth":
            return self.ib.reqMktDepth(contract)
        return self.ib.reqTickByTickData(contract, kind)

    @rule(
        kind=st.sampled_from(["mktData", *TICK_BY_TICK, "mktDepth"]),
        which=st.integers(0, len(CONTRACTS) - 1),
    )
    def cancel(self, kind: str, which: int) -> None:
        contract = CONTRACTS[which]
        if not self.tws.connected:
            return
        stream = self.indexed(contract, kind)
        before = len(self.tws.cancels)
        if kind == "mktData":
            found = self.ib.cancelMktData(contract)
        elif kind == "mktDepth":
            self.ib.cancelMktDepth(contract)
            found = stream is not None
        else:
            found = self.ib.cancelTickByTickData(contract, kind)
        self.tws.run()
        assert found == (stream is not None), (kind, contract)
        assert len(self.tws.cancels) == before + (1 if found else 0)
        if stream is not None:
            stream.live = False

    # -- server messages -------------------------------------------------

    @rule(data=st.data(), price=st.floats(1, 100).map(lambda p: round(p, 2)))
    def send_tick(self, data: st.DataObject, price: float) -> None:
        """Send a tick for a stream.

        A tick for a live stream updates its ticker. A tick for a cancelled
        reqId is dropped; TWS sends a few of these after a cancel."""
        if not self.streams:
            return
        stream = self.pick(data, self.streams)
        assert isinstance(stream, Stream)
        ticker = stream.ticker
        before = (ticker.last, ticker.bid, ticker.ask, len(ticker.tickByTicks))
        depthBefore = len(ticker.domTicks)
        if stream.indexKind == "mktData":
            self.tws.lastTick(stream.ask, price)
            expected = (price, before[1], before[2], before[3])
        elif stream.kind in TICK_BY_TICK:
            self.tws.tickByTick(stream.ask, stream.kind, price)
            expected = (
                price if stream.kind in ("Last", "AllLast") else before[0],
                price if stream.kind == "BidAsk" else before[1],
                price + 1 if stream.kind == "BidAsk" else before[2],
                before[3] + 1,
            )
        else:
            self.tws.depth(stream.ask, 0, DepthOperation.INSERT, 1, price)
            expected = before
        after = (ticker.last, ticker.bid, ticker.ask, len(ticker.tickByTicks))
        if stream.live and stream.epoch == self.epoch:
            assert after == expected, stream.kind
            if stream.kind == "mktDepth":
                assert ticker.dom.bids[0].price == price
                assert len(ticker.domTicks) == depthBefore + 1
        else:
            assert after == before and len(ticker.domTicks) == depthBefore

    @rule(data=st.data())
    def end_snapshot(self, data: st.DataObject) -> None:
        candidates = [s for s in self.liveStreams() if s.kind == SNAPSHOT]
        if not candidates:
            return
        stream = self.pick(data, candidates)
        assert isinstance(stream, Stream)
        before = len(self.tws.cancels)
        self.tws.snapshotEnd(stream.ask)
        stream.live = False
        assert len(self.tws.cancels) == before  # a snapshot is never cancelled

    @rule(data=st.data())
    def reset_depth_book(self, data: st.DataObject) -> None:
        candidates = [s for s in self.liveStreams() if s.kind == "mktDepth"]
        if not candidates:
            return
        stream = self.pick(data, candidates)
        assert isinstance(stream, Stream)
        levels = len(stream.ticker.dom.bids) + len(stream.ticker.dom.asks)
        ticksBefore = len(stream.ticker.domTicks)
        self.tws.depthReset(stream.ask)
        assert not stream.ticker.dom
        assert len(stream.ticker.domTicks) == ticksBefore + levels

    @rule(data=st.data())
    def refuse_stream(self, data: st.DataObject) -> None:
        """Send error 354 (not subscribed) for a stream.

        A refused snapshot can never complete, so its subscription ends. A
        refused stream stays open until the client cancels it."""
        candidates = self.liveStreams()
        if not candidates:
            return
        stream = self.pick(data, candidates)
        assert isinstance(stream, Stream)
        before = len(self.tws.cancels)
        self.tws.refuseStream(stream.ask)
        if stream.kind == SNAPSHOT:
            stream.live = False
        assert len(self.tws.cancels) == before

    @rule()
    def disconnect(self) -> None:
        if not self.tws.connected:
            return
        self.tws.disconnect()
        for stream in self.streams:
            stream.live = False
        self.pool.clear()
        self.epoch += 1

    @rule()
    def reconnect(self) -> None:
        self.tws.reconnect()

    # -- invariants ------------------------------------------------------

    @invariant()
    def registry_holds_live_streams(self) -> None:
        registry = self.tws.wrapper.subscriptions
        assert {sub.reqId for sub in registry} == {
            s.ask.reqId for s in self.liveStreams()
        }
        for s in self.liveStreams():
            assert registry.get_ticker(s.ask.reqId) is s.ticker
        for contract in CONTRACTS:
            for kind in ("mktData", *TICK_BY_TICK, "mktDepth"):
                found = registry.find_market_data_for_contract(contract, kind)
                expected = self.indexed(contract, kind)
                assert (found is None) == (expected is None), (contract, kind)
                if found is not None and expected is not None:
                    assert found.reqId == expected.ask.reqId

    @invariant()
    def one_pooled_ticker_per_contract(self) -> None:
        for key, ticker in self.pool.items():
            contracts = [c for c in CONTRACTS if identity(c) == key]
            for contract in contracts:
                assert self.ib.ticker(contract) is ticker
        assert set(map(id, self.ib.tickers())) == set(map(id, self.pool.values()))
        for s in self.streams:
            if s.kind == SNAPSHOT:
                assert s.ticker not in self.ib.tickers()

    @invariant()
    def streams_cancelled_at_most_once_snapshots_never(self) -> None:
        cancels = self.tws.cancels
        assert len(cancels) == len(set(cancels)), cancels
        snapshotReqIds = {s.ask.reqId for s in self.streams if s.kind == SNAPSHOT}
        assert not any(reqId in snapshotReqIds for _, reqId in cancels)

    @invariant()
    def ended_tickers_are_done(self) -> None:
        """Tickers are set done when their data stops.

        A snapshot has its own Ticker. Its updateEvent is done once the
        snapshot ends or the socket drops. A pooled Ticker's updateEvent is
        done once its connection drops."""
        for s in self.streams:
            if s.kind == SNAPSHOT:
                assert s.ticker.updateEvent.done() == (not s.live), s.kind
            elif s.epoch < self.epoch:
                assert s.ticker.updateEvent.done(), s.kind

    def teardown(self) -> None:
        """Cancel every stream, end every snapshot, and check that the
        registry is empty."""
        for s in self.liveStreams():
            if s.kind == SNAPSHOT:
                self.tws.snapshotEnd(s.ask)
            elif s.kind == "mktData":
                assert self.ib.cancelMktData(s.contract)
            elif s.kind == "mktDepth":
                self.ib.cancelMktDepth(s.contract)
            else:
                assert self.ib.cancelTickByTickData(s.contract, s.kind)
            s.live = False
        self.tws.run()
        self.registry_holds_live_streams()
        self.streams_cancelled_at_most_once_snapshots_never()
        assert len(self.tws.wrapper.subscriptions) == 0


TestMarketDataSimulation = MarketDataSimulation.TestCase
TestMarketDataSimulation.settings = examples(100, stateful_step_count=40)
