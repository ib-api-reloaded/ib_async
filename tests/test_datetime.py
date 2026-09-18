"""Date parsing and execution decoding require no running TWS connection."""

import datetime as dt
import os
import time
from types import SimpleNamespace
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from ib_async.decoder import Decoder
from ib_async.util import parseIBDatetime


@pytest.fixture(params=["UTC", "America/Los_Angeles"])
def local_timezone(request, monkeypatch):
    if not hasattr(time, "tzset"):
        pytest.skip("Changing the process timezone requires time.tzset")
    original = os.environ.get("TZ")
    monkeypatch.setenv("TZ", request.param)
    time.tzset()
    try:
        yield request.param
    finally:
        if original is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", original)
        time.tzset()


@pytest.mark.parametrize(
    "raw, expected",
    [
        (
            "20260916-15:01:20",
            dt.datetime(2026, 9, 16, 15, 1, 20, tzinfo=dt.timezone.utc),
        ),
        (
            "20260116-15:01:20",
            dt.datetime(2026, 1, 16, 15, 1, 20, tzinfo=dt.timezone.utc),
        ),
        (
            "20261101-08:30:00",
            dt.datetime(2026, 11, 1, 8, 30, tzinfo=dt.timezone.utc),
        ),
        (
            "20261101-09:30:00",
            dt.datetime(2026, 11, 1, 9, 30, tzinfo=dt.timezone.utc),
        ),
    ],
)
def test_hyphenated_utc_datetime_is_aware(raw, expected, local_timezone):
    parsed = parseIBDatetime(raw)
    assert parsed == expected
    assert parsed.tzinfo is dt.timezone.utc


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("20260916", dt.date(2026, 9, 16)),
        ("1700000000", dt.datetime.fromtimestamp(1700000000, dt.timezone.utc)),
        (
            "20260916 15:01:20 UTC",
            dt.datetime(2026, 9, 16, 15, 1, 20, tzinfo=ZoneInfo("UTC")),
        ),
        (
            "20260916 08:01:20 America/Los_Angeles",
            dt.datetime(2026, 9, 16, 8, 1, 20, tzinfo=ZoneInfo("America/Los_Angeles")),
        ),
        (
            "20260916 15:01:20 GB-Eire",
            dt.datetime(2026, 9, 16, 15, 1, 20, tzinfo=ZoneInfo("GB-Eire")),
        ),
        ("20260916  15:01:20", dt.datetime(2026, 9, 16, 15, 1, 20)),
        ("20260916 15:01:20", dt.datetime(2026, 9, 16, 15, 1, 20)),
        ("2026-09-16 15:01:20.0", dt.datetime(2026, 9, 16, 15, 1, 20)),
    ],
)
def test_existing_datetime_formats_are_unchanged(raw, expected):
    assert parseIBDatetime(raw) == expected


@pytest.mark.parametrize(
    "raw", ["20261316-15:01:20", "20260916-25:01:20", "20260230-15:01:20"]
)
def test_invalid_hyphenated_utc_datetime_is_rejected(raw):
    with pytest.raises(ValueError):
        parseIBDatetime(raw)


@pytest.mark.parametrize("server_version", [177, 178])
@pytest.mark.parametrize("security_type", ["FUT", "BAG"])
@pytest.mark.parametrize("tws_timezone", ["", "America/Los_Angeles"])
@pytest.mark.parametrize("raw", ["20260916-15:01:20", "20260116-15:01:20"])
def test_execution_utc_time_does_not_use_local_or_tws_timezone(
    server_version, security_type, tws_timezone, raw, local_timezone
):
    wrapper = Mock()
    wrapper.defaultTimezone = dt.timezone.utc
    wrapper.ib = SimpleNamespace(TimezoneTWS=tws_timezone)
    decoder = Decoder(wrapper, server_version)
    fields = [
        "11",
        "77",
        "1",
        "100",
        "TEST",
        security_type,
        "20261216",
        "0",
        "",
        "125000",
        "CME",
        "USD",
        "TESTZ6",
        "TEST",
        "0001.0002.01.01",
        raw,
        "DU123",
        "CME",
        "SLD",
        "1",
        "1.2339",
        "333",
        "7",
        "0",
        "1",
        "1.2339",
        "",
        "",
        "0",
        "",
        "0",
    ]
    if server_version >= 178:
        fields.append("0")

    decoder.execDetails(fields)

    wrapper.execDetails.assert_called_once()
    request_id, contract, execution = wrapper.execDetails.call_args.args
    expected = dt.datetime.strptime(raw, "%Y%m%d-%H:%M:%S").replace(
        tzinfo=dt.timezone.utc
    )
    assert execution.time == expected
    assert execution.time.tzinfo is dt.timezone.utc
    assert request_id == 77
    assert contract.secType == security_type
    assert contract.conId == 100
    assert execution.execId == "0001.0002.01.01"
    assert execution.permId == 333
    assert execution.clientId == 7
    assert execution.side == "SLD"
    assert execution.shares == execution.cumQty == 1
    assert execution.price == execution.avgPrice == 1.2339


@pytest.mark.parametrize(
    "raw, expected_local, expected_fold",
    [
        ("20260916-15:01:20", (2026, 9, 16, 8, 1, 20), 0),
        ("20260116-15:01:20", (2026, 1, 16, 7, 1, 20), 0),
        ("20261101-08:30:00", (2026, 11, 1, 1, 30, 0), 0),
        ("20261101-09:30:00", (2026, 11, 1, 1, 30, 0), 1),
    ],
)
def test_utc_conversion_respects_daylight_saving(raw, expected_local, expected_fold):
    local = parseIBDatetime(raw).astimezone(ZoneInfo("America/Los_Angeles"))
    assert local.replace(tzinfo=None) == dt.datetime(*expected_local)
    assert local.fold == expected_fold
