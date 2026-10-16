"""Stateful test that compares the wrapper's tick processing with a model.

The simulated TWS sends market data ticks for one live subscription and
one cancelled subscription. The ticks cover prices with sizes, sizes
alone, RT volume strings, exchange and timestamp strings, dividends,
generic values, option computations and EFP data. They arrive in any
order, and packet boundaries can fall anywhere. The model is a dict of
the Ticker's fields. It is updated by the rules IBKR documents for each
tick type.

After each step the test checks that the live Ticker's fields equal the
model, that the tick log holds exactly the ticks of the current packet,
that the derived values (hasBidAsk, midpoint, marketPrice) follow from
the quote, and that the cancelled Ticker never changes. At each packet
end it checks that updateEvent fires once for the live Ticker if and only
if a tick reached it, and that pendingTickersEvent carries exactly that
Ticker.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import ib_async as ibi
from ib_async.ticker import HaltedStatus, Ticker
from ib_async.util import getLoop
from ib_async.wrapper import (
    _GENERIC_TICK_NO_CLAMP,
    _HALTED_TICKS,
    EFP_TICK_MAP,
    GENERIC_TICK_MAP,
    GREEKS_TICK_MAP,
    PRICE_TICK_MAP,
    RT_VOLUME_TICK_MAP,
    SIZE_TICK_MAP,
    STRING_TICK_MAP,
    TIMESTAMP_TICK_MAP,
    Wrapper,
)
from tests._property import machine
from tests._sim import SimulatedTws

EMPTY_PRICE, EMPTY_SIZE = -1, 0
BID, ASK, LAST = (1, 66), (2, 67), (4, 68)
BID_SIZE, ASK_SIZE, LAST_SIZE = (0, 69), (3, 70), (5, 71)

prices = st.floats(0.5, 500).map(lambda p: round(p, 2))
sizes = st.one_of(st.just(0.0), st.floats(1, 10000).map(lambda s: float(int(s))))
# IBKR sends -1 for a missing price, so the strategy generates it often.
pricesOrEmpty = st.one_of(st.just(-1.0), prices)

QUOTE_FIELDS = (
    "bid", "bidSize", "ask", "askSize", "last", "lastSize",
    "prevBid", "prevBidSize", "prevAsk", "prevAskSize", "prevLast", "prevLastSize",
    "vwap", "rtTime", "dividends",
)  # fmt: skip
MODELLED_FIELDS = sorted(
    set(QUOTE_FIELDS)
    | set(PRICE_TICK_MAP.values())
    | set(SIZE_TICK_MAP.values())
    | set(GENERIC_TICK_MAP.values())
    | set(STRING_TICK_MAP.values())
    | set(TIMESTAMP_TICK_MAP.values())
    | set(RT_VOLUME_TICK_MAP.values())
    | set(GREEKS_TICK_MAP.values())
    | set(EFP_TICK_MAP.values())
)


# A value of one of the modelled Ticker fields.
TickerValue = (
    float
    | str
    | datetime
    | HaltedStatus
    | ibi.Dividends
    | ibi.OptionComputation
    | ibi.EfpData
    | None
)
TickerModel = dict[str, TickerValue]


def snapshot(ticker: Ticker) -> TickerModel:
    return {name: getattr(ticker, name) for name in MODELLED_FIELDS}


def num(m: TickerModel, name: str) -> float | None:
    """Return the numeric field ``name`` of the model."""
    value = m[name]
    assert value is None or isinstance(value, float | int)
    return value


def hasBidAsk(m: TickerModel) -> bool:
    bid, bidSize, ask, askSize = (
        num(m, n) for n in ("bid", "bidSize", "ask", "askSize")
    )
    return bool(
        bid is not None
        and bid != -1
        and bidSize
        and bidSize > 0
        and ask is not None
        and ask != -1
        and askSize
        and askSize > 0
    )


def midpoint(m: TickerModel) -> float | None:
    if not hasBidAsk(m):
        return None
    bid, ask = num(m, "bid"), num(m, "ask")
    assert bid is not None and ask is not None
    return (bid + ask) * 0.5


def marketPrice(m: TickerModel) -> float | None:
    last = num(m, "last")
    if hasBidAsk(m):
        bid, ask = num(m, "bid"), num(m, "ask")
        assert bid is not None and ask is not None
        if last is not None and bid <= last <= ask:
            return last
        return (bid + ask) * 0.5
    return last


class TickProcessing(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.tws = SimulatedTws(getLoop())
        ib = self.tws.ib
        self.ticker = ib.reqMktData(ibi.Stock("A", "SMART", "USD", conId=10))
        self.reqId = self.tws.asks[-1].reqId
        self.cancelled = ib.reqMktData(ibi.Stock("B", "SMART", "USD", conId=11))
        self.cancelledReqId = self.tws.asks[-1].reqId
        ib.cancelMktData(self.cancelled.contract)
        self.tws.run()
        self.cancelledBefore = snapshot(self.cancelled)

        self.model = snapshot(self.ticker)
        # The ticks of the current packet, as (tickType, price or value, size).
        self.ticks: list[tuple[int, float | HaltedStatus | None, float]] = []
        self.touched = False  # True once a tick updates the live ticker
        self.updates = 0
        self.pending: list[set[Ticker]] = []
        self.ticker.updateEvent += self._onUpdate
        ib.pendingTickersEvent += lambda tickers: self.pending.append(set(tickers))
        self.tws.wrapper.tcpDataArrived()

    @property
    def wrapper(self) -> Wrapper:
        return self.tws.wrapper

    def _onUpdate(self, ticker: Ticker) -> None:
        self.updates += 1

    def _tick(self, tickType: int, price: float | None, size: float) -> None:
        if price or size:
            self.ticks.append((tickType, price, size))

    # -- price and size ticks ----------------------------------------------

    @rule(
        tickType=st.sampled_from([*BID, *ASK, *LAST, *PRICE_TICK_MAP]),
        price=pricesOrEmpty,
        size=sizes,
    )
    def price_tick(self, tickType: int, price: float, size: float) -> None:
        self.wrapper.priceSizeTick(self.reqId, tickType, price, size, ibi.TickAttrib())
        m = self.model
        if tickType in BID or tickType in ASK:
            side = "bid" if tickType in BID else "ask"
            if size == 0:
                price, size = EMPTY_PRICE, EMPTY_SIZE
            m["prev" + side.capitalize()] = m[side]
            m["prev" + side.capitalize() + "Size"] = m[side + "Size"]
            m[side], m[side + "Size"] = price, size
        elif tickType in LAST:
            close = num(m, "close")
            if price == -1 and size == 0 and close is not None and close > 0:
                price, size = EMPTY_PRICE, EMPTY_SIZE
            m["prevLast"], m["prevLastSize"] = m["last"], m["lastSize"]
            m["last"], m["lastSize"] = price, size
        else:
            m[PRICE_TICK_MAP[tickType]] = price
        self._tick(tickType, price, size)
        self.touched = True

    @rule(
        tickType=st.sampled_from([*BID_SIZE, *ASK_SIZE, *LAST_SIZE, *SIZE_TICK_MAP]),
        size=sizes,
    )
    def size_tick(self, tickType: int, size: float) -> None:
        self.wrapper.tickSize(self.reqId, tickType, size)
        m = self.model
        price: float | None = EMPTY_PRICE
        if tickType in BID_SIZE or tickType in ASK_SIZE:
            side = "bid" if tickType in BID_SIZE else "ask"
            if size == m[side + "Size"]:
                return  # an unchanged size is not logged
            m["prev" + side.capitalize() + "Size"] = m[side + "Size"]
            if size == 0:
                m[side], m[side + "Size"] = EMPTY_PRICE, EMPTY_SIZE
            else:
                price = num(m, side)
                m[side + "Size"] = size
        elif tickType in LAST_SIZE:
            price = num(m, "last")
            if price is None:
                return  # a size without a last price is dropped
            if size != m["lastSize"]:
                m["prevLastSize"], m["lastSize"] = m["lastSize"], size
        else:
            m[SIZE_TICK_MAP[tickType]] = size
        self._tick(tickType, price, size)
        self.touched = True

    # -- string ticks --------------------------------------------------------

    @rule(
        tickType=st.sampled_from(sorted(RT_VOLUME_TICK_MAP)),
        price=st.one_of(st.none(), prices),
        size=sizes,
        ms=st.integers(1_600_000_000_000, 1_900_000_000_000),
        volume=st.one_of(st.none(), st.integers(0, 10**8)),
        vwap=st.one_of(st.none(), prices),
    )
    def rt_volume(self, tickType, price, size, ms, volume, vwap) -> None:
        """Send an RT volume string in the form price;size;time;volume;vwap;single.
        An empty price updates only volume, VWAP and time."""
        parts = [
            "" if price is None else str(price),
            str(size),
            str(ms),
            "" if volume is None else str(volume),
            "" if vwap is None else str(vwap),
            "true",
        ]
        self.wrapper.tickString(self.reqId, tickType, ";".join(parts))
        m = self.model
        if volume is not None:
            m[RT_VOLUME_TICK_MAP[tickType]] = float(volume)
        if vwap is not None:
            m["vwap"] = vwap
        m["rtTime"] = datetime.fromtimestamp(ms / 1000, UTC)
        if price is not None:
            m["prevLast"], m["prevLastSize"] = m["last"], m["lastSize"]
            m["last"], m["lastSize"] = price, size
            self._tick(tickType, price, size)
        self.touched = True

    @rule(tickType=st.sampled_from(sorted(STRING_TICK_MAP)), value=st.text(max_size=6))
    def string_tick(self, tickType: int, value: str) -> None:
        self.wrapper.tickString(self.reqId, tickType, value)
        self.model[STRING_TICK_MAP[tickType]] = value
        self.touched = True

    @rule(
        tickType=st.sampled_from(sorted(TIMESTAMP_TICK_MAP)),
        seconds=st.one_of(st.just(0), st.integers(1_600_000_000, 1_900_000_000)),
    )
    def timestamp_tick(self, tickType: int, seconds: int) -> None:
        """Send a last-trade timestamp. Zero means no trade yet and is ignored."""
        self.wrapper.tickString(self.reqId, tickType, str(seconds))
        if seconds:
            self.model[TIMESTAMP_TICK_MAP[tickType]] = datetime.fromtimestamp(
                seconds, UTC
            )
        self.touched = True

    @rule(
        past=st.one_of(st.none(), prices),
        upcoming=st.one_of(st.none(), prices),
        day=st.one_of(st.none(), st.dates(date(2020, 1, 1), date(2035, 12, 31))),
        amount=st.one_of(st.none(), prices),
    )
    def dividends_tick(self, past, upcoming, day, amount) -> None:
        text = ",".join(
            "" if v is None else v
            for v in (
                None if past is None else str(past),
                None if upcoming is None else str(upcoming),
                None if day is None else day.strftime("%Y%m%d"),
                None if amount is None else str(amount),
            )
        )
        self.wrapper.tickString(self.reqId, 59, text)
        self.model["dividends"] = ibi.Dividends(past, upcoming, day, amount)
        self.touched = True

    @rule(
        tickType=st.sampled_from([45, 48, 59, 77, 88]),
        value=st.sampled_from(["", "abc", "1;2", "1,2", "x;y;z;1;2;3"]),
    )
    def malformed_string_tick(self, tickType: int, value: str) -> None:
        """An unparseable string is logged and does not change the ticker."""
        self.wrapper.tickString(self.reqId, tickType, value)

    @rule(value=st.text(max_size=4))
    def unknown_string_tick(self, value: str) -> None:
        """An unknown string tick type is logged. The ticker is still marked
        as updated, so its event fires at the end of the packet."""
        self.wrapper.tickString(self.reqId, 999, value)
        self.touched = True

    # -- generic, greeks and EFP ----------------------------------------------

    @rule(
        tickType=st.sampled_from(sorted(GENERIC_TICK_MAP)),
        value=st.one_of(
            st.sampled_from([-1.0, 0.0, 1.0, 2.0, 7.0]),
            st.floats(-100, 100).map(lambda v: round(v, 3)),
        ),
    )
    def generic_tick(self, tickType: int, value: float) -> None:
        self.wrapper.tickGeneric(self.reqId, tickType, value)
        shown: float | HaltedStatus = value
        if tickType not in _GENERIC_TICK_NO_CLAMP:
            shown = value if value > 0 else EMPTY_SIZE
        if (
            tickType in _HALTED_TICKS
            and int(value) in HaltedStatus.__members__.values()
        ):
            shown = HaltedStatus(int(value))
        self.model[GENERIC_TICK_MAP[tickType]] = shown
        self.ticks.append((tickType, shown, 0))  # logged even when zero
        self.touched = True

    @rule(
        tickType=st.sampled_from(sorted(GREEKS_TICK_MAP)),
        values=st.lists(
            st.one_of(
                st.sampled_from([-1.0, -2.0]),
                st.floats(0, 5).map(lambda v: round(v, 4)),
            ),
            min_size=8,
            max_size=8,
        ),
    )
    def option_computation(self, tickType: int, values: list[float]) -> None:
        """Send greeks. IBKR sends -1 for an unknown price or volatility and
        -2 for an unknown greek. The Ticker stores both as None."""
        self.wrapper.tickOptionComputation(self.reqId, tickType, 1, *values)
        unset = (-1, -2, -1, -1, -2, -2, -2, -1)
        shown = [None if v == u else v for v, u in zip(values, unset, strict=True)]
        self.model[GREEKS_TICK_MAP[tickType]] = ibi.OptionComputation(1, *shown)
        self.touched = True

    @rule(tickType=st.sampled_from(sorted(EFP_TICK_MAP)), basis=prices, implied=prices)
    def efp_tick(self, tickType: int, basis: float, implied: float) -> None:
        self.wrapper.tickEFP(
            self.reqId, tickType, basis, f"{basis}%", implied, 30, "20261218", 0.1, 0.2
        )
        self.model[EFP_TICK_MAP[tickType]] = ibi.EfpData(
            basis, f"{basis}%", implied, 30, "20261218", 0.1, 0.2
        )
        self.touched = True

    # -- ticks for the cancelled subscription ----------------------------------

    @rule(price=prices, size=sizes, value=st.floats(0, 10))
    def ticks_after_cancel(self, price: float, size: float, value: float) -> None:
        """TWS can send a few ticks after a cancel. They do not change anything."""
        w, reqId = self.wrapper, self.cancelledReqId
        w.priceSizeTick(reqId, 4, price, size, ibi.TickAttrib())
        w.tickSize(reqId, 8, size)
        w.tickString(reqId, 48, f"{price};{size};1700000000000;10;{price};true")
        w.tickGeneric(reqId, 23, value)
        w.tickOptionComputation(
            reqId, 13, 1, value, 0.5, price, 0, 0.1, 0.1, 0.1, price
        )
        w.tickEFP(reqId, 38, value, "", price, 1, "", 0, 0)

    # -- packet boundaries --------------------------------------------------------

    @rule()
    def end_packet(self) -> None:
        """End one TCP packet. Each updated ticker fires its events once.
        The next packet starts with empty tick logs."""
        updatesBefore, pendingBefore = self.updates, len(self.pending)
        self.wrapper.tcpDataProcessed()
        assert self.updates == updatesBefore + (1 if self.touched else 0)
        if self.touched:
            assert self.pending[-1] == {self.ticker}
            assert len(self.pending) == pendingBefore + 1
            assert self.ticker.time == self.wrapper.lastTime
        else:
            assert len(self.pending) == pendingBefore
        self.wrapper.tcpDataArrived()
        self.ticks = []
        self.touched = False

    # -- invariants -------------------------------------------------------------------

    @invariant()
    def ticker_matches_model(self) -> None:
        assert snapshot(self.ticker) == self.model

    @invariant()
    def tick_log_matches_packet(self) -> None:
        logged = [(t.tickType, t.price, t.size) for t in self.ticker.ticks]
        assert logged == self.ticks

    @invariant()
    def derived_values_match_quote(self) -> None:
        t, m = self.ticker, self.model
        assert t.hasBidAsk() == hasBidAsk(m)
        assert t.midpoint() == midpoint(m)
        assert t.marketPrice() == marketPrice(m)

    @invariant()
    def cancelled_ticker_unchanged(self) -> None:
        assert snapshot(self.cancelled) == self.cancelledBefore
        assert self.cancelled.ticks == []


TestTickProcessing = TickProcessing.TestCase
TestTickProcessing.settings = machine()
