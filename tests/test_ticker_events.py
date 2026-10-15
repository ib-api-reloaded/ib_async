"""Ticker event classes are slotted eventkit dataclasses.

``TickerUpdateEvent`` and the tick/bar operators built on it are declared
with ``eventkit.event_class``: typed fields instead of hand-written
``__slots__``, identity comparison, and the original constructors.
These tests pin that layout and check the bar operators still aggregate
ticks the same way.
"""

import dataclasses
import inspect
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from eventkit import Event

from ib_async.objects import TickData
from ib_async.ticker import (
    Bar,
    Midpoints,
    TickBars,
    Ticker,
    TickerUpdateEvent,
    Tickfilter,
    TimeBars,
    VolumeBars,
)

T0 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)

FACTORIES: dict[type, Callable[[], Event]] = {
    TickerUpdateEvent: lambda: TickerUpdateEvent("updateEvent"),
    Tickfilter: lambda: Tickfilter((4, 5)),
    Midpoints: lambda: Midpoints(()),
    TimeBars: lambda: TimeBars(Event("timer")),
    TickBars: lambda: TickBars(2),
    VolumeBars: lambda: VolumeBars(3),
}

DECLARED_FIELDS = {
    TickerUpdateEvent: set(),
    Tickfilter: {"_tickTypes"},
    Midpoints: set(),
    TimeBars: {"_timer", "bars"},
    TickBars: {"_count", "bars"},
    VolumeBars: {"_volume", "bars"},
}

SIGNATURES = {
    # Inherited unchanged from eventkit.
    TickerUpdateEvent: str(inspect.signature(Event.__init__)),
    Tickfilter: "(self, tickTypes, source=None)",
    Midpoints: "(self, tickTypes, source=None)",
    TimeBars: "(self, timer, source=None)",
    TickBars: "(self, count, source=None)",
    VolumeBars: "(self, volume, source=None)",
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
    assert str(inspect.signature(cls.__init__)) == SIGNATURES[cls]


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


def test_tickbars_from_synthetic_ticks():
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(2)
    emitted: list = []
    tickBars.connect(emitted.append)

    _feed(ticker, TICKS)

    assert list(tickBars.bars) == [
        Bar(_at(0), 10.0, 12.0, 10.0, 12.0, 3, 2),
        Bar(_at(3), 11.0, 11.0, 8.0, 8.0, 4, 2),
        Bar(_at(5), 9.0, 9.0, 9.0, 9.0, 4, 1),
    ]
    # Emits the bar list once per completed bar.
    assert len(emitted) == 2
    assert all(e is tickBars.bars for e in emitted)


def test_volumebars_from_synthetic_ticks():
    ticker = Ticker()
    volumeBars = ticker.updateEvent.trades().volumebars(3)
    emitted: list = []
    volumeBars.connect(emitted.append)

    _feed(ticker, TICKS)

    assert list(volumeBars.bars) == [
        Bar(_at(0), 10.0, 12.0, 10.0, 12.0, 3, 2),
        Bar(_at(3), 11.0, 11.0, 11.0, 11.0, 3, 1),
        Bar(_at(4), 8.0, 9.0, 8.0, 9.0, 5, 2),
    ]
    assert len(emitted) == 3
    assert all(e is volumeBars.bars for e in emitted)


def test_timebars_from_synthetic_ticks():
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    emitted: list[Bar] = []
    timeBars.connect(emitted.append)

    _feed(ticker, TICKS[:1])  # before the first timer tick: ignored
    timer.emit(_at(0))
    _feed(ticker, TICKS[1:3])
    timer.emit(_at(3))
    _feed(ticker, TICKS[3:5])
    timer.emit(_at(5))
    timer.emit(_at(6))  # empty interval carries the previous close

    expected = [
        Bar(_at(0), 12.0, 12.0, 12.0, 12.0, 2, 1),
        Bar(_at(3), 11.0, 11.0, 8.0, 8.0, 4, 2),
        Bar(_at(5), 8.0, 8.0, 8.0, 8.0, 0, 0),
    ]
    assert emitted == expected
    assert list(timeBars.bars) == [*expected, Bar(_at(6))]

    timer.set_done()
    assert timeBars.done()
    assert timeBars._timer is None


def test_trades_filter_includes_rt_volume_and_rt_trade_volume():
    """Ticks 48 (RT Volume) and 77 (RT Trade Volume, which leaves out
    unreportable trades) are both trades the wrapper records as such."""
    ticker = Ticker()
    received: list[tuple] = []
    ticker.updateEvent.trades().connect(lambda *args: received.append(args))
    _feed(ticker, [(0, 48, 10.0, 100), (1, 77, 10.5, 50)])
    assert received == [(_at(0), 10.0, 100), (_at(1), 10.5, 50)]
