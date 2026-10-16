"""Property tests for the tick, volume and time bar operators.

The tests feed random streams of trade ticks, some with a non-finite price
or size, and compare the bars with a reference that splits the stream
into groups directly. Each completed bar must have the same open, high,
low, close, volume, tick count and volume-weighted average price as the
reference, in the same order. ``maxBars`` keeps that many completed bars.
A completed bar never changes, and the operator is done when its source
is done.
"""

from __future__ import annotations

import dataclasses
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from eventkit import Event
from hypothesis import given
from hypothesis import strategies as st

from ib_async.objects import RealTimeBar, TickData
from ib_async.ticker import Ticker
from tests._property import examples

T0 = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)


def at(seconds: int) -> datetime:
    return T0 + timedelta(seconds=seconds)


# A tick is (time in seconds, price, size). Some prices and sizes are not
# finite, like a midpoint with no quote or a tick with no size.
prices = st.one_of(
    st.floats(1, 1000).map(lambda p: round(p, 2)),
    st.just(float("nan")),
    st.just(float("inf")),
)
sizes = st.one_of(st.floats(0, 500).map(lambda s: round(s, 1)), st.just(float("nan")))
ticks = st.lists(st.tuples(prices, sizes), max_size=40).map(
    lambda ps: [(i, p, s) for i, (p, s) in enumerate(ps)]
)


def feed(ticker: Ticker, stream) -> None:
    for seconds, price, size in stream:
        ticker.time = at(seconds)
        ticker.ticks = [TickData(at(seconds), 4, price, size)]
        ticker.updateEvent.emit(ticker)


def priced(stream):
    """Ticks with a finite price, as Decimals; a non-finite size becomes 0."""
    return [
        (s, Decimal(str(p)), Decimal(str(z)) if math.isfinite(z) else Decimal(0))
        for s, p, z in stream
        if math.isfinite(p)
    ]


def barOf(time: datetime, group) -> RealTimeBar:
    """The reference bar for a group of priced ticks."""
    ps = [p for _, p, _ in group]
    volume = sum((z for _, _, z in group), Decimal(0))
    wap = sum((p * z for _, p, z in group), Decimal(0)) / volume if volume else None
    return RealTimeBar(time, ps[0], max(ps), min(ps), ps[-1], volume, wap, len(group))


def collect(operator) -> list[RealTimeBar]:
    emitted: list[RealTimeBar] = []
    operator.connect(emitted.append)
    return emitted


def same(bar: RealTimeBar, expected: RealTimeBar) -> None:
    assert dataclasses.astuple(bar) == dataclasses.astuple(expected), (bar, expected)


@given(
    stream=ticks,
    count=st.integers(1, 7),
    maxBars=st.one_of(st.none(), st.integers(1, 5)),
)
@examples()
def test_tick_bars_group_by_count(stream, count, maxBars):
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(count, maxBars)
    emitted = collect(tickBars)
    feed(ticker, stream)

    valid = priced(stream)
    groups = [valid[i : i + count] for i in range(0, len(valid), count)]
    complete = [g for g in groups if len(g) == count]
    assert len(emitted) == len(complete)
    for bar, group in zip(emitted, complete, strict=True):
        same(bar, barOf(at(group[0][0]), group))
    kept = emitted if maxBars is None else emitted[-maxBars:]
    inProgress = groups[-1:] if groups and len(groups[-1]) < count else []
    assert len(tickBars.bars) == len(kept) + len(inProgress)
    assert all(a is b for a, b in zip(tickBars.bars, kept, strict=False))
    for bar in emitted:
        assert isinstance(bar, RealTimeBar) and bar.count == count


@given(stream=ticks, volume=st.decimals(Decimal("0.5"), 600, places=1))
@examples()
def test_volume_bar_completes_at_volume(stream, volume):
    ticker = Ticker()
    volumeBars = ticker.updateEvent.trades().volumebars(volume)
    emitted = collect(volumeBars)
    feed(ticker, stream)

    groups: list[list] = [[]]
    for tick in priced(stream):
        groups[-1].append(tick)
        if sum((z for _, _, z in groups[-1]), Decimal(0)) >= volume:
            groups.append([])
    complete = groups[:-1]
    assert len(emitted) == len(complete)
    for bar, group in zip(emitted, complete, strict=True):
        same(bar, barOf(at(group[0][0]), group))
        assert bar.volume >= volume
        assert bar.volume - group[-1][2] < volume


@given(
    stream=ticks,
    timerAt=st.lists(st.integers(0, 45), unique=True, max_size=8).map(sorted),
)
@examples()
def test_time_bars_group_by_timer(stream, timerAt):
    """A bar starts at each timer event and holds the ticks until the next.

    Ticks before the first timer event are in no bar. An interval with no
    ticks gives a bar at the last close with zero volume, or no bar if
    there is no previous close."""
    ticker = Ticker()
    timer = Event("timer")
    timeBars = ticker.updateEvent.trades().timebars(timer)
    emitted = collect(timeBars)
    events = sorted(
        [(s, "tick", (s, p, z)) for s, p, z in stream]
        + [(t, "timer", None) for t in timerAt],
        key=lambda e: (e[0], e[1] == "tick"),  # a timer at t fires before the tick at t
    )
    for _, what, tick in events:
        if what == "timer":
            timer.emit(at(_))
        else:
            feed(ticker, [tick])

    # Reference bars: the ticks between consecutive timer events.
    expected: list[RealTimeBar] = []
    lastClose: Decimal | None = None
    for i, start in enumerate(timerAt[:-1]):
        end = timerAt[i + 1]
        group = [t for t in priced(stream) if start <= t[0] < end]
        if group:
            bar = barOf(at(start), group)
        elif lastClose is not None:
            flat = lastClose
            bar = RealTimeBar(at(start), flat, flat, flat, flat, Decimal(0), None, 0)
        else:
            continue
        expected.append(bar)
        lastClose = bar.close
    assert len(emitted) == len(expected)
    for bar, want in zip(emitted, expected, strict=True):
        same(bar, want)

    ticker.updateEvent.set_done()
    assert timeBars.done()


@given(stream=ticks, count=st.integers(1, 4))
@examples()
def test_completed_bar_is_unchanged_and_operator_ends_with_source(stream, count):
    ticker = Ticker()
    tickBars = ticker.updateEvent.trades().tickbars(count)
    emitted = collect(tickBars)
    feed(ticker, stream)
    snapshots = [dataclasses.astuple(bar) for bar in emitted]
    feed(ticker, [(100, 1.0, 1.0)] * count)
    assert [dataclasses.astuple(bar) for bar in emitted[: len(snapshots)]] == snapshots
    ticker.updateEvent.set_done()
    assert tickBars.done()
