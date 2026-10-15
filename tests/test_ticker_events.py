"""Ticker event classes are slotted eventkit dataclasses.

``TickerUpdateEvent`` and the tick/bar operators built on it are declared
with ``eventkit.event_class``: typed fields instead of hand-written
``__slots__``, identity comparison, and the original constructors.
These tests pin that layout and check the bars the operators build from
ticks.
"""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from eventkit import Event

from ib_async.objects import RealTimeBar, TickData
from ib_async.ticker import (
    BarList,
    Midpoints,
    TickBars,
    Ticker,
    TickerUpdateEvent,
    Tickfilter,
    TimeBars,
    VolumeBars,
    _Bars,
)

T0 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)

FACTORIES: dict[type, Callable[[], Event]] = {
    TickerUpdateEvent: lambda: TickerUpdateEvent("updateEvent"),
    Tickfilter: lambda: Tickfilter((4, 5)),
    Midpoints: lambda: Midpoints(()),
    _Bars: lambda: _Bars(),
    TimeBars: lambda: TimeBars(Event("timer")),
    TickBars: lambda: TickBars(2),
    VolumeBars: lambda: VolumeBars(3),
}

DECLARED_FIELDS = {
    TickerUpdateEvent: set(),
    Tickfilter: {"_tickTypes"},
    Midpoints: set(),
    _Bars: {"bars", "_builder", "_lastClose"},
    TimeBars: {"_timer"},
    TickBars: {"_count"},
    VolumeBars: {"_volume"},
}

REQUIRED = inspect.Parameter.empty


def parameters(function: Callable[..., object]) -> list[tuple[str, object]]:
    """A function's parameters as (name, default) pairs: what a caller
    depends on, whatever the annotations."""
    return [
        (p.name, p.default) for p in inspect.signature(function).parameters.values()
    ]


SIGNATURES = {
    # Inherited unchanged from eventkit.
    TickerUpdateEvent: parameters(Event.__init__),
    Tickfilter: [("self", REQUIRED), ("tickTypes", REQUIRED), ("source", None)],
    Midpoints: [("self", REQUIRED), ("tickTypes", REQUIRED), ("source", None)],
    _Bars: [("self", REQUIRED), ("source", None), ("maxBars", None)],
    TimeBars: [
        ("self", REQUIRED),
        ("timer", REQUIRED),
        ("source", None),
        ("maxBars", None),
    ],
    TickBars: [
        ("self", REQUIRED),
        ("count", REQUIRED),
        ("source", None),
        ("maxBars", None),
    ],
    VolumeBars: [
        ("self", REQUIRED),
        ("volume", REQUIRED),
        ("source", None),
        ("maxBars", None),
    ],
}

CLASSES = list(FACTORIES)


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_is_slotted_dataclass(cls):
    assert dataclasses.is_dataclass(cls)
    assert "__slots__" in cls.__dict__
    assert "__dict__" not in cls.__dict__


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_declares_its_own_fields(cls):
    assert set(cls.__dict__["__slots__"]) == DECLARED_FIELDS[cls]
    names = {f.name for f in dataclasses.fields(cls)}
    assert DECLARED_FIELDS[cls] <= names


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_instances_have_no_dict(cls):
    event = FACTORIES[cls]()
    assert not hasattr(event, "__dict__")
    with pytest.raises(AttributeError):
        event.undeclaredAttribute = 1


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_constructor_signature_unchanged(cls):
    assert parameters(cls.__init__) == SIGNATURES[cls]


@pytest.mark.parametrize("cls", CLASSES, ids=lambda c: c.__name__)
def test_compares_by_identity(cls):
    a = FACTORIES[cls]()
    b = FACTORIES[cls]()
    assert a != b
    assert len({a, b, a}) == 2


@pytest.mark.parametrize(
    ("cls", "doc_source"),
    [
        (TimeBars, Tickfilter.timebars),
        (TickBars, Tickfilter.tickbars),
        (VolumeBars, Tickfilter.volumebars),
    ],
    ids=lambda v: getattr(v, "__name__", ""),
)
def test_bar_operators_keep_docstrings(cls, doc_source):
    assert cls.__doc__ == doc_source.__doc__


