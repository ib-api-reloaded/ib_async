import asyncio
import datetime as dt
import enum
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ib_async.util import (
    UNSET_DECIMAL,
    UNSET_DOUBLE,
    UNSET_INTEGER,
    _fillDate,
    dataclassAsDict,
    dataclassAsTuple,
    dataclassNonDefaults,
    dataclassRepr,
    dataclassUpdate,
    decimalMaxString,
    df,
    floatMaxString,
    formatIBDatetime,
    formatSI,
    getEnumTypeFromString,
    getLoop,
    globalErrorEvent,
    isnamedtupleinstance,
    isNan,
    isValidIntValue,
    listOfValues,
    parseIBDatetime,
    parseIBTimeStamp,
    patchAsyncio,
    quantize_decimals,
    run,
    schedule,
    sleep,
    timeit,
    timeRange,
    timeRangeAsync,
    tree,
    waitUntil,
    waitUntilAsync,
)


# Dummy dataclasses for testing
@dataclass
class TestDataClass:
    a: int
    b: str = "default"
    c: float = 1.0
    d: Decimal = Decimal("1.23")
    e: list = field(default_factory=list)
    f: dict = field(default_factory=dict)


@dataclass
class AnotherTestDataClass:
    x: int = 10
    y: str = "hello"


@dataclass
class DataClassWithDecimal:
    value: Decimal


# Dummy Enum for testing
class TestEnum(enum.Enum):
    ALPHA = "A", "AlphaValue"
    BETA = "B", "BetaValue"
    GAMMA = "C", "GammaValue"

    def __init__(self, char_val, description):
        self.char_val = char_val
        self.description = description

    @property
    def value(self):
        return self.char_val, self.description

    @classmethod
    def from_char(cls, char_val):
        for member in cls:
            if member.char_val == char_val:
                return member
        raise ValueError(f"No member with char_val '{char_val}'")


@pytest.fixture(autouse=True)
def clear_global_error_event():
    """Fixture to reset globalErrorEvent before each test."""
    globalErrorEvent.clear()
    yield


def test_dataclassAsDict():
    obj = TestDataClass(a=1, b="test")
    expected = {
        "a": 1,
        "b": "test",
        "c": 1.0,
        "d": Decimal("1.23"),
        "e": [],
        "f": {},
    }
    assert dataclassAsDict(obj) == expected

    with pytest.raises(TypeError):
        dataclassAsDict(123)


def test_dataclassAsTuple():
    obj = TestDataClass(a=1, b="test")
    expected = (1, "test", 1.0, Decimal("1.23"), [], {})
    assert dataclassAsTuple(obj) == expected

    with pytest.raises(TypeError):
        dataclassAsTuple("not_a_dataclass")


def test_dataclassNonDefaults():
    obj1 = TestDataClass(a=1)
    assert dataclassNonDefaults(obj1) == {"a": 1}

    obj2 = TestDataClass(a=1, b="non-default", c=2.0, d=Decimal("3.45"))
    expected2 = {"a": 1, "b": "non-default", "c": 2.0, "d": Decimal("3.45")}
    assert dataclassNonDefaults(obj2) == expected2

    obj3 = TestDataClass(a=1, e=[1, 2])
    assert dataclassNonDefaults(obj3) == {"a": 1, "e": [1, 2]}

    with pytest.raises(TypeError):
        dataclassNonDefaults({"a": 1})


def test_dataclassUpdate():
    obj = TestDataClass(a=1, b="original")
    src_obj = AnotherTestDataClass(x=20, y="updated")

    # Test update from kwargs
    dataclassUpdate(obj, a=5, b="new")
    assert obj.a == 5
    assert obj.b == "new"

    # Test update from another dataclass (only matching fields)
    dataclassUpdate(obj, src_obj, a=100)  # src_obj doesn't have 'a' or 'b'
    assert obj.a == 100
    assert obj.b == "new"
    assert obj.c == 1.0

    # Test update from dataclass where fields match
    @dataclass
    class MatchingSrc:
        a: int = 0
        c: float = 0.0

    match_src = MatchingSrc(a=99, c=9.9)
    dataclassUpdate(obj, match_src)
    assert obj.a == 99
    assert obj.c == 9.9
    assert obj.b == "new"

    with pytest.raises(TypeError):
        dataclassUpdate("not_a_dataclass", a=1)


