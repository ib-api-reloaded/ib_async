"""``formatDate=3`` historical bars.

TWS answers ``reqHistoricalData(formatDate=3)`` with ``MMdd HH:MM:SS <tz>``
bar timestamps -- the year never reaches the wire. The response bounds IB
reports for the dataset stay full-width, so they anchor the run; the bars
themselves are dated only once the whole series has arrived, because the
bounds do not share a frame with the bars on any server at or above
``MIN_SERVER_VER_HISTORICAL_DATA_END`` nor in the protobuf transport.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey
from ib_async._subscriptions import HistoricalBarsSub
from ib_async.decoder import Decoder
from ib_async.util import isIBShortDatetime, parseIBDatetime, parseIBShortDatetimes

EASTERN = ZoneInfo("US/Eastern")

# A decoder that predates ``MIN_SERVER_VER_HISTORICAL_DATA_END`` carries no
# msgId 108 handler at all, so the split-frame half of the transport
# coverage has nothing to drive. The wrapper-level cases below pin the
# same deferred dating without a decoder.
requiresSplitEndFrame = pytest.mark.skipif(
    not hasattr(Decoder, "historicalDataEnd"),
    reason="decoder predates the split end-of-dataset frame",
)


def _openBarRequest(ib: ibi.IB, reqId: int = 1):
    req, _ = ib.wrapper.requests.open(ReqIdKey(reqId))
    return req.future


# -- util layer ---------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "0714 09:30:00 US/Eastern",
        "1231 23:30:00 Europe/Amsterdam",
    ],
)
def test_short_datetimes_are_recognised(value):
    assert isIBShortDatetime(value)


@pytest.mark.parametrize(
    "value",
    [
        "20250714",
        "1752501600",
        "20250714 09:30:00 US/Eastern",
        "20250714  09:30:00",
        "2025-07-14 09:30:00.0",
    ],
)
def test_full_datetimes_are_not_mistaken_for_short_ones(value):
    assert not isIBShortDatetime(value)


def test_existing_datetime_formats_are_unchanged():
    assert parseIBDatetime("20250714") == datetime(2025, 7, 14).date()
    assert parseIBDatetime("1752501600") == datetime.fromtimestamp(
        1752501600, ZoneInfo("UTC")
    )
    assert parseIBDatetime("20250714 09:30:00 US/Eastern") == datetime(
        2025, 7, 14, 9, 30, tzinfo=EASTERN
    )
    assert parseIBDatetime("20250714  09:30:00") == datetime(2025, 7, 14, 9, 30)


def test_short_datetime_without_a_year_is_rejected():
    with pytest.raises(ValueError, match="carries no year"):
        parseIBDatetime("0714 09:30:00 US/Eastern")


def test_short_datetime_accepts_an_explicit_year():
    assert parseIBDatetime("0714 09:30:00 US/Eastern", year=2025) == datetime(
        2025, 7, 14, 9, 30, tzinfo=EASTERN
    )


def test_short_datetime_run_is_dated_from_the_start_bound():
    start = datetime(2025, 7, 14, 8, 59, 54, tzinfo=EASTERN)

    assert parseIBShortDatetimes(
        ["0714 09:30:00 US/Eastern", "0714 10:00:00 US/Eastern"], start=start
    ) == [
        datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN),
        datetime(2025, 7, 14, 10, 0, tzinfo=EASTERN),
    ]


def test_short_datetime_run_rolls_the_year_over():
    start = datetime(2024, 12, 31, 0, 0, tzinfo=EASTERN)

    assert parseIBShortDatetimes(
        ["1231 23:30:00 US/Eastern", "0101 00:30:00 US/Eastern"], start=start
    ) == [
        datetime(2024, 12, 31, 23, 30, tzinfo=EASTERN),
        datetime(2025, 1, 1, 0, 30, tzinfo=EASTERN),
    ]


def test_short_datetime_run_spans_more_than_a_year():
    """A multi-year span is not ambiguous once the run is walked in order,
    so a long ``durationStr`` must not be rejected."""
    start = datetime(2023, 6, 1, 0, 0, tzinfo=EASTERN)
    values = [
        "0601 10:00:00 US/Eastern",
        "1201 10:00:00 US/Eastern",
        "0601 10:00:00 US/Eastern",
        "1201 10:00:00 US/Eastern",
        "0601 10:00:00 US/Eastern",
    ]

    assert parseIBShortDatetimes(values, start=start) == [
        datetime(2023, 6, 1, 10, 0, tzinfo=EASTERN),
        datetime(2023, 12, 1, 10, 0, tzinfo=EASTERN),
        datetime(2024, 6, 1, 10, 0, tzinfo=EASTERN),
        datetime(2024, 12, 1, 10, 0, tzinfo=EASTERN),
        datetime(2025, 6, 1, 10, 0, tzinfo=EASTERN),
    ]


def test_short_datetime_run_is_dated_backwards_from_the_end_bound():
    end = datetime(2025, 1, 1, 12, 0, tzinfo=EASTERN)

    assert parseIBShortDatetimes(
        ["1231 23:30:00 US/Eastern", "0101 00:30:00 US/Eastern"], end=end
    ) == [
        datetime(2024, 12, 31, 23, 30, tzinfo=EASTERN),
        datetime(2025, 1, 1, 0, 30, tzinfo=EASTERN),
    ]


def test_short_datetime_leap_day_survives():
    start = datetime(2024, 2, 28, 0, 0, tzinfo=EASTERN)

    assert parseIBShortDatetimes(
        ["0228 10:00:00 US/Eastern", "0229 10:00:00 US/Eastern"], start=start
    ) == [
        datetime(2024, 2, 28, 10, 0, tzinfo=EASTERN),
        datetime(2024, 2, 29, 10, 0, tzinfo=EASTERN),
    ]


def test_short_datetime_anchor_before_the_first_bar_does_not_shift_a_year():
    """The start bound can sit a session ahead of the first bar; that must
    not push the run into the following year."""
    start = datetime(2025, 7, 14, 10, 0, tzinfo=EASTERN)

    assert parseIBShortDatetimes(["0714 09:30:00 US/Eastern"], start=start) == [
        datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN)
    ]


def test_no_short_datetimes_yields_nothing():
    assert parseIBShortDatetimes([]) == []


# -- wrapper layer ------------------------------------------------------------


def test_short_bars_are_dated_at_end_of_dataset():
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=EASTERN))
    future = _openBarRequest(ib)

    for date in ("0714 09:30:00 US/Eastern", "0714 10:00:00 US/Eastern"):
        ib.wrapper.historicalData(1, ibi.BarData(date=date))

    ib.wrapper.historicalDataEnd(
        1, "20250714 08:59:54 US/Eastern", "20250715 08:59:54 US/Eastern"
    )

    assert [bar.date for bar in future.result()] == [
        datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN),
        datetime(2025, 7, 14, 10, 0, tzinfo=EASTERN),
    ]


def test_short_bars_without_response_bounds_fall_back_to_now():
    """IB always reports bounds, but a dataset must never be lost when it
    doesn't -- the run is anchored on the current time instead."""
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=EASTERN))
    future = _openBarRequest(ib)

    now = datetime.now(EASTERN)
    ib.wrapper.historicalData(1, ibi.BarData(date=now.strftime("%m%d 10:00:00 UTC")))
    ib.wrapper.historicalDataEnd(1, "", "")

    (bar,) = future.result()
    assert isinstance(bar.date, datetime)
    assert abs((bar.date - now).days) <= 1


