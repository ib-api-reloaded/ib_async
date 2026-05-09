"""v3.0 dataclass migrations for bars and tick records.

Two coordinated changes:

1. ``BarData`` and ``RealTimeBar`` numeric fields (``open``, ``high``,
   ``low``, ``close``, ``volume``, ``average`` / ``wap``) become
   ``Decimal | None`` end-to-end. ``None`` is the unset sentinel —
   falsy under ``if bar.open:`` checks, no ``Decimal('NaN')`` truthy
   trap.
2. The tick / depth records (``TickData``, ``HistoricalTick`` family,
   ``TickByTick*`` family, ``MktDepthData``, ``DOMLevel``,
   ``PriceIncrement``) migrate from ``NamedTuple`` to
   ``@dataclass(slots=True, frozen=True)`` for v3.0 framework
   consistency. Numeric field types are kept ``float`` here pending the
   ``Ticker``-side benchmark gate; these records are stored verbatim
   onto ``ticker.ticks`` / ``ticker.tickByTicks`` so they track Ticker
   exactly when that migration lands.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass
from datetime import UTC
from decimal import Decimal

import pytest

from ib_async._proto.safe import safe_decimal
from ib_async.objects import (
    BarData,
    DOMLevel,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    MktDepthData,
    PriceIncrement,
    RealTimeBar,
    TickAttribBidAsk,
    TickAttribLast,
    TickByTickAllLast,
    TickByTickBidAsk,
    TickByTickMidPoint,
    TickData,
)

# ---------------------------------------------------------------------------
# BarData / RealTimeBar — Decimal | None semantics
# ---------------------------------------------------------------------------


def test_bar_data_default_numerics_are_none():
    bar = BarData()
    assert bar.open is None
    assert bar.high is None
    assert bar.low is None
    assert bar.close is None
    assert bar.volume is None
    assert bar.average is None
    assert bar.barCount == 0


def test_real_time_bar_default_numerics_are_none():
    rt = RealTimeBar()
    assert rt.open_ is None
    assert rt.high is None
    assert rt.low is None
    assert rt.close is None
    assert rt.volume is None
    assert rt.wap is None
    assert rt.count == 0


def test_bar_data_unset_open_is_falsy():
    """The ``Decimal('NaN')`` truthy-trap fix: ``if bar.open:`` must be
    False on an unset open, not silently True."""
    bar = BarData()
    assert not bar.open


def test_bar_data_zero_open_is_falsy_too():
    bar = BarData(open=Decimal("0"))
    assert not bar.open


def test_bar_data_nonzero_open_is_truthy():
    bar = BarData(open=Decimal("150.25"))
    assert bar.open
    assert bar.open == Decimal("150.25")


def test_bar_data_safe_decimal_round_trip_from_wire_strings():
    """The historicalData decoder routes wire strings through
    safe_decimal — verify the resulting BarData behaves as expected."""
    bar = BarData(
        open=safe_decimal("150.25"),
        high=safe_decimal("151.0"),
        low=safe_decimal(""),  # wire-empty
        close=safe_decimal("nan"),  # wire-NaN
        volume=safe_decimal("1000"),
        average=safe_decimal("150.5"),
    )
    assert bar.open == Decimal("150.25")
    assert bar.high == Decimal("151.0")
    assert bar.low is None
    assert bar.close is None
    assert bar.volume == Decimal("1000")


# ---------------------------------------------------------------------------
# Tick / depth records — slotted frozen dataclass shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cls",
    [
        TickData,
        HistoricalTick,
        HistoricalTickBidAsk,
        HistoricalTickLast,
        TickByTickAllLast,
        TickByTickBidAsk,
        TickByTickMidPoint,
        MktDepthData,
        DOMLevel,
        PriceIncrement,
    ],
)
def test_tick_record_is_real_dataclass(cls):
    """v3.0: NamedTuples are gone; structural shape is @dataclass."""
    assert is_dataclass(cls)


@pytest.mark.parametrize(
    "cls",
    [
        TickData,
        HistoricalTick,
        HistoricalTickBidAsk,
        HistoricalTickLast,
        TickByTickAllLast,
        TickByTickBidAsk,
        TickByTickMidPoint,
        MktDepthData,
        DOMLevel,
        PriceIncrement,
    ],
)
def test_tick_record_has_slots(cls):
    assert "__slots__" in cls.__dict__


def test_tick_data_is_frozen():
    from datetime import datetime

    td = TickData(
        time=datetime(2026, 5, 9, tzinfo=UTC),
        tickType=1,
        price=150.25,
        size=100.0,
    )
    with pytest.raises(FrozenInstanceError):
        td.price = 200.0  # type: ignore[misc]


def test_dom_level_is_frozen():
    dom = DOMLevel(price=150.25, size=100.0, marketMaker="ARCA")
    with pytest.raises(FrozenInstanceError):
        dom.price = 200.0  # type: ignore[misc]


def test_mkt_depth_data_round_trip():
    from datetime import datetime

    md = MktDepthData(
        time=datetime(2026, 5, 9, tzinfo=UTC),
        position=0,
        marketMaker="ARCA",
        operation=2,
        side=0,
        price=150.25,
        size=100.0,
    )
    assert md.position == 0
    assert md.price == 150.25
    assert md.marketMaker == "ARCA"


# ---------------------------------------------------------------------------
# TickByTick variants carry their attribute payloads cleanly
# ---------------------------------------------------------------------------


def test_tick_by_tick_all_last_carries_tick_attrib_last():
    from datetime import datetime

    attrib = TickAttribLast(pastLimit=True, unreported=False)
    t = TickByTickAllLast(
        tickType=1,
        time=datetime(2026, 5, 9, tzinfo=UTC),
        price=150.25,
        size=100.0,
        tickAttribLast=attrib,
        exchange="ARCA",
        specialConditions="",
    )
    assert t.tickAttribLast.pastLimit is True
    assert t.tickAttribLast.unreported is False


def test_tick_by_tick_bid_ask_carries_tick_attrib_bid_ask():
    from datetime import datetime

    attrib = TickAttribBidAsk(bidPastLow=False, askPastHigh=True)
    t = TickByTickBidAsk(
        time=datetime(2026, 5, 9, tzinfo=UTC),
        bidPrice=150.0,
        askPrice=150.5,
        bidSize=100.0,
        askSize=200.0,
        tickAttribBidAsk=attrib,
    )
    assert t.tickAttribBidAsk.askPastHigh is True


def test_tick_by_tick_mid_point_minimal_record():
    from datetime import datetime

    t = TickByTickMidPoint(time=datetime(2026, 5, 9, tzinfo=UTC), midPoint=150.25)
    assert t.midPoint == 150.25


# ---------------------------------------------------------------------------
# HistoricalTick variants
# ---------------------------------------------------------------------------


def test_historical_tick_minimal_record():
    from datetime import datetime

    t = HistoricalTick(time=datetime(2026, 5, 9, tzinfo=UTC), price=150.25, size=100.0)
    assert t.price == 150.25


def test_historical_tick_bid_ask_carries_attrib():
    from datetime import datetime

    attrib = TickAttribBidAsk(bidPastLow=True, askPastHigh=False)
    t = HistoricalTickBidAsk(
        time=datetime(2026, 5, 9, tzinfo=UTC),
        tickAttribBidAsk=attrib,
        priceBid=150.0,
        priceAsk=150.5,
        sizeBid=100.0,
        sizeAsk=200.0,
    )
    assert t.tickAttribBidAsk.bidPastLow is True


def test_historical_tick_last_carries_attrib():
    from datetime import datetime

    attrib = TickAttribLast(pastLimit=False, unreported=True)
    t = HistoricalTickLast(
        time=datetime(2026, 5, 9, tzinfo=UTC),
        tickAttribLast=attrib,
        price=150.25,
        size=100.0,
        exchange="ARCA",
        specialConditions="",
    )
    assert t.tickAttribLast.unreported is True
    assert t.exchange == "ARCA"


# ---------------------------------------------------------------------------
# PriceIncrement — used by marketRule responses
# ---------------------------------------------------------------------------


def test_price_increment_keyword_construction():
    pi = PriceIncrement(lowEdge=0.0, increment=0.01)
    assert pi.lowEdge == 0.0
    assert pi.increment == 0.01