def test_dataclassRepr():
    obj1 = TestDataClass(a=1)
    assert dataclassRepr(obj1) == "TestDataClass(a=1)"

    obj2 = TestDataClass(a=1, b="custom")
    assert dataclassRepr(obj2) == "TestDataClass(a=1, b='custom')"

    obj3 = TestDataClass(a=1, c=2.5)
    assert dataclassRepr(obj3) == "TestDataClass(a=1, c=2.5)"

    obj4 = TestDataClass(a=1, e=[1, 2, 3])
    assert dataclassRepr(obj4) == "TestDataClass(a=1, e=[1, 2, 3])"


def test_isnamedtupleinstance():
    from collections import namedtuple

    Point = namedtuple("Point", "x y")
    p = Point(1, 2)
    assert isnamedtupleinstance(p)
    assert not isnamedtupleinstance((1, 2))
    assert not isnamedtupleinstance([1, 2])
    assert not isnamedtupleinstance(TestDataClass(a=1))


def test_tree():
    # Basic types
    assert tree(1) == 1
    assert tree("hello") == "hello"
    assert tree(True) is True
    assert tree(1.5) == 1.5
    assert tree(b"bytes") == b"bytes"

    # Datetime/date
    d = dt.date(2023, 1, 1)
    assert tree(d) == "2023-01-01"
    dt_obj = dt.datetime(2023, 1, 1, 10, 30, 0)
    assert tree(dt_obj) == "2023-01-01T10:30:00"

    # Dict
    assert tree({"a": 1, "b": "c"}) == {"a": 1, "b": "c"}

    # Namedtuple
    from collections import namedtuple

    Point = namedtuple("Point", "x y")
    p = Point(1, "two")
    assert tree(p) == {"x": 1, "y": "two"}

    # List, tuple, set
    assert tree([1, 2, "a"]) == [1, 2, "a"]
    assert tree((1, 2, "a")) == [1, 2, "a"]
    assert sorted(tree({1, 2, 3})) == [1, 2, 3]

    # Dataclass
    obj = TestDataClass(a=1, b="custom")
    expected_dataclass_tree = {"TestDataClass": {"a": 1, "b": "custom"}}
    assert tree(obj) == expected_dataclass_tree

    # Nested structure
    nested_obj = {
        "num": 1,
        "text": "test",
        "date": dt.date(2024, 5, 10),
        "data": TestDataClass(a=5, c=3.3),
        "items": [Point(10, 20), {"key": "value"}],
    }
    expected_nested_tree = {
        "num": 1,
        "text": "test",
        "date": "2024-05-10",
        "data": {"TestDataClass": {"a": 5, "c": 3.3}},
        "items": [{"x": 10, "y": 20}, {"key": "value"}],
    }
    assert tree(nested_obj) == expected_nested_tree

    # Other objects
    class CustomClass:
        def __str__(self):
            return "Custom"

    assert tree(CustomClass()) == "Custom"


def test_isNan():
    assert isNan(float("nan"))
    assert not isNan(1.0)
    assert not isNan(0.0)
    assert not isNan(float("inf"))
    assert not isNan(-1.0)


def test_formatSI():
    assert formatSI(0) == "0 "
    assert formatSI(1) == "1 "
    assert formatSI(10) == "10 "
    assert formatSI(100) == "100 "
    assert formatSI(1000) == "1.00 k"
    assert formatSI(1234) == "1.23 k"
    assert formatSI(1234567) == "1.23 M"
    assert formatSI(0.1) == "100 m"
    assert formatSI(0.01) == "10.0 m"
    assert formatSI(0.001) == "1.00 m"
    assert formatSI(0.000000001) == "1.00 n"
    assert formatSI(-1234) == "-1.23 k"
    assert formatSI(1000000000000000000000000.0) == "1.00 Y"  # Yotta
    assert (
        formatSI(0.000000000000000000000001) == "0.00 "
    )  # yocto - incorrect in implementation
    assert formatSI(0.0000000000000000000000001) == "0.00 "  # smaller than yocto


