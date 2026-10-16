"""Property tests of historical data against the simulated TWS.

- keepUpToDate bar subscription. After the first bars arrive, an update
  for the last bar's time replaces that bar. An update for a later time
  appends a bar. An update for an earlier time is ignored. An identical
  bar changes nothing. The bars list and the update events match a
  simple model.
- Historical ticks of each kind arrive in chunks. The request returns all
  of them in order once the last chunk is marked done. Cancelling the
  request sends one cancel.
- A head timestamp in any of IBKR's time formats parses to the same
  datetime. A head timestamp that cannot be parsed fails the request with
  ValueError.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async.util import getLoop
from tests._property import examples
from tests._sim import CONTRACT, SimulatedTws

START = 1_700_000_000
MINUTE = 60

prices = st.decimals(Decimal(1), Decimal(500), places=2)


def bar(epoch: int, close: Decimal) -> ibi.BarData:
    return ibi.BarData(
        date=str(epoch),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=Decimal(10),
    )


def when(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def row(b: ibi.BarData) -> tuple:
    return (b.date, b.open, b.high, b.low, b.close, b.volume)


# The bars the simulated server answers with: open 1, high 2, low 1,
# close 2, volume 10, one minute apart from START.
def initialRow(i: int) -> tuple:
    return (
        when(START + MINUTE * i),
        Decimal(1),
        Decimal(2),
        Decimal(1),
        Decimal(2),
        Decimal(10),
    )


@given(
    initial=st.integers(1, 5),
    updates=st.lists(
        st.tuples(st.sampled_from(["same", "later", "earlier"]), prices), max_size=12
    ),
)
@examples()
def test_keep_up_to_date_bars_match_model(initial, updates):
    tws = SimulatedTws(getLoop())
    task = tws.start(
        tws.ib.reqHistoricalDataAsync(
            CONTRACT, "", "1 D", "1 min", "TRADES", True, keepUpToDate=True, timeout=0
        )
    )
    ask = tws.asks[-1]
    tws.answer(ask, rows=initial)
    assert task.done()
    bars = task.result()
    model = [initialRow(i) for i in range(initial)]
    assert [row(b) for b in bars] == model

    events: list[bool] = []
    bars.updateEvent += lambda bars, hasNewBar: events.append(hasNewBar)
    expected: list[bool] = []
    last = START + MINUTE * (initial - 1)
    for kind, close in updates:
        if kind == "same":
            epoch = last
        elif kind == "later":
            epoch = last + MINUTE
        else:
            epoch = last - MINUTE
        update = bar(epoch, close)
        tws.barUpdate(ask, update)
        if kind == "earlier":
            continue  # An update before the last bar is ignored.
        updated = row(update)
        if kind == "later":
            model.append(updated)
            expected.append(True)
            last = epoch
        elif model[-1] != updated:
            model[-1] = updated
            expected.append(False)
        # A repeat of the last bar changes nothing and emits no event.
        assert [row(b) for b in bars] == model
    assert events == expected


TICK_KINDS = {
    "TRADES": lambda t: ibi.HistoricalTickLast(
        when(t), ibi.TickAttribLast(), 1.0, 1.0, "", ""
    ),
    "BID_ASK": lambda t: ibi.HistoricalTickBidAsk(
        when(t), ibi.TickAttribBidAsk(), 1.0, 2.0, 1.0, 1.0
    ),
    "MIDPOINT": lambda t: ibi.HistoricalTick(when(t), 1.5, 0.0),
}


@given(
    kind=st.sampled_from(sorted(TICK_KINDS)),
    chunks=st.lists(st.integers(0, 4), min_size=1, max_size=4),
)
@examples()
def test_historical_ticks_arrive_in_chunks(kind, chunks):
    tws = SimulatedTws(getLoop())
    task = tws.start(
        tws.ib.reqHistoricalTicksAsync(
            CONTRACT, "", "20261016 12:00:00", 100, kind, True
        )
    )
    ask = tws.asks[-1]
    assert ask.kind == "reqHistoricalTicks"
    sent = []
    t = START
    for i, size in enumerate(chunks):
        ticks = []
        for _ in range(size):
            ticks.append(TICK_KINDS[kind](t))
            t += 1
        sent.extend(ticks)
        tws.historicalTicks(ask, ticks, done=i == len(chunks) - 1)
        assert task.done() == (i == len(chunks) - 1)
    assert task.result() == sent


def test_cancel_historical_ticks_sends_one_cancel():
    tws = SimulatedTws(getLoop())
    task = tws.start(
        tws.ib.reqHistoricalTicksAsync(
            CONTRACT, "", "20261016 12:00:00", 10, "TRADES", True
        )
    )
    ask = tws.asks[-1]
    tws.ib.cancelHistoricalTicks(ask.reqId)
    tws.run()
    assert tws.cancels == [("cancelHistoricalTicks", ask.reqId)]
    assert task.cancelled() or task.done()


HEAD_TIMES = {
    "1609459200": datetime(2021, 1, 1, tzinfo=UTC),
    "20210101 00:00:00": datetime(2021, 1, 1, tzinfo=UTC),
    "20210101-00:00:00": datetime(2021, 1, 1, tzinfo=UTC),
    "20210101 00:00:00 UTC": datetime(2021, 1, 1, tzinfo=UTC),
}


@pytest.mark.parametrize("text", sorted(HEAD_TIMES))
def test_head_timestamp_parses_each_time_format(text):
    tws = SimulatedTws(getLoop())
    task = tws.start(tws.ib.reqHeadTimeStampAsync(CONTRACT, "TRADES", True, 1))
    tws.headTimestamp(tws.asks[-1], text)
    assert task.result() == HEAD_TIMES[text]
    assert tws.cancels == [("cancelHeadTimeStamp", tws.asks[-1].reqId)]


@pytest.mark.parametrize("text", ["", "-9223372036854775808", "no data"])
def test_unreadable_head_timestamp_fails_the_request(text):
    tws = SimulatedTws(getLoop())
    task = tws.start(tws.ib.reqHeadTimeStampAsync(CONTRACT, "TRADES", True, 1))
    tws.headTimestamp(tws.asks[-1], text)
    assert isinstance(task.exception(), ValueError)
    # The head timestamp request is a subscription that TWS answers once.
    # The client cancels it after any answer.
    assert tws.cancels == [("cancelHeadTimeStamp", tws.asks[-1].reqId)]


def test_cancelled_head_timestamp_request_sends_one_cancel():
    tws = SimulatedTws(getLoop())
    task = tws.start(tws.ib.reqHeadTimeStampAsync(CONTRACT, "TRADES", True, 1))
    task.cancel()
    tws.run()
    assert tws.cancels == [("cancelHeadTimeStamp", tws.asks[-1].reqId)]
    with pytest.raises(asyncio.CancelledError):
        task.result()
