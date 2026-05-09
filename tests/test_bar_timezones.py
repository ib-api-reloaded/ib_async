from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import ib_async as ibi
from ib_async._requests import ReqIdKey


def test_realtime_bars_use_configured_default_timezone():
    from ib_async._subscriptions import RealTimeBarsSub

    eastern = ZoneInfo("America/New_York")
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=eastern))
    bars = ibi.RealTimeBarList()
    contract = ibi.Stock("ABC", "SMART", "USD", conId=1)
    bars.contract = contract
    ib.wrapper.subscriptions.add(RealTimeBarsSub(reqId=1, contract=contract, bars=bars))

    timestamp = int(datetime(2025, 10, 20, 15, 0, 5, tzinfo=UTC).timestamp())
    ib.wrapper.realtimeBar(1, timestamp, 1.0, 2.0, 0.5, 1.5, 10, 1.2, 3)

    assert bars[-1].time == datetime(2025, 10, 20, 11, 0, 5, tzinfo=eastern)


def test_historical_data_with_explicit_timezone_uses_default_timezone():
    eastern = ZoneInfo("America/New_York")
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=eastern))
    req, _ = ib.wrapper.requests.open(ReqIdKey(1))
    future = req.future

    bar = ibi.BarData(date="20251020 15:00:00 UTC")
    ib.wrapper.historicalData(1, bar)
    ib.wrapper.historicalDataEnd(1, "", "")

    assert future.result()[-1].date == datetime(2025, 10, 20, 11, 0, 0, tzinfo=eastern)


def test_historical_data_without_timezone_uses_default_timezone():
    eastern = ZoneInfo("America/New_York")
    ib = ibi.IB(defaults=ibi.IBDefaults(timezone=eastern))
    req, _ = ib.wrapper.requests.open(ReqIdKey(1))
    future = req.future

    bar = ibi.BarData(date="20251020  15:00:00")
    ib.wrapper.historicalData(1, bar)
    ib.wrapper.historicalDataEnd(1, "", "")

    assert future.result()[-1].date == datetime(2025, 10, 20, 15, 0, 0, tzinfo=eastern)
