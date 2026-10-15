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
    _Bars: {"bars", "_maxBars", "_builder", "_published", "_lastClose"},
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
    # the bar in progress is flat at the last close until its first tick
    assert list(timeBars.bars) == [*expected, bar(6, ("8",) * 4, "0", None, 0)]
    # False on each tick, and as a new bar starts flat at the last close;
    # True as each bar completes
    assert flags == [False, True, False, False, False, True, False, True, False]

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


def test_max_bars_keeps_the_newest_completed_bars():
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(1, maxBars=2)
    emitted, _ = record(tickBars)

    _feed(ticker, TICKS)

    # five trades, five one-tick bars, all emitted; the last two are kept
    assert len(emitted) == 5
    assert list(tickBars.bars) == emitted[-2:]
    assert tickBars.maxBars == 2


def test_max_bars_does_not_count_the_bar_in_progress():
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

    flat = ("12",) * 4
    assert emitted[-1] == bar(3, flat, "0", None, 0)
    assert list(timeBars.bars) == [emitted[-1], bar(5, flat, "0", None, 0)]


def test_max_bars_keeps_at_least_one_bar():
    with pytest.raises(ValueError, match="at least 1 bar"):
        TickBars(1, maxBars=0)


def test_a_time_bar_before_any_tick_is_no_bar():
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    emitted, flags = record(timeBars)

    timer.emit(_at(0))
    timer.emit(_at(1))  # no tick and no close to repeat
    _feed(ticker, TICKS[2:3])
    timer.emit(_at(3))

    assert emitted == [bar(1, ("12",) * 4, "2", Decimal(12), 1)]
    assert flags == [False, True, False]
    assert [b.time for b in timeBars.bars] == [_at(1), _at(3)]


def test_clearing_bars_leaves_the_operator_working():
    """bars is the user's: emptying it mid-bar loses the bars it held,
    and the bar in progress carries on into it."""
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(2)
    emitted, _ = record(tickBars)

    _feed(ticker, TICKS[:1])
    tickBars.bars.clear()
    _feed(ticker, TICKS[1:3])

    assert emitted == [bar(0, ("10", "12", "10", "12"), "3", Decimal("34.0") / 3, 2)]
    assert list(tickBars.bars) == emitted

    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    timer.emit(_at(0))
    timeBars.bars.clear()
    _feed(ticker, TICKS[3:4])
    timer.emit(_at(4))
    assert [b.time for b in timeBars.bars] == [_at(0), _at(4)]


def test_time_bars_end_with_their_source():
    """After the ticks end (a disconnect), the timer no longer completes
    bars: nothing is emitted, and bars stays as it was."""
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    emitted, flags = record(timeBars)
    timer.emit(_at(0))
    _feed(ticker, TICKS[2:3])
    ticker.updateEvent.set_done()

    assert timeBars.done()
    held = list(timeBars.bars)
    timer.emit(_at(60))
    timer.emit(_at(120))
    assert (emitted, flags, list(timeBars.bars)) == ([], [False], held)


def test_time_bars_end_with_their_timer():
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    _, flags = record(timeBars)
    timer.emit(_at(0))
    timer.set_done()

    assert timeBars.done()
    _feed(ticker, TICKS)
    assert flags == [] and list(timeBars.bars) == []


def test_a_naive_timer_time_is_local_time():
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    timer.emit(datetime(2026, 10, 15, 9, 30))
    _feed(ticker, TICKS[2:3])
    (bar,) = timeBars.bars
    assert bar.time == datetime(2026, 10, 15, 9, 30).astimezone()


def test_ticks_without_a_finite_price_or_size():
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(2)
    _feed(ticker, [(0, 4, float("inf"), 1), (1, 4, 10.0, float("inf"))])
    _feed(ticker, [(2, 4, 11.0, 2)])
    assert list(tickBars.bars) == [
        bar(1, ("10", "11", "10", "11"), "2", Decimal(11), 2)
    ]


@pytest.mark.parametrize("volume", [float("nan"), float("inf"), 0, -1])
def test_a_volume_bar_needs_a_finite_positive_volume(volume):
    with pytest.raises(ValueError, match="positive volume"):
        VolumeBars(volume)


def test_max_bars_is_checked_when_changed():
    tickBars = TickBars(1, maxBars=2)
    tickBars.maxBars = None
    with pytest.raises(ValueError, match="at least 1 bar"):
        tickBars.maxBars = 0


def test_a_bar_cannot_be_changed():
    with pytest.raises(dataclasses.FrozenInstanceError):
        bar(0, None, "0", None, 0).close = Decimal(1)  # type: ignore[misc]


def test_time_bars_on_an_ended_source_end_at_once():
    """After a disconnect ends a ticker's updateEvent, time bars made from
    it are ended, not broken."""
    ticker = Ticker()
    ticker.updateEvent.set_done()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    assert timeBars.done()
    timer.emit(_at(0))
    assert list(timeBars.bars) == []


def test_time_bars_on_an_ended_timer_end_at_once():
    ticker = Ticker()
    timer = Event("timer")
    timer.set_done()
    timeBars = ticker.updateEvent.trades().timebars(timer)
    assert timeBars.done()
    _feed(ticker, TICKS)
    assert list(timeBars.bars) == []