@patch("builtins.print")
@patch("time.time", side_effect=[0, 1.5])
def test_timeit(mock_time, mock_print):
    with timeit("Test Run"):
        pass
    mock_print.assert_called_once_with("Test Run took 1.50 s")


@patch("builtins.print")
@patch("time.time", side_effect=[0, 12345.678])
def test_timeit_format_si(mock_time, mock_print):
    with timeit("Long Run"):
        pass
    mock_print.assert_called_once_with("Long Run took 12.3 ks")


def test_formatIBDatetime():
    assert formatIBDatetime(None) == ""

    # Datetime
    dt_obj = dt.datetime(2023, 1, 15, 10, 30, 45, tzinfo=dt.timezone.utc)
    assert formatIBDatetime(dt_obj) == "20230115 10:30:45 UTC"

    dt_obj_ny = dt.datetime(
        2023, 1, 15, 5, 30, 45, tzinfo=dt.timezone(dt.timedelta(hours=-5))
    )  # EST
    assert formatIBDatetime(dt_obj_ny) == "20230115 10:30:45 UTC"

    # Date
    date_obj = dt.date(2023, 2, 1)
    assert formatIBDatetime(date_obj) == "20230201 22:59:59 UTC"

    # String (pass-through)
    assert formatIBDatetime("20230301 12:00:00") == "20230301 12:00:00"


@patch("ib_async.util.ZoneInfo", create=True)
def test_parseIBDatetime(MockZoneInfo):
    from zoneinfo import ZoneInfo as RealZoneInfo

    MockZoneInfo.side_effect = lambda x: RealZoneInfo(x)

    # YYYYmmdd
    assert parseIBDatetime("20230101") == dt.date(2023, 1, 1)

    # Timestamp as string
    timestamp_str = str(
        int(dt.datetime(2023, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc).timestamp())
    )
    assert parseIBDatetime(timestamp_str) == dt.datetime(
        2023, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc
    )

    # YYYYmmdd HH:MM:SS Europe/Amsterdam
    result = parseIBDatetime("20221125 10:00:00 Europe/Amsterdam")
    expected = dt.datetime(
        2022, 11, 25, 10, 0, 0, tzinfo=RealZoneInfo("Europe/Amsterdam")
    )
    assert result == expected
    MockZoneInfo.assert_called_with("Europe/Amsterdam")

    # YYYYmmdd  HH:MM:SS
    assert parseIBDatetime("20230101  12:30:45") == dt.datetime(2023, 1, 1, 12, 30, 45)

    # YYYY-mm-dd HH:MM:SS.0
    assert parseIBDatetime("2023-01-01 12:30:45.0") == dt.datetime(
        2023, 1, 1, 12, 30, 45
    )
    assert parseIBDatetime("2023-01-01 12:30:45") == dt.datetime(2023, 1, 1, 12, 30, 45)