# Synthetic tick stream: (seconds after T0, tickType, price, size).
# tickType 4 is a last-trade tick; 1 is a bid tick that ``trades()`` drops.
TICKS = [
    (0, 4, 10.0, 1),
    (1, 1, 9.0, 5),
    (2, 4, 12.0, 2),
    (3, 4, 11.0, 3),
    (4, 4, 8.0, 1),
    (5, 4, 9.0, 4),
]


def _at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


def _feed(ticker: Ticker, ticks) -> None:
    """Deliver each tick as its own ticker update."""
    for seconds, tickType, price, size in ticks:
        ticker.time = _at(seconds)
        ticker.ticks = [TickData(_at(seconds), tickType, price, size)]
        ticker.updateEvent.emit(ticker)


def test_trades_filter_emits_only_trade_ticks():
    ticker = Ticker()
    received: list[tuple] = []
    ticker.updateEvent.trades().connect(lambda *args: received.append(args))

    _feed(ticker, TICKS)

    assert received == [
        (_at(seconds), price, size)
        for seconds, tickType, price, size in TICKS
        if tickType == 4
    ]


def test_midpoints_emit_ticker_midpoint():
    ticker = Ticker()
    ticker.bid = 100.0
    ticker.ask = 101.0
    ticker.bidSize = 1
    ticker.askSize = 1
    received: list[tuple] = []
    ticker.updateEvent.midpoints().connect(lambda *args: received.append(args))

    _feed(ticker, TICKS[:1])
    ticker.ticks = []
    ticker.updateEvent.emit(ticker)  # no ticks, no emit

    assert received == [(_at(0), 100.5, 0)]


def bar(
    seconds: int,
    ohlc: tuple[str, str, str, str] | None,
    volume: str,
    wap: Decimal | None,
    count: int,
) -> RealTimeBar:
    """The bar expected at ``seconds``; prices as the Decimals they read as."""
    open_, high, low, close = (
        (Decimal(p) for p in ohlc) if ohlc else (None, None, None, None)
    )
    return RealTimeBar(
        _at(seconds), open_, high, low, close, Decimal(volume), wap, count
    )


def record(bars: _Bars) -> tuple[list[RealTimeBar], list[bool]]:
    """What a bar operator emits, and its updateEvent's hasNewBar flags."""
    emitted: list[RealTimeBar] = []
    flags: list[bool] = []
    bars.connect(emitted.append)
    bars.bars.updateEvent += lambda _, hasNewBar: flags.append(hasNewBar)
    return emitted, flags


def test_tickbars_from_synthetic_ticks():
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(2)
    emitted, flags = record(tickBars)

    _feed(ticker, TICKS)

    # WAP is sum(price * size) / volume: (10 * 1 + 12 * 2) / 3, ...
    first = bar(0, ("10", "12", "10", "12"), "3", Decimal("34.0") / 3, 2)
    second = bar(3, ("11", "11", "8", "8"), "4", Decimal("10.25"), 2)
    inProgress = bar(5, ("9", "9", "9", "9"), "4", Decimal(9), 1)
    assert list(tickBars.bars) == [first, second, inProgress]
    assert emitted == [first, second]
    # in progress (False) on each tick, True as the last bar completes
    assert flags == [False, True, False, True, False]


def test_volumebars_from_synthetic_ticks():
    ticker = Ticker()
    volumeBars = ticker.updateEvent.trades().volumebars(3)
    emitted, flags = record(volumeBars)

    _feed(ticker, TICKS)

    expected = [
        bar(0, ("10", "12", "10", "12"), "3", Decimal("34.0") / 3, 2),
        bar(3, ("11", "11", "11", "11"), "3", Decimal(11), 1),
        # the last tick takes the bar past 3: a tick is not split
        bar(4, ("8", "9", "8", "9"), "5", Decimal("8.8"), 2),
    ]
    assert list(volumeBars.bars) == expected
    assert emitted == expected
    assert flags == [False, True, True, False, True]


