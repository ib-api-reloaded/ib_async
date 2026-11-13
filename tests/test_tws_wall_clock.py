"""Every time TWS sends is resolved by one rule.

A time with a zone, or in the hyphenated UTC form, is that instant. A time
without a zone is a wall clock in TWS's own zone: ``TimezoneTWS``, or the
default time zone (``IBDefaults.timezone``) when that is unset. The host's
zone never counts. Every result is shown in the default time zone.

Executions, bars, head timestamps and historical news all follow it. The
tests run with the host in Tokyo, a zone no setting names.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey

EASTERN = ZoneInfo("America/New_York")
LONDON = ZoneInfo("Europe/London")

# 2026-05-09 09:30 New York is 13:30 UTC.
EASTERN_OPEN = datetime(2026, 5, 9, 13, 30, tzinfo=UTC)


@pytest.fixture(autouse=True)
def tokyoHost(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("TZ", "Asia/Tokyo")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def execution(ib: ibi.IB, s: str) -> datetime:
    return ib.client.decoder._normalizeExecutionTime(s)


def bar(ib: ibi.IB, s: str) -> datetime:
    ib.wrapper.requests.open(ReqIdKey(1))
    received = ibi.BarData(date=s)
    ib.wrapper.historicalData(1, received)
    assert isinstance(received.date, datetime)
    return received.date


def headTimestamp(ib: ibi.IB, s: str) -> datetime:
    future = ib.wrapper.requests.open(ReqIdKey(2)).future
    ib.wrapper.headTimestamp(2, s)
    return future.result()


def news(ib: ibi.IB, s: str) -> datetime:
    future = ib.wrapper.requests.open(ReqIdKey(3)).future
    ib.wrapper.historicalNews(3, s, "BZ", "a", "h")
    ib.wrapper.historicalNewsEnd(3, False)
    return future.result()[0].time


PATHS: list[Callable[[ibi.IB, str], datetime]] = [execution, bar, headTimestamp, news]


def ib(timezoneTWS: str = "", defaults: ZoneInfo = UTC) -> ibi.IB:
    made = ibi.IB(defaults=ibi.IBDefaults(timezone=defaults))
    made.TimezoneTWS = timezoneTWS
    return made


@pytest.mark.parametrize("path", PATHS)
def test_zoneless_time_is_in_timezone_tws(path: Callable[[ibi.IB, str], datetime]):
    assert path(ib("US/Eastern"), "20260509  09:30:00") == EASTERN_OPEN


@pytest.mark.parametrize("path", PATHS)
def test_zoneless_time_without_timezone_tws_is_in_the_default_zone(
    path: Callable[[ibi.IB, str], datetime],
):
    assert path(ib(defaults=EASTERN), "20260509  09:30:00") == EASTERN_OPEN


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize(
    "s",
    [
        "20260509 09:30:00 US/Eastern",
        "20260509-13:30:00",
        "20260509 13:30:00 UTC",
        # A Z suffix marks UTC, with or without a space before it.
        "20260509-13:30:00Z",
        "20260509-13:30:00 Z",
        "20260509 13:30:00Z",
        "20260509 13:30:00 Z",
    ],
)
@pytest.mark.parametrize("timezoneTWS", ["", "Asia/Kolkata"])
def test_time_with_a_zone_ignores_every_setting(
    path: Callable[[ibi.IB, str], datetime], s: str, timezoneTWS: str
):
    assert path(ib(timezoneTWS, defaults=LONDON), s) == EASTERN_OPEN


def test_a_zone_name_ending_in_z_is_still_that_zone():
    """NZ is New Zealand, not a Z suffix."""
    parsed = ibi.util.parseIBDatetime("20260509 09:30:00 NZ")
    assert parsed == datetime(2026, 5, 9, 9, 30, tzinfo=ZoneInfo("NZ"))


@pytest.mark.parametrize("path", PATHS)
def test_every_time_is_shown_in_the_default_zone(
    path: Callable[[ibi.IB, str], datetime],
):
    result = path(ib(defaults=LONDON), "20260509 09:30:00 US/Eastern")
    assert result.tzinfo is LONDON
    assert result.hour == 14
