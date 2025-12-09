
import asyncio
import datetime as dt
import enum
import logging
import math
import sys
import unittest
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import AsyncMock, MagicMock, call, patch

from ib_async.util import (
    EPOCH,
    NO_VALID_ID,
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


class TestUtil(unittest.TestCase):

    def setUp(self):
        # Reset globalErrorEvent before each test
        globalErrorEvent.clear()

    def test_dataclassAsDict(self):
        obj = TestDataClass(a=1, b="test")
        expected = {"a": 1, "b": "test", "c": 1.0, "d": Decimal("1.23"), "e": [], "f": {}}
        self.assertEqual(dataclassAsDict(obj), expected)

        with self.assertRaises(TypeError):
            dataclassAsDict(123)

    def test_dataclassAsTuple(self):
        obj = TestDataClass(a=1, b="test")
        expected = (1, "test", 1.0, Decimal("1.23"), [], {})
        self.assertEqual(dataclassAsTuple(obj), expected)

        with self.assertRaises(TypeError):
            dataclassAsTuple("not_a_dataclass")

    def test_dataclassNonDefaults(self):
        obj1 = TestDataClass(a=1)
        self.assertEqual(dataclassNonDefaults(obj1), {"a": 1})

        obj2 = TestDataClass(a=1, b="non-default", c=2.0, d=Decimal("3.45"))
        expected2 = {"a": 1, "b": "non-default", "c": 2.0, "d": Decimal("3.45")}
        self.assertEqual(dataclassNonDefaults(obj2), expected2)

        obj3 = TestDataClass(a=1, e=[1,2])
        self.assertEqual(dataclassNonDefaults(obj3), {"a":1, "e":[1,2]})

        with self.assertRaises(TypeError):
            dataclassNonDefaults({"a": 1})

    def test_dataclassUpdate(self):
        obj = TestDataClass(a=1, b="original")
        src_obj = AnotherTestDataClass(x=20, y="updated")
        
        # Test update from kwargs
        dataclassUpdate(obj, a=5, b="new")
        self.assertEqual(obj.a, 5)
        self.assertEqual(obj.b, "new")

        # Test update from another dataclass (only matching fields)
        dataclassUpdate(obj, src_obj, a=100) # src_obj doesn't have 'a' or 'b'
        self.assertEqual(obj.a, 100)
        self.assertEqual(obj.b, "new") # Should remain unchanged as src_obj doesn't have 'b'
        self.assertEqual(obj.c, 1.0) # Should remain unchanged as src_obj doesn't have 'c'

        # Test update from dataclass where fields match
        @dataclass
        class MatchingSrc:
            a: int = 0
            c: float = 0.0
        match_src = MatchingSrc(a=99, c=9.9)
        dataclassUpdate(obj, match_src)
        self.assertEqual(obj.a, 99)
        self.assertEqual(obj.c, 9.9)
        self.assertEqual(obj.b, "new")

        with self.assertRaises(TypeError):
            dataclassUpdate("not_a_dataclass", a=1)

    def test_dataclassRepr(self):
        obj1 = TestDataClass(a=1)
        self.assertEqual(dataclassRepr(obj1), "TestDataClass(a=1)")

        obj2 = TestDataClass(a=1, b="custom")
        self.assertEqual(dataclassRepr(obj2), "TestDataClass(a=1, b='custom')")

        obj3 = TestDataClass(a=1, c=2.5)
        self.assertEqual(dataclassRepr(obj3), "TestDataClass(a=1, c=2.5)")

        obj4 = TestDataClass(a=1, e=[1,2,3])
        self.assertEqual(dataclassRepr(obj4), "TestDataClass(a=1, e=[1, 2, 3])")

    def test_isnamedtupleinstance(self):
        from collections import namedtuple
        Point = namedtuple("Point", "x y")
        p = Point(1, 2)
        self.assertTrue(isnamedtupleinstance(p))
        self.assertFalse(isnamedtupleinstance((1, 2)))
        self.assertFalse(isnamedtupleinstance([1, 2]))
        self.assertFalse(isnamedtupleinstance(TestDataClass(a=1)))

    def test_tree(self):
        # Basic types
        self.assertEqual(tree(1), 1)
        self.assertEqual(tree("hello"), "hello")
        self.assertEqual(tree(True), True)
        self.assertEqual(tree(1.5), 1.5)
        self.assertEqual(tree(b"bytes"), b"bytes")

        # Datetime/date
        d = dt.date(2023, 1, 1)
        self.assertEqual(tree(d), "2023-01-01")
        dt_obj = dt.datetime(2023, 1, 1, 10, 30, 0)
        self.assertEqual(tree(dt_obj), "2023-01-01T10:30:00")

        # Dict
        self.assertEqual(tree({"a": 1, "b": "c"}), {"a": 1, "b": "c"})
        
        # Namedtuple
        from collections import namedtuple
        Point = namedtuple("Point", "x y")
        p = Point(1, "two")
        self.assertEqual(tree(p), {"x": 1, "y": "two"})

        # List, tuple, set
        self.assertEqual(tree([1, 2, "a"]), [1, 2, "a"])
        self.assertEqual(tree((1, 2, "a")), [1, 2, "a"])
        self.assertEqual(tree({1, 2, 3}), [1, 2, 3]) # Note: sets become lists, order not guaranteed

        # Dataclass
        obj = TestDataClass(a=1, b="custom")
        expected_dataclass_tree = {"TestDataClass": {"a": 1, "b": "custom"}}
        self.assertEqual(tree(obj), expected_dataclass_tree)

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
        self.assertEqual(tree(nested_obj), expected_nested_tree)

        # Other objects
        class CustomClass:
            def __str__(self):
                return "Custom"
        self.assertEqual(tree(CustomClass()), "Custom")

    def test_isNan(self):
        self.assertTrue(isNan(float("nan")))
        self.assertFalse(isNan(1.0))
        self.assertFalse(isNan(0.0))
        self.assertFalse(isNan(float("inf")))
        self.assertFalse(isNan(-1.0))

    def test_formatSI(self):
        self.assertEqual(formatSI(0), "0.00 ")
        self.assertEqual(formatSI(1), "1.00 ")
        self.assertEqual(formatSI(10), "10.0 ")
        self.assertEqual(formatSI(100), "100 ")
        self.assertEqual(formatSI(1000), "1.00 k")
        self.assertEqual(formatSI(1234), "1.23 k")
        self.assertEqual(formatSI(1234567), "1.23 M")
        self.assertEqual(formatSI(0.1), "100 m")
        self.assertEqual(formatSI(0.01), "10.0 m")
        self.assertEqual(formatSI(0.001), "1.00 m")
        self.assertEqual(formatSI(0.000000001), "1.00 n")
        self.assertEqual(formatSI(-1234), "-1.23 k")
        self.assertEqual(formatSI(1000000000000000000000000.0), "1.00 Y") # Yotta
        self.assertEqual(formatSI(0.000000000000000000000001), "1.00 y") # yocto
        self.assertEqual(formatSI(0.0000000000000000000000001), "0.00 ") # smaller than yocto

    @patch('builtins.print')
    @patch('time.time', side_effect=[0, 1.5])
    def test_timeit(self, mock_time, mock_print):
        with timeit("Test Run"):
            pass
        mock_print.assert_called_once_with("Test Run took 1.50 s")

    @patch('builtins.print')
    @patch('time.time', side_effect=[0, 12345.678])
    def test_timeit_format_si(self, mock_time, mock_print):
        with timeit("Long Run"):
            pass
        mock_print.assert_called_once_with("Long Run took 12.3 k s")

    def test_formatIBDatetime(self):
        self.assertEqual(formatIBDatetime(None), "")
        
        # Datetime
        dt_obj = dt.datetime(2023, 1, 15, 10, 30, 45, tzinfo=dt.timezone.utc)
        self.assertEqual(formatIBDatetime(dt_obj), "20230115 10:30:45 UTC")

        dt_obj_ny = dt.datetime(2023, 1, 15, 5, 30, 45, tzinfo=dt.timezone(dt.timedelta(hours=-5))) # EST
        # Should convert to UTC: 2023-01-15 10:30:45 UTC
        self.assertEqual(formatIBDatetime(dt_obj_ny), "20230115 10:30:45 UTC")

        # Date
        date_obj = dt.date(2023, 2, 1)
        # Should convert to end of day UTC: 2023-02-01 23:59:59 UTC
        self.assertEqual(formatIBDatetime(date_obj), "20230201 23:59:59 UTC")

        # String (pass-through)
        self.assertEqual(formatIBDatetime("20230301 12:00:00"), "20230301 12:00:00")

    @patch('ib_async.util.ZoneInfo', side_effect=lambda x: dt.timezone.utc if x == 'Europe/Amsterdam' else dt.timezone.utc) # Mock ZoneInfo
    def test_parseIBDatetime(self, MockZoneInfo):
        from zoneinfo import ZoneInfo as RealZoneInfo  # For direct comparison

        # YYYYmmdd
        self.assertEqual(parseIBDatetime("20230101"), dt.date(2023, 1, 1))

        # Timestamp as string
        timestamp_str = str(int(dt.datetime(2023, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc).timestamp()))
        self.assertEqual(parseIBDatetime(timestamp_str), dt.datetime(2023, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc))

        # YYYYmmdd HH:MM:SS Europe/Amsterdam
        with patch('ib_async.util.ZoneInfo', side_effect=lambda x: RealZoneInfo('Europe/Amsterdam') if x == 'Europe/Amsterdam' else dt.timezone.utc):
            result = parseIBDatetime("20221125 10:00:00 Europe/Amsterdam")
            expected = dt.datetime(2022, 11, 25, 10, 0, 0, tzinfo=RealZoneInfo('Europe/Amsterdam'))
            self.assertEqual(result, expected)

        # YYYYmmdd  HH:MM:SS
        self.assertEqual(parseIBDatetime("20230101  12:30:45"), dt.datetime(2023, 1, 1, 12, 30, 45))

        # YYYY-mm-dd HH:MM:SS.0
        self.assertEqual(parseIBDatetime("2023-01-01 12:30:45.0"), dt.datetime(2023, 1, 1, 12, 30, 45))
        self.assertEqual(parseIBDatetime("2023-01-01 12:30:45"), dt.datetime(2023, 1, 1, 12, 30, 45))

    def test_parseIBTimeStamp(self):
        timestamp = 1672531200 # 2023-01-01 00:00:00 UTC
        expected_dt = dt.datetime(2023, 1, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(parseIBTimeStamp(timestamp), expected_dt)

        # With different timezone
        ny_tz = dt.timezone(dt.timedelta(hours=-5))
        expected_dt_ny = dt.datetime(2023, 1, 1, 0, 0, 0, tzinfo=ny_tz)
        self.assertEqual(parseIBTimeStamp(timestamp, tz=ny_tz), expected_dt_ny)

    def test_decimalMaxString(self):
        self.assertEqual(decimalMaxString(Decimal("123.45")), "123.45")
        self.assertEqual(decimalMaxString(UNSET_DECIMAL), "")
        self.assertEqual(decimalMaxString(Decimal("0")), "0")

    def test_floatMaxString(self):
        self.assertEqual(floatMaxString(123.456789), "123.456789")
        self.assertEqual(floatMaxString(123.000000), "123")
        self.assertEqual(floatMaxString(UNSET_DOUBLE), "")
        self.assertEqual(floatMaxString(0.0), "0")
        self.assertEqual(floatMaxString(None), "")

    def test_getEnumTypeFromString(self):
        self.assertEqual(getEnumTypeFromString(TestEnum, "A"), TestEnum.ALPHA)
        self.assertEqual(getEnumTypeFromString(TestEnum, "B"), TestEnum.BETA)
        self.assertEqual(getEnumTypeFromString(TestEnum, "C"), TestEnum.GAMMA)
        # If not found, should return the first enum member
        self.assertEqual(getEnumTypeFromString(TestEnum, "X"), TestEnum.ALPHA)

    def test_listOfValues(self):
        expected_list = [TestEnum.ALPHA, TestEnum.BETA, TestEnum.GAMMA]
        self.assertEqual(listOfValues(TestEnum), expected_list)

    def test_isValidIntValue(self):
        self.assertTrue(isValidIntValue(10))
        self.assertTrue(isValidIntValue(0))
        self.assertFalse(isValidIntValue(UNSET_INTEGER))
        self.assertTrue(isValidIntValue(-1))

    def test_quantize_decimals_decorator(self):
        @quantize_decimals(places=2)
        @dataclass
        class MyResult:
            price: Decimal
            amount: Decimal
            name: str
            not_decimal: float = 1.234

        res = MyResult(price=Decimal("12.3456"), amount=Decimal("7.891"), name="Test")
        self.assertEqual(res.price, Decimal("12.35"))
        self.assertEqual(res.amount, Decimal("7.89"))
        self.assertEqual(res.name, "Test")
        self.assertEqual(res.not_decimal, 1.234) # float should not be quantized

        # Test with different places and rounding
        @quantize_decimals(places=0, rounding=ROUND_HALF_UP)
        @dataclass
        class MyIntResult:
            count: Decimal

        res_int = MyIntResult(count=Decimal("5.6"))
        self.assertEqual(res_int.count, Decimal("6"))

        # Test with a function that returns a non-dataclass
        @quantize_decimals(places=2)
        def return_non_dataclass():
            return "just a string"

        self.assertEqual(return_non_dataclass(), "just a string")

        # Test with a function that returns None
        @quantize_decimals(places=2)
        def return_none():
            return None
        self.assertIsNone(return_none())


class TestUtilAsync(unittest.IsolatedAsyncioTestCase):

    @patch('asyncio.get_running_loop')
    def test_getLoop_running(self, mock_get_running_loop):
        mock_loop = MagicMock()
        mock_get_running_loop.return_value = mock_loop
        self.assertEqual(getLoop(), mock_loop)
        mock_get_running_loop.assert_called_once()

    @patch('asyncio.new_event_loop')
    @patch('asyncio.set_event_loop')
    @patch('asyncio.get_running_loop', side_effect=RuntimeError)
    def test_getLoop_new(self, mock_get_running_loop, mock_set_event_loop, mock_new_event_loop):
        mock_loop = MagicMock()
        mock_new_event_loop.return_value = mock_loop
        self.assertEqual(getLoop(), mock_loop)
        mock_get_running_loop.assert_called_once()
        mock_new_event_loop.assert_called_once()
        mock_set_event_loop.assert_called_once_with(mock_loop)

    @patch('nest_asyncio.apply')
    def test_patchAsyncio(self, mock_apply):
        patchAsyncio()
        mock_apply.assert_called_once()

    @patch('ib_async.util.getLoop')
    async def test_run_no_awaitables(self, mock_getLoop):
        mock_loop = AsyncMock()
        mock_loop.is_running.return_value = False
        mock_getLoop.return_value = mock_loop
        
        with patch('asyncio.all_tasks', return_value=[]):
            run()
            mock_loop.run_forever.assert_called_once()
            # If no tasks, no cancellation attempts
            mock_loop.run_until_complete.assert_not_called()

        mock_loop.reset_mock()
        mock_loop.is_running.return_value = True
        run() # Should do nothing if loop is already running
        mock_loop.run_forever.assert_not_called()

    @patch('ib_async.util.getLoop')
    @patch('asyncio.gather', new_callable=AsyncMock)
    @patch('asyncio.ensure_future')
    @patch('asyncio.wait_for', new_callable=AsyncMock)
    async def test_run_with_awaitables(self, mock_wait_for, mock_ensure_future, mock_gather, mock_getLoop):
        mock_loop = MagicMock()
        mock_getLoop.return_value = mock_loop
        mock_task = MagicMock()
        mock_ensure_future.return_value = mock_task
        mock_wait_for.return_value = MagicMock() # The future that wait_for returns

        # Test single awaitable
        awaitable = AsyncMock(return_value="result1")
        mock_loop.run_until_complete.return_value = "result1"
        result = run(awaitable)
        self.assertEqual(result, "result1")
        mock_gather.assert_called_once_with(awaitable) # gather is called even for single
        mock_ensure_future.assert_called_once()
        mock_loop.run_until_complete.assert_called_once_with(mock_task)
        mock_wait_for.assert_called_once_with(mock_gather.return_value, None)
        mock_getLoop.assert_called()

        mock_gather.reset_mock()
        mock_ensure_future.reset_mock()
        mock_loop.run_until_complete.reset_mock()
        mock_wait_for.reset_mock()

        # Test multiple awaitables
        awaitable1 = AsyncMock(return_value="result1")
        awaitable2 = AsyncMock(return_value="result2")
        mock_loop.run_until_complete.return_value = ["result1", "result2"]
        result = run(awaitable1, awaitable2)
        self.assertEqual(result, ["result1", "result2"])
        mock_gather.assert_called_once_with(awaitable1, awaitable2)
        mock_ensure_future.assert_called_once()
        mock_loop.run_until_complete.assert_called_once_with(mock_task)
        mock_wait_for.assert_called_once_with(mock_gather.return_value, None)

        mock_gather.reset_mock()
        mock_ensure_future.reset_mock()
        mock_loop.run_until_complete.reset_mock()
        mock_wait_for.reset_mock()
        
        # Test with timeout
        awaitable = AsyncMock(return_value="result_timeout")
        mock_loop.run_until_complete.return_value = "result_timeout"
        result = run(awaitable, timeout=5.0)
        self.assertEqual(result, "result_timeout")
        mock_wait_for.assert_called_once_with(mock_gather.return_value, 5.0)

    @patch('ib_async.util.getLoop')
    @patch('asyncio.gather', new_callable=AsyncMock)
    @patch('asyncio.ensure_future')
    @patch('asyncio.all_tasks', return_value=[MagicMock()]) # Simulate active tasks
    async def test_run_cancel_pending_tasks(self, mock_all_tasks, mock_ensure_future, mock_gather, mock_getLoop):
        mock_loop = MagicMock()
        mock_loop.is_running.return_value = False
        mock_getLoop.return_value = mock_loop
        
        # Mock gather for cancellation
        mock_cancel_future = MagicMock()
        mock_gather.return_value = mock_cancel_future
        mock_loop.run_until_complete.side_effect = [asyncio.CancelledError(), None] # First for gather.cancel, second for normal run
        
        run() # Call without awaitables, should try to cancel all tasks
        mock_loop.run_forever.assert_called_once()
        mock_all_tasks.assert_called_once()
        mock_gather.assert_called_once_with(*mock_all_tasks.return_value)
        mock_cancel_future.cancel.assert_called_once()
        mock_loop.run_until_complete.assert_has_calls([call(mock_cancel_future)])

    @patch('ib_async.util.getLoop')
    @patch('asyncio.sleep')
    async def test_sleep(self, mock_sleep, mock_getLoop):
        mock_loop = MagicMock()
        mock_getLoop.return_value = mock_loop
        mock_sleep.return_value = None # asyncio.sleep is an awaitable that returns None

        result = sleep(0.1)
        self.assertTrue(result)
        mock_sleep.assert_awaited_once_with(0.1)

    def test_fillDate(self):
        today = dt.date.today()

        # dt.time input
        time_obj = dt.time(10, 30, 0)
        expected_dt = dt.datetime(today.year, today.month, today.day, 10, 30, 0)
        self.assertEqual(_fillDate(time_obj), expected_dt)

        # dt.datetime input
        dt_obj = dt.datetime(2023, 1, 1, 11, 0, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(_fillDate(dt_obj), dt_obj)

    @patch('ib_async.util.getLoop')
    def test_schedule(self, mock_getLoop):
        mock_loop = MagicMock()
        mock_getLoop.return_value = mock_loop
        callback = MagicMock()
        
        now = dt.datetime.now()
        target_time = now + dt.timedelta(seconds=10)
        
        schedule(target_time, callback, 1, 2, "test")
        
        # Check if call_later is called with approximately 10 seconds delay
        # We need to account for tiny time differences during test execution
        mock_loop.call_later.assert_called_once()
        args, _ = mock_loop.call_later.call_args
        delay = args[0]
        self.assertAlmostEqual(delay, 10, delta=0.1)
        self.assertEqual(args[1], callback)
        self.assertEqual(args[2:], (1, 2, "test"))

        # Test with dt.time
        mock_loop.reset_mock()
        time_obj = dt.time(now.hour, (now.minute + 1) % 60, now.second)
        schedule(time_obj, callback)
        mock_loop.call_later.assert_called_once()

    @patch('ib_async.util.run')
    @patch('datetime.datetime')
    def test_waitUntil(self, mock_datetime, mock_run):
        # Mock datetime.datetime.now()
        mock_now = dt.datetime(2023, 1, 1, 10, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: dt.datetime(*args, **kw) # Allow normal datetime creation
        mock_datetime.today.return_value = dt.date(2023, 1, 1)

        target_time = dt.datetime(2023, 1, 1, 10, 0, 5)
        waitUntil(target_time)
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        # Expecting asyncio.sleep(5)
        self.assertEqual(args[0].__name__, "sleep") # Accessing the coroutine object
        self.assertEqual(args[0].cr_code.co_name, "sleep") # Verify it's the sleep coroutine

        mock_run.reset_mock()
        # Test with dt.time
        target_time_obj = dt.time(10, 0, 10)
        waitUntil(target_time_obj)
        mock_run.assert_called_once()
        args, _ = mock_run.call_args
        # Expecting asyncio.sleep(10)
        self.assertEqual(args[0].__name__, "sleep")
        self.assertEqual(args[0].cr_code.co_name, "sleep")


    @patch('asyncio.sleep', new_callable=AsyncMock)
    @patch('datetime.datetime')
    async def test_waitUntilAsync(self, mock_datetime, mock_sleep):
        mock_now = dt.datetime(2023, 1, 1, 10, 0, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: dt.datetime(*args, **kw)
        mock_datetime.today.return_value = dt.date(2023, 1, 1)

        target_time = dt.datetime(2023, 1, 1, 10, 0, 5)
        result = await waitUntilAsync(target_time)
        self.assertTrue(result)
        mock_sleep.assert_awaited_once_with(5)

        mock_sleep.reset_mock()
        target_time_obj = dt.time(10, 0, 10)
        result = await waitUntilAsync(target_time_obj)
        self.assertTrue(result)
        mock_sleep.assert_awaited_once_with(10)

    @patch('ib_async.util.waitUntil')
    @patch('datetime.datetime')
    def test_timeRange(self, mock_datetime, mock_waitUntil):
        mock_now = dt.datetime(2023, 1, 1, 9, 58, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: dt.datetime(*args, **kw)
        mock_datetime.today.return_value = dt.date(2023, 1, 1)
        
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
        
        # Collect results from the generator
        results = list(timeRange(start_time, end_time, step))

        self.assertEqual(results, expected_times)
        self.assertEqual(mock_waitUntil.call_count, len(expected_times))
        
        # Test with start time already passed
        mock_datetime.now.return_value = dt.datetime(2023, 1, 1, 10, 0, 2)
        results2 = list(timeRange(start_time, end_time, step))
        self.assertEqual(results2, expected_times[2:])


    @patch('ib_async.util.waitUntilAsync')
    @patch('datetime.datetime')
    async def test_timeRangeAsync(self, mock_datetime, mock_waitUntilAsync):
        mock_now = dt.datetime(2023, 1, 1, 9, 58, 0)
        mock_datetime.now.return_value = mock_now
        mock_datetime.side_effect = lambda *args, **kw: dt.datetime(*args, **kw)
        mock_datetime.today.return_value = dt.date(2023, 1, 1)

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

        results = []
        async for t in timeRangeAsync(start_time, end_time, step):
            results.append(t)
        
        self.assertEqual(results, expected_times)
        self.assertEqual(mock_waitUntilAsync.call_count, len(expected_times))

        # Test with start time already passed
        mock_datetime.now.return_value = dt.datetime(2023, 1, 1, 10, 0, 2)
        results2 = []
        async for t in timeRangeAsync(start_time, end_time, step):
            results2.append(t)
        self.assertEqual(results2, expected_times[2:])

    @patch('pandas.DataFrame')
    @patch('pandas.read_sql') # Mocking to avoid actual DB interaction
    def test_df(self, mock_read_sql, mock_dataframe):
        # Mock pandas DataFrame creation
        mock_instance = MagicMock()
        mock_dataframe.from_records.return_value = mock_instance
        mock_instance.__getitem__.return_value = MagicMock(values=[[1,2,3], [4,5,6]])
        mock_instance.drop.return_value = mock_instance

        # Test with dataclasses
        obj1 = TestDataClass(a=1, b="one")
        obj2 = TestDataClass(a=2, b="two")
        
        result_df = df([obj1, obj2])
        mock_dataframe.from_records.assert_called_once()
        self.assertEqual(mock_dataframe.from_records.call_args[0][0], [(1, 'one', 1.0, Decimal('1.23'), [], {}), (2, 'two', 1.0, Decimal('1.23'), [], {})])
        self.assertEqual(result_df, mock_instance)
        self.assertEqual(result_df.columns, ['a', 'b', 'c', 'd', 'e', 'f'])

        mock_dataframe.reset_mock()
        # Test with DynamicObject (mocked)
        class DynamicObjectMock:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
        
        dyn_obj1 = DynamicObjectMock(id=1, name="Alpha")
        dyn_obj2 = DynamicObjectMock(id=2, name="Beta")
        
        result_df_dyn = df([dyn_obj1, dyn_obj2])
        mock_dataframe.from_records.assert_called_once_with([{'id': 1, 'name': 'Alpha'}, {'id': 2, 'name': 'Beta'}])
        self.assertEqual(result_df_dyn, mock_instance)

        mock_dataframe.reset_mock()
        # Test with namedtuple
        from collections import namedtuple
        NamedTupleMock = namedtuple("NamedTupleMock", "field1 field2")
        nt_obj1 = NamedTupleMock(10, "ten")
        nt_obj2 = NamedTupleMock(20, "twenty")

        result_df_nt = df([nt_obj1, nt_obj2])
        mock_dataframe.from_records.assert_called_once()
        self.assertEqual(result_df_nt.columns, ('field1', 'field2'))
        self.assertEqual(result_df_nt, mock_instance)

        mock_dataframe.reset_mock()
        # Test with list of dicts
        dict_obj1 = {"col1": 1, "col2": "a"}
        dict_obj2 = {"col1": 2, "col2": "b"}
        result_df_dict = df([dict_obj1, dict_obj2])
        mock_dataframe.from_records.assert_called_once_with([{'col1': 1, 'col2': 'a'}, {'col1': 2, 'col2': 'b'}])
        self.assertEqual(result_df_dict, mock_instance)
        
        mock_dataframe.reset_mock()
        # Test with labels
        obj = TestDataClass(a=1, b="one")
        result_df_labels = df([obj], labels=["a"])
        mock_instance.drop.assert_called_once_with(
            ['b', 'c', 'd', 'e', 'f'], axis=1
        )
        self.assertEqual(result_df_labels, mock_instance)

        mock_dataframe.reset_mock()
        # Test empty list
        self.assertIsNone(df([]))

# To run tests
if __name__ == "__main__":
    unittest.main()