def test_full_bars_still_date_on_arrival():
    """Only ``formatDate=3`` defers; every other format must keep dating
    each bar as it lands so nothing downstream sees a raw wire string."""
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=EASTERN))
    _openBarRequest(ib)

    ib.wrapper.historicalData(1, ibi.BarData(date="20250714 09:30:00 US/Eastern"))

    req = ib.wrapper.requests.get(ReqIdKey(1))
    assert req is not None
    assert req.container[0].date == datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN)


def test_short_bar_update_is_dated_against_the_previous_bar():
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=EASTERN))
    bars = ibi.BarDataList()
    contract = ibi.Stock("AAPL", "SMART", "USD", conId=265598)
    bars.contract = contract
    ib.wrapper.subscriptions.add(
        HistoricalBarsSub(reqId=1, contract=contract, bars=bars)
    )
    bars.append(ibi.BarData(date=datetime(2024, 12, 31, 23, 30, tzinfo=EASTERN)))

    ib.wrapper.historicalDataUpdate(1, ibi.BarData(date="0101 00:30:00 US/Eastern"))

    assert bars[-1].date == datetime(2025, 1, 1, 0, 30, tzinfo=EASTERN)


def test_short_bar_update_before_the_dataset_is_dated_is_dropped():
    """An update that races ``historicalDataEnd`` has nothing to order
    itself against and must be skipped rather than crash the callback."""
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=EASTERN))
    bars = ibi.BarDataList()
    contract = ibi.Stock("AAPL", "SMART", "USD", conId=265598)
    bars.contract = contract
    ib.wrapper.subscriptions.add(
        HistoricalBarsSub(reqId=1, contract=contract, bars=bars)
    )
    bars.append(ibi.BarData(date="0714 09:30:00 US/Eastern"))

    ib.wrapper.historicalDataUpdate(1, ibi.BarData(date="0714 10:00:00 US/Eastern"))

    assert len(bars) == 1


