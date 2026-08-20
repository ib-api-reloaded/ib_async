import datetime as dt
from zoneinfo import ZoneInfo

import pytest

from ib_async.decoder import Decoder
from ib_async.objects import BarData
from ib_async.util import parseIBDatetime

EASTERN = ZoneInfo("US/Eastern")


def _full(value: str) -> dt.datetime:
    parsed = parseIBDatetime(value)
    assert isinstance(parsed, dt.datetime)
    return parsed


def test_parse_format_date_3_uses_response_year() -> None:
    start = _full("20250714 08:59:54 US/Eastern")
    end = _full("20250715 08:59:54 US/Eastern")

    parsed = parseIBDatetime(
        "0714 09:30:00 US/Eastern",
        start=start,
        end=end,
    )

    assert parsed == dt.datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN)


def test_parse_format_date_3_handles_year_rollover() -> None:
    start = _full("20241231 00:00:00 US/Eastern")
    end = _full("20250102 00:00:00 US/Eastern")

    assert (
        parseIBDatetime("1231 23:30:00 US/Eastern", start=start, end=end).year == 2024
    )
    assert (
        parseIBDatetime("0101 00:30:00 US/Eastern", start=start, end=end).year == 2025
    )


def test_parse_format_date_3_rejects_ambiguous_year() -> None:
    start = _full("20240101 00:00:00 US/Eastern")
    end = _full("20250102 00:00:00 US/Eastern")

    with pytest.raises(ValueError, match="2 candidates"):
        parseIBDatetime("0101 00:30:00 US/Eastern", start=start, end=end)


def test_parse_format_date_3_rejects_date_outside_response_range() -> None:
    start = _full("20250714 08:59:54 US/Eastern")
    end = _full("20250715 08:59:54 US/Eastern")

    with pytest.raises(ValueError, match="no candidate"):
        parseIBDatetime("0713 09:30:00 US/Eastern", start=start, end=end)


def test_parse_format_date_3_requires_context() -> None:
    with pytest.raises(ValueError, match="without a response range"):
        parseIBDatetime("0714 09:30:00 US/Eastern")


def test_existing_datetime_formats_are_unchanged() -> None:
    assert parseIBDatetime("20250714") == dt.date(2025, 7, 14)
    assert parseIBDatetime("1752501600") == dt.datetime.fromtimestamp(
        1752501600, dt.timezone.utc
    )
    assert parseIBDatetime("20250714 09:30:00 US/Eastern") == dt.datetime(
        2025, 7, 14, 9, 30, tzinfo=EASTERN
    )


class _RecordingWrapper:
    def __init__(self) -> None:
        self.bars: list[BarData] = []
        self.end: tuple[int, str, str] | None = None

    def historicalData(self, reqId: int, bar: BarData) -> None:
        self.bars.append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str) -> None:
        self.end = (reqId, start, end)


def test_decoder_parses_short_bars_before_wrapper() -> None:
    wrapper = _RecordingWrapper()
    decoder = Decoder(wrapper, serverVersion=177)
    start = "20250714 08:59:54 US/Eastern"
    end = "20250715 08:59:54 US/Eastern"
    fields = [
        "17",
        "6",
        start,
        end,
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

    decoder.historicalData(fields)

    assert [bar.date for bar in wrapper.bars] == [
        dt.datetime(2025, 7, 14, 9, 30, tzinfo=EASTERN),
        dt.datetime(2025, 7, 14, 10, 0, tzinfo=EASTERN),
    ]
    assert wrapper.end == (6, start, end)