def test_parseIBTimeStamp():
    timestamp = 1672531200  # 2023-01-01 00:00:00 UTC
    expected_dt = dt.datetime(2023, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
    assert parseIBTimeStamp(timestamp) == expected_dt

    # With different timezone
    ny_tz = dt.timezone(dt.timedelta(hours=-5))
    # timestamp is UTC, so parsing it with a -5h offset will result in a time 5h earlier
    expected_dt_ny = dt.datetime(2022, 12, 31, 19, 0, 0, tzinfo=ny_tz)
    assert parseIBTimeStamp(timestamp, tz=ny_tz) == expected_dt_ny


def test_decimalMaxString():
    assert decimalMaxString(Decimal("123.45")) == "123.45"
    assert decimalMaxString(UNSET_DECIMAL) == ""
    assert decimalMaxString(Decimal("0")) == "0"


def test_floatMaxString():
    assert floatMaxString(123.456789) == "123.456789"
    assert floatMaxString(123.000000) == "123"
    assert floatMaxString(UNSET_DOUBLE) == ""
    assert floatMaxString(0.0) == "0"
    assert floatMaxString(None) == ""


def test_getEnumTypeFromString():
    assert getEnumTypeFromString(TestEnum, "A") == TestEnum.ALPHA
    assert getEnumTypeFromString(TestEnum, "B") == TestEnum.BETA
    assert getEnumTypeFromString(TestEnum, "C") == TestEnum.GAMMA
    # If not found, should return the first enum member
    assert getEnumTypeFromString(TestEnum, "X") == TestEnum.ALPHA


def test_listOfValues():
    expected_list = [TestEnum.ALPHA, TestEnum.BETA, TestEnum.GAMMA]
    assert listOfValues(TestEnum) == expected_list


def test_isValidIntValue():
    assert isValidIntValue(10)
    assert isValidIntValue(0)
    assert not isValidIntValue(UNSET_INTEGER)
    assert isValidIntValue(-1)


def test_quantize_decimals_decorator():
    @quantize_decimals(places=2)
    @dataclass
    class MyResult:
        price: Decimal
        amount: Decimal
        name: str
        not_decimal: float = 1.234

    res = MyResult(price=Decimal("12.3456"), amount=Decimal("7.891"), name="Test")
    assert res.price == Decimal("12.35")
    assert res.amount == Decimal("7.89")
    assert res.name == "Test"
    assert res.not_decimal == 1.234  # float should not be quantized

    # Test with different places and rounding
    @quantize_decimals(places=0, rounding=ROUND_HALF_UP)
    @dataclass
    class MyIntResult:
        count: Decimal

    res_int = MyIntResult(count=Decimal("5.6"))
    assert res_int.count == Decimal("6")

    # Test with a function that returns a non-dataclass
    @quantize_decimals(places=2)
    def return_non_dataclass():
        return "just a string"

    assert return_non_dataclass() == "just a string"

    # Test with a function that returns None
    @quantize_decimals(places=2)
    def return_none():
        return None

    assert return_none() is None


@pytest.mark.asyncio
@patch("asyncio.get_running_loop")
async def test_getLoop_running(mock_get_running_loop):
    mock_loop = MagicMock()
    mock_get_running_loop.return_value = mock_loop
    assert getLoop() == mock_loop
    mock_get_running_loop.assert_called_once()


@pytest.mark.asyncio
@patch("nest_asyncio.apply")
async def test_patchAsyncio(mock_apply):
    patchAsyncio()
    mock_apply.assert_called_once()


def test_fillDate():
    today = dt.date.today()

    # dt.time input
    time_obj = dt.time(10, 30, 0)
    expected_dt = dt.datetime(today.year, today.month, today.day, 10, 30, 0)
    assert _fillDate(time_obj) == expected_dt

    # dt.datetime input
    dt_obj = dt.datetime(2023, 1, 1, 11, 0, 0, tzinfo=dt.timezone.utc)
    assert _fillDate(dt_obj) == dt_obj


@patch("ib_async.util.getLoop")
def test_schedule(mock_getLoop):
    mock_loop = MagicMock()
    mock_getLoop.return_value = mock_loop
    callback = MagicMock()

    now = dt.datetime.now()
    target_time = now + dt.timedelta(seconds=10)

    schedule(target_time, callback, 1, 2, "test")

    mock_loop.call_later.assert_called_once()
    args, _ = mock_loop.call_later.call_args
    delay = args[0]
    assert delay == pytest.approx(10, abs=0.1)
    assert args[1] == callback
    assert args[2:] == (1, 2, "test")

    # Test with dt.time
    mock_loop.reset_mock()
    time_obj = dt.time(now.hour, (now.minute + 1) % 60, now.second)
    schedule(time_obj, callback)
    mock_loop.call_later.assert_called_once()


@patch("ib_async.util.run")
def test_waitUntil(mock_run):
    with patch("datetime.datetime", wraps=dt.datetime) as mock_dt:
        mock_now = dt.datetime(2023, 1, 1, 10, 0, 0)
        mock_dt.now.return_value = mock_now

        target_time = dt.datetime(2023, 1, 1, 10, 0, 5)
        waitUntil(target_time)

        # The argument to run should be an awaitable (coroutine from sleep)
        mock_run.assert_called_once()
        (sleep_coro,) = mock_run.call_args[0]
        # Inspecting coroutines is tricky, but we can check it's from sleep
        assert sleep_coro.__name__ == "sleep"

    with patch("datetime.datetime", wraps=dt.datetime) as mock_dt:
        mock_run.reset_mock()
        mock_now = dt.datetime(2023, 1, 1, 10, 0, 0)
        mock_dt.now.return_value = mock_now
        mock_dt.today.return_value = mock_now.date()
        target_time_obj = dt.time(10, 0, 10)
        waitUntil(target_time_obj)
        mock_run.assert_called_once()


@pytest.mark.asyncio
@patch("asyncio.sleep", new_callable=AsyncMock)
async def test_waitUntilAsync(mock_sleep):
    with patch("datetime.datetime", wraps=dt.datetime) as mock_dt:
        mock_now = dt.datetime(2023, 1, 1, 10, 0, 0)
        mock_dt.now.return_value = mock_now

        # Mock _fillDate for the first part of the test
        with patch("ib_async.util._fillDate") as mock_util_fillDate:
            mock_util_fillDate.side_effect = lambda t: (
                dt.datetime(2023, 1, 1, t.hour, t.minute, t.second)
                if isinstance(t, dt.time)
                else t
            )
            target_time = dt.datetime(2023, 1, 1, 10, 0, 5)
            result = await waitUntilAsync(target_time)
            assert result is True
            mock_sleep.assert_awaited_once_with(5)

        # Reset mock for the second part of the test
        mock_sleep.reset_mock()
        mock_dt.now.return_value = dt.datetime(
            2023, 1, 1, 10, 0, 0
        )  # Reset mock_dt.now
        with patch("ib_async.util._fillDate") as mock_util_fillDate:
            mock_util_fillDate.side_effect = lambda t: (
                dt.datetime(2023, 1, 1, t.hour, t.minute, t.second)
                if isinstance(t, dt.time)
                else t
            )
            target_time_obj = dt.time(10, 0, 10)
            result = await waitUntilAsync(target_time_obj)
            assert result is True
            mock_sleep.assert_awaited_once_with(10)


@patch("ib_async.util.waitUntil")
def test_timeRange(mock_waitUntil):
    start_dt = dt.datetime(2023, 1, 1, 9, 58, 0)
    with (
        patch("datetime.datetime", wraps=dt.datetime) as mock_dt,
        patch("ib_async.util._fillDate") as mock_util_fillDate,
    ):
        mock_dt.now.return_value = start_dt
        mock_util_fillDate.side_effect = lambda t: (
            dt.datetime(2023, 1, 1, t.hour, t.minute, t.second)
            if isinstance(t, dt.time)
            else t
        )

        start_time = dt.time(10, 0, 0)
        end_time = dt.time(10, 0, 5)
        step = 1

        expected_times = [
            dt.datetime(2023, 1, 1, 10, 0, 0),
            dt.datetime(2023, 1, 1, 10, 0, 1),
            dt.datetime(2023, 1, 1, 10, 0, 2),
            dt.datetime(2023, 1, 1, 10, 0, 3),
            dt.datetime(2023, 1, 1, 10, 0, 4),
            dt.datetime(2023, 1, 1, 10, 0, 5),
        ]

        results = list(timeRange(start_time, end_time, step))
        assert results == expected_times
        assert mock_waitUntil.call_count == len(expected_times)

    with patch("datetime.datetime", wraps=dt.datetime) as mock_dt:
        mock_dt.now.return_value = dt.datetime(2023, 1, 1, 10, 0, 2)
        with patch("ib_async.util._fillDate") as mock_util_fillDate:
            mock_util_fillDate.side_effect = lambda t: (
                dt.datetime(2023, 1, 1, t.hour, t.minute, t.second)
                if isinstance(t, dt.time)
                else t
            )
            results2 = list(timeRange(start_time, end_time, step))
            assert results2 == expected_times[2:]


@pytest.mark.asyncio
@patch("ib_async.util.waitUntilAsync", new_callable=AsyncMock)
async def test_timeRangeAsync(mock_waitUntilAsync):
    start_dt = dt.datetime(2023, 1, 1, 9, 58, 0)
    with (
        patch("datetime.datetime", wraps=dt.datetime) as mock_dt,
        patch("ib_async.util._fillDate") as mock_util_fillDate,
    ):
        mock_dt.now.return_value = start_dt
        mock_util_fillDate.side_effect = lambda t: (
            dt.datetime(2023, 1, 1, t.hour, t.minute, t.second)
            if isinstance(t, dt.time)
            else t
        )

        start_time = dt.time(10, 0, 0)
        end_time = dt.time(10, 0, 5)
        step = 1

        expected_times = [
            dt.datetime(2023, 1, 1, 10, 0, 0),
            dt.datetime(2023, 1, 1, 10, 0, 1),
            dt.datetime(2023, 1, 1, 10, 0, 2),
            dt.datetime(2023, 1, 1, 10, 0, 3),
            dt.datetime(2023, 1, 1, 10, 0, 4),
            dt.datetime(2023, 1, 1, 10, 0, 5),
        ]

        results = [t async for t in timeRangeAsync(start_time, end_time, step)]
        assert results == expected_times
        assert mock_waitUntilAsync.call_count == len(expected_times)

    with patch("datetime.datetime", wraps=dt.datetime) as mock_dt:
        mock_waitUntilAsync.reset_mock()
        mock_dt.now.return_value = dt.datetime(2023, 1, 1, 10, 0, 2)
        with patch("ib_async.util._fillDate") as mock_util_fillDate:
            mock_util_fillDate.side_effect = lambda t: (
                dt.datetime(2023, 1, 1, t.hour, t.minute, t.second)
                if isinstance(t, dt.time)
                else t
            )
            results2 = [t async for t in timeRangeAsync(start_time, end_time, step)]
            assert results2 == expected_times[2:]


@patch("pandas.DataFrame")
@patch("pandas.read_sql")
def test_df(mock_read_sql, mock_dataframe):
    mock_instance = MagicMock()
    mock_dataframe.from_records.return_value = mock_instance
    mock_instance.__getitem__.return_value = MagicMock(values=[[1, 2, 3], [4, 5, 6]])
    mock_instance.drop.return_value = mock_instance

    # Test with dataclasses
    obj1 = TestDataClass(a=1, b="one")
    obj2 = TestDataClass(a=2, b="two")

    result_df = df([obj1, obj2])
    mock_dataframe.from_records.assert_called_once()
    assert list(mock_dataframe.from_records.call_args[0][0]) == [
        (1, "one", 1.0, Decimal("1.23"), [], {}),
        (2, "two", 1.0, Decimal("1.23"), [], {}),
    ]
    assert result_df == mock_instance
    assert result_df.columns == ["a", "b", "c", "d", "e", "f"]

    mock_dataframe.reset_mock()

    # Test with list of dicts
    dict_obj1 = {"col1": 1, "col2": "a"}
    dict_obj2 = {"col1": 2, "col2": "b"}
    result_df_dict = df([dict_obj1, dict_obj2])
    mock_dataframe.from_records.assert_called_once_with(
        [{"col1": 1, "col2": "a"}, {"col1": 2, "col2": "b"}]
    )
    assert result_df_dict == mock_instance
