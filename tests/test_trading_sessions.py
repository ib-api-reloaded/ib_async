"""ContractDetails.tradingSessions and liquidSessions, from the text IBKR
sends.

tradingHours and liquidHours list one entry per closed day or session,
separated by ';': 'yyyymmdd:CLOSED' or 'yyyymmdd:hhmm-yyyymmdd:hhmm'. A
session may end on a later day (a future's overnight session), a day may
hold several sessions, and the text may end with ';'. Times are in the
contract's timeZoneId.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from hypothesis import given
from hypothesis import strategies as st

from ib_async import ContractDetails, TradingSession
from tests._property import examples

ZONES = ["US/Eastern", "US/Central", "Europe/London", "Asia/Tokyo", "Asia/Seoul"]

minutes = st.datetimes(dt.datetime(2020, 1, 1), dt.datetime(2035, 12, 31)).map(
    lambda t: t.replace(second=0, microsecond=0)
)
# A session, as its start and length, or a closed day.
entries = st.one_of(
    st.tuples(minutes, st.integers(1, 24 * 60)),
    st.dates(dt.date(2020, 1, 1), dt.date(2035, 12, 31)),
)


def presented(entry: tuple[dt.datetime, int] | dt.date) -> str:
    if isinstance(entry, dt.date):
        return f"{entry:%Y%m%d}:CLOSED"
    start, length = entry
    end = start + dt.timedelta(minutes=length)
    return f"{start:%Y%m%d:%H%M}-{end:%Y%m%d:%H%M}"


def session(entry: tuple[dt.datetime, int], zone: ZoneInfo) -> TradingSession:
    start, length = entry
    end = start + dt.timedelta(minutes=length)
    return TradingSession(start.replace(tzinfo=zone), end.replace(tzinfo=zone))


@given(
    zone=st.sampled_from(ZONES),
    trading=st.lists(entries, max_size=8),
    liquid=st.lists(entries, max_size=8),
    trailing=st.booleans(),
)
@examples()
def test_sessions_are_the_open_entries_in_the_contract_zone(
    zone: str,
    trading: list[tuple[dt.datetime, int] | dt.date],
    liquid: list[tuple[dt.datetime, int] | dt.date],
    trailing: bool,
) -> None:
    end = ";" if trailing else ""
    details = ContractDetails(
        timeZoneId=zone,
        tradingHours=";".join(map(presented, trading)) + end,
        liquidHours=";".join(map(presented, liquid)) + end,
    )
    tz = ZoneInfo(zone)
    assert details.tradingSessions() == [
        session(e, tz) for e in trading if not isinstance(e, dt.date)
    ]
    assert details.liquidSessions() == [
        session(e, tz) for e in liquid if not isinstance(e, dt.date)
    ]


def test_ibkr_documented_hours() -> None:
    eastern = ZoneInfo("US/Eastern")
    details = ContractDetails(
        timeZoneId="US/Eastern",
        tradingHours="20240721:CLOSED;20240722:0400-20240722:2000",
        liquidHours="20240721:CLOSED;20240722:0930-20240722:1600",
    )
    assert details.tradingSessions() == [
        TradingSession(
            dt.datetime(2024, 7, 22, 4, 0, tzinfo=eastern),
            dt.datetime(2024, 7, 22, 20, 0, tzinfo=eastern),
        )
    ]
    assert details.liquidSessions() == [
        TradingSession(
            dt.datetime(2024, 7, 22, 9, 30, tzinfo=eastern),
            dt.datetime(2024, 7, 22, 16, 0, tzinfo=eastern),
        )
    ]


def test_no_hours_are_no_sessions() -> None:
    assert ContractDetails().tradingSessions() == []
    assert ContractDetails(timeZoneId="US/Eastern").liquidSessions() == []
