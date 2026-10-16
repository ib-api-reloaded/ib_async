"""Property tests for IB datetime formatting and parsing.

- A time formatted for IB parses back to the same instant.
- A date formatted for IB parses back to the same day.
- A string that is not an IB datetime raises ValueError and no other
  exception.
- A last trade date splits into its date, time and zone.
- A sequence of formatDate=3 timestamps, which have no year, gets the
  years that keep it in order from its anchor.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ib_async import util
from tests._property import examples

ZONES = ["UTC", "US/Eastern", "Europe/Amsterdam", "Asia/Tokyo"]
instants = st.datetimes(
    dt.datetime(1990, 1, 1),
    dt.datetime(2099, 12, 31),
    timezones=st.sampled_from(ZONES).map(ZoneInfo),
).map(lambda t: t.replace(microsecond=0))


@given(when=instants)
@examples()
def test_time_round_trip(when):
    parsed = util.parseIBDatetime(util.formatIBDatetime(when))
    assert isinstance(parsed, dt.datetime)
    # The result is the same instant in UTC. Compare timestamps, because
    # aware datetimes in a DST fold compare unequal across zones.
    assert parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0)
    assert parsed.timestamp() == when.timestamp()


@given(day=st.dates(dt.date(1990, 1, 1), dt.date(2099, 12, 31)))
@examples()
def test_date_round_trip(day):
    parsed = util.parseIBDatetime(util.formatIBDatetime(day))
    assert isinstance(parsed, dt.datetime)
    # A date is formatted as the end of that local day, in UTC.
    assert parsed.astimezone().date() == day


@given(
    text=st.one_of(
        st.text(max_size=24),
        st.integers(0, 10**22).map(str),
        st.sampled_from(
            [
                "20221125 10:00:00 Nowhere/Land",
                "1125 10:00:00 UTC",
                "99999999",
                "20221301 00:00:00 UTC",
                "20221125-25:00:00",
            ]
        ),
    )
)
@examples()
def test_invalid_string_raises_only_value_error(text):
    try:
        parsed = util.parseIBDatetime(text)
    except ValueError:
        return
    assert isinstance(parsed, dt.date)


@given(
    date=st.sampled_from(["20250331", "20260619"]),
    time=st.sampled_from(["", "19:30:00", "15:00:00"]),
    zone=st.sampled_from(["", "GB-Eire", "US/Eastern", "UTC"]),
    hyphenated=st.booleans(),
)
@examples()
def test_last_trade_date_splits_into_parts(date, time, zone, hyphenated):
    """IB writes either ``date time zone`` separated by spaces, or
    ``date-time`` separated by a hyphen.

    In the space form the zone name may contain a hyphen (GB-Eire). The
    hyphen form is never used with such a zone."""
    parts = [p for p in (date, time, zone) if p]
    hyphenated = hyphenated and "-" not in zone
    value = ("-" if hyphenated else " ").join(parts)
    split = util.splitIBLastTradeDate(value)
    assert 1 <= len(split) <= 3
    assert split[0] == date
    if time:
        assert split[1] == time
    if zone:
        assert split[-1] == zone


@given(
    start=st.datetimes(
        dt.datetime(2000, 1, 1),
        dt.datetime(2098, 1, 1),
        timezones=st.just(ZoneInfo("UTC")),
    ).map(lambda t: t.replace(microsecond=0)),
    steps=st.lists(st.integers(1, 20 * 86400), min_size=1, max_size=12),
)
@examples()
def test_short_datetimes_get_years_in_order(start, steps):
    """formatDate=3 bars have ``MMdd HH:MM:SS`` and a zone but no year.

    Given an anchor, a sequence of them gets the correct year for each
    timestamp, including across a new year."""
    times = [start]
    for step in steps:
        times.append(times[-1] + dt.timedelta(seconds=step))
    short = [t.strftime("%m%d %H:%M:%S UTC") for t in times]
    assert all(util.isIBShortDatetime(s) for s in short)
    placed = util.parseIBShortDatetimes(short, start=start)
    assert placed == times
    placedFromEnd = util.parseIBShortDatetimes(short, end=times[-1])
    assert placedFromEnd == times


def test_single_short_datetime_needs_year():
    with pytest.raises(ValueError, match="carries no year"):
        util.parseIBDatetime("1125 10:00:00 UTC")
    assert util.parseIBDatetime("1125 10:00:00 UTC", year=2022) == dt.datetime(
        2022, 11, 25, 10, tzinfo=ZoneInfo("UTC")
    )