def test_timebars_from_synthetic_ticks():
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    emitted, flags = record(timeBars)

    _feed(ticker, TICKS[:1])  # before the first timer event: in no bar
    timer.emit(_at(0))
    _feed(ticker, TICKS[1:3])
    timer.emit(_at(3))
    _feed(ticker, TICKS[3:5])
    timer.emit(_at(5))
    timer.emit(_at(6))  # an empty interval repeats the previous close

    expected = [
        bar(0, ("12", "12", "12", "12"), "2", Decimal(12), 1),
        bar(3, ("11", "11", "8", "8"), "4", Decimal("10.25"), 2),
        bar(5, ("8", "8", "8", "8"), "0", None, 0),
    ]
    assert emitted == expected
    assert list(timeBars.bars) == [*expected, bar(6, None, "0", None, 0)]
    assert flags == [False, True, False, False, True, True]

    timer.set_done()
    assert timeBars.done()
    assert timeBars._timer is None


def test_a_completed_bar_never_changes():
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(2)
    emitted, _ = record(tickBars)
    _feed(ticker, TICKS[:3])
    (completed,) = emitted
    snapshot = dataclasses.replace(completed)

    _feed(ticker, TICKS[3:])

    assert completed == snapshot
    assert tickBars.bars[0] is completed


def test_midpoint_bars_have_no_volume_and_no_wap():
    ticker = Ticker()
    ticker.bid, ticker.ask = 100.0, 101.0
    ticker.bidSize, ticker.askSize = 1, 1
    tickBars = ticker.updateEvent.midpoints().tickbars(2)

    _feed(ticker, TICKS[:2])

    assert list(tickBars.bars) == [
        bar(0, ("100.5", "100.5", "100.5", "100.5"), "0", None, 2)
    ]


def test_ticks_without_a_price_are_skipped():
    """A midpoint without a bid and ask has no price: it is in no bar."""
    ticker = Ticker()
    tickBars = ticker.updateEvent.midpoints().tickbars(1)

    _feed(ticker, TICKS[:2])

    assert list(tickBars.bars) == []


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: TickBars(0), "at least 1 tick"),
        (lambda: VolumeBars(0), "positive volume"),
    ],
)
def test_bar_sizes_are_refused_when_empty(
    make: Callable[[], _Bars], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        make()


def test_trades_filter_includes_rt_volume_and_rt_trade_volume():
    """Ticks 48 (RT Volume) and 77 (RT Trade Volume, which leaves out
    unreportable trades) are both trades the wrapper records as such."""
    ticker = Ticker()
    received: list[tuple] = []
    ticker.updateEvent.trades().connect(lambda *args: received.append(args))
    _feed(ticker, [(0, 48, 10.0, 100), (1, 77, 10.5, 50)])
    assert received == [(_at(0), 10.0, 100), (_at(1), 10.5, 50)]


def test_a_tick_without_a_size_adds_no_volume():
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(2)

    _feed(ticker, [(0, 4, 10.0, float("nan")), (1, 4, 11.0, 2)])

    assert list(tickBars.bars) == [
        bar(0, ("10", "11", "10", "11"), "2", Decimal(11), 2)
    ]


def test_max_bars_keeps_the_newest_like_a_deque():
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(1, maxBars=2)
    emitted, _ = record(tickBars)

    _feed(ticker, TICKS)

    # five trades, five one-tick bars, all emitted; the last two are kept
    assert len(emitted) == 5
    assert list(tickBars.bars) == emitted[-2:]
    assert tickBars.bars.maxlen == 2


def test_an_empty_time_bar_repeats_the_close_with_one_bar_kept():
    """The close an empty bar repeats is kept by the operator, not read
    from a bar the cap has dropped."""
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer, maxBars=1)
    emitted, _ = record(timeBars)

    timer.emit(_at(0))
    _feed(ticker, TICKS[2:3])  # close 12
    timer.emit(_at(3))
    timer.emit(_at(5))  # empty

    assert emitted[-1] == bar(3, ("12", "12", "12", "12"), "0", None, 0)
    assert len(timeBars.bars) == 1


def test_bar_list_caps_appends_and_refuses_an_empty_cap():
    bars = BarList([bar(0, None, "0", None, 0), bar(1, None, "0", None, 0)], maxlen=1)
    assert [b.time for b in bars] == [_at(1)]
    bars.append(bar(2, None, "0", None, 0))
    assert [b.time for b in bars] == [_at(2)]
    assert len(BarList()) == 0 and BarList().maxlen is None
    with pytest.raises(ValueError, match="at least 1 bar"):
        BarList(maxlen=0)