# -- decoder layer ------------------------------------------------------------


@requiresSplitEndFrame
def test_short_bars_survive_the_split_end_frame():
    """From ``MIN_SERVER_VER_HISTORICAL_DATA_END`` the bounds ship in their
    own frame after the bars, so nothing inside the bar frame can date
    them."""
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=EASTERN))
    ib.client.serverVersion = lambda: 225  # type: ignore[method-assign]
    ib.wrapper.clientId = 0
    future = _openBarRequest(ib, reqId=6)

    decoder = ib.client.decoder
    decoder.serverVersion = 225
    decoder.historicalData(
        [
            "17",
            "6",
            "2",
            "0714 09:30:00 US/Eastern",
            "209.93",
            "210.91",
            "207.67",
            "207.89",
            "5583527",
            "208.961",
            "28611",
            "0714 10:00:00 US/Eastern",
            "207.90",
            "208.78",
            "207.54",
            "208.03",
            "2978782",
            "208.082",
            "16926",
        ]
    )
    decoder.historicalDataEnd(
        ["108", "6", "20250714 08:59:54 US/Eastern", "20250715 08:59:54 US/Eastern"]
    )

    assert [bar.date for bar in future.result()] == [
        datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN),
        datetime(2025, 7, 14, 10, 0, tzinfo=EASTERN),
    ]


def test_short_bars_survive_the_legacy_inline_end():
    """Below ``MIN_SERVER_VER_HISTORICAL_DATA_END`` the bounds ride in the
    bar frame -- the payload from the original report."""
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=EASTERN))
    future = _openBarRequest(ib, reqId=6)

    decoder = ib.client.decoder
    decoder.serverVersion = 195
    decoder.historicalData(
        [
            "17",
            "6",
            "20250714 08:59:54 US/Eastern",
            "20250715 08:59:54 US/Eastern",
            "1",
            "0714 09:30:00 US/Eastern",
            "209.93",
            "210.91",
            "207.67",
            "207.89",
            "5583527",
            "208.961",
            "28611",
        ]
    )

    assert [bar.date for bar in future.result()] == [
        datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN)
    ]
