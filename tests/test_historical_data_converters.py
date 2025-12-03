from datetime import datetime, timezone

import pytest

from ib_async.contract import Contract, TagValue
from ib_async.objects import (
    BarData,
    HistogramData,
    HistoricalSchedule,
    HistoricalSession,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    RealTimeBar,
    TickAttribBidAsk,
    TickAttribLast,
)
from ib_async.protobuf.FundamentalsDataRequest_pb2 import (
    FundamentalsDataRequest as FundamentalsDataRequestProto,
)
from ib_async.protobuf.HeadTimestampRequest_pb2 import (
    HeadTimestampRequest as HeadTimestampRequestProto,
)
from ib_async.protobuf.HistogramDataEntry_pb2 import (
    HistogramDataEntry as HistogramDataEntryProto,
)
from ib_async.protobuf.HistogramDataRequest_pb2 import (
    HistogramDataRequest as HistogramDataRequestProto,
)
from ib_async.protobuf.HistoricalDataBar_pb2 import (
    HistoricalDataBar as HistoricalDataBarProto,
)
from ib_async.protobuf.HistoricalDataRequest_pb2 import (
    HistoricalDataRequest as HistoricalDataRequestProto,
)
from ib_async.protobuf.HistoricalSchedule_pb2 import (
    HistoricalSchedule as HistoricalScheduleProto,
)
from ib_async.protobuf.HistoricalSession_pb2 import (
    HistoricalSession as HistoricalSessionProto,
)
from ib_async.protobuf.HistoricalTick_pb2 import HistoricalTick as HistoricalTickProto
from ib_async.protobuf.HistoricalTickBidAsk_pb2 import (
    HistoricalTickBidAsk as HistoricalTickBidAskProto,
)
from ib_async.protobuf.HistoricalTickLast_pb2 import (
    HistoricalTickLast as HistoricalTickLastProto,
)
from ib_async.protobuf.HistoricalTicksRequest_pb2 import (
    HistoricalTicksRequest as HistoricalTicksRequestProto,
)
from ib_async.protobuf.RealTimeBarsRequest_pb2 import (
    RealTimeBarsRequest as RealTimeBarsRequestProto,
)
from ib_async.protobuf.RealTimeBarTick_pb2 import (
    RealTimeBarTick as RealTimeBarTickProto,
)
from ib_async.protobuf.TickAttribBidAsk_pb2 import (
    TickAttribBidAsk as TickAttribBidAskProto,
)
from ib_async.protobuf.TickAttribLast_pb2 import (
    TickAttribLast as TickAttribLastProto,
)
from ib_async.protobuf.CancelHistoricalData_pb2 import (
    CancelHistoricalData as CancelHistoricalDataProto,
)
from ib_async.protobuf_converters.historical_data_converters import (
    createBarData,
    createBarDataList,
    createFundamentalsDataRequestProto,
    createHeadTimestampRequestProto,
    createHistogramDataEntry,
    createHistogramDataRequestProto,
    createHistoricalDataRequestProto,
    createHistoricalSchedule,
    createHistoricalTick,
    createHistoricalTickBidAsk,
    createHistoricalTickLast,
    createHistoricalTicksRequestProto,
    createRealTimeBarsRequestProto,
    createRealTimeBarTick,
    fillTagValueList,
    createCancelHistoricalDataProto,
)


class TestHistoricalDataConverters:
    def test_createHeadTimestampRequestProto(self):
        contract = Contract(symbol="AAPL", secType="STK")
        proto = createHeadTimestampRequestProto(1, contract, "TRADES", True, 1)
        assert isinstance(proto, HeadTimestampRequestProto)
        assert proto.reqId == 1
        assert proto.contract.symbol == "AAPL"
        assert proto.whatToShow == "TRADES"
        assert proto.useRTH is True
        assert proto.formatDate == 1

    def test_fillTagValueList(self):
        tag_values = [TagValue("tag1", "val1"), TagValue("tag2", "val2")]
        proto_map: dict[str, str] = {}
        fillTagValueList(tag_values, proto_map)
        assert proto_map == {"tag1": "val1", "tag2": "val2"}

    def test_createHistoricalDataRequestProto(self):
        contract = Contract(symbol="TSLA", secType="STK")
        proto = createHistoricalDataRequestProto(
            2,
            contract,
            "20250101 12:00:00",
            "1 D",
            "1 min",
            "TRADES",
            True,
            1,
            False,
            [],
        )
        assert isinstance(proto, HistoricalDataRequestProto)
        assert proto.reqId == 2
        assert proto.contract.symbol == "TSLA"
        assert proto.endDateTime == "20250101 12:00:00"
        assert proto.duration == "1 D"
        assert proto.barSizeSetting == "1 min"
        assert proto.whatToShow == "TRADES"
        assert proto.useRTH is True
        assert proto.formatDate == 1
        assert proto.keepUpToDate is False

    def test_createRealTimeBarsRequestProto(self):
        contract = Contract(symbol="GOOG", secType="STK")
        proto = createRealTimeBarsRequestProto(3, contract, 5, "TRADES", True, [])
        assert isinstance(proto, RealTimeBarsRequestProto)
        assert proto.reqId == 3
        assert proto.contract.symbol == "GOOG"
        assert proto.barSize == 5
        assert proto.whatToShow == "TRADES"
        assert proto.useRTH is True

    def test_createBarData(self):
        bar_proto = HistoricalDataBarProto(
            date="2025-01-01 10:00:00",
            open=100.0,
            high=102.0,
            low=99.0,
            close=101.0,
            volume="1000",
            WAP="100.5",
            barCount=50,
        )
        bar = createBarData(bar_proto)
        assert isinstance(bar, BarData)
        assert bar.date == datetime(2025, 1, 1, 10, 0)
        assert bar.open == 100.0
        assert bar.high == 102.0
        assert bar.low == 99.0
        assert bar.close == 101.0
        assert bar.volume == 1000
        assert bar.average == 100.5
        assert bar.barCount == 50

    def test_createBarDataList(self):
        bar_proto1 = HistoricalDataBarProto(
            date="2025-01-01 10:00:00",
            open=100,
            high=102,
            low=99,
            close=101,
            volume="1000",
            WAP="100.5",
            barCount=50,
        )
        bar_proto2 = HistoricalDataBarProto(
            date="2025-01-01 10:05:00",
            open=101,
            high=103,
            low=100,
            close=102,
            volume="1000",
            WAP="101.5",
            barCount=50,
        )
        bars = createBarDataList([bar_proto1, bar_proto2])
        assert len(bars) == 2
        assert bars[0].open == 100
        assert bars[1].open == 101

    def test_createHistoricalTicksRequestProto(self):
        contract = Contract(symbol="MSFT", secType="STK")
        proto = createHistoricalTicksRequestProto(
            4,
            contract,
            "20250101 10:00:00",
            "20250101 10:05:00",
            100,
            "TRADES",
            True,
            False,
            [],
        )
        assert isinstance(proto, HistoricalTicksRequestProto)
        assert proto.reqId == 4
        assert proto.contract.symbol == "MSFT"
        assert proto.startDateTime == "20250101 10:00:00"
        assert proto.endDateTime == "20250101 10:05:00"
        assert proto.numberOfTicks == 100
        assert proto.whatToShow == "TRADES"
        assert proto.useRTH is True
        assert proto.ignoreSize is False

    def test_createHistoricalTick(self):
        ts = int(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
        tick_proto = HistoricalTickProto(time=ts, price=150.0, size="10")
        tick = createHistoricalTick(tick_proto, timezone.utc)
        assert isinstance(tick, HistoricalTick)
        assert tick.time == datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert tick.price == 150.0
        assert tick.size == 10

    def test_createHistoricalTickBidAsk(self):
        ts = int(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
        attrib_proto = TickAttribBidAskProto(bidPastLow=True, askPastHigh=False)
        tick_proto = HistoricalTickBidAskProto(
            time=ts,
            tickAttribBidAsk=attrib_proto,
            priceBid=149.9,
            priceAsk=150.1,
            sizeBid="5",
            sizeAsk="8",
        )
        tick = createHistoricalTickBidAsk(tick_proto, timezone.utc)
        assert isinstance(tick, HistoricalTickBidAsk)
        assert tick.time == datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert tick.tickAttribBidAsk.bidPastLow is True
        assert tick.priceBid == 149.9
        assert tick.sizeAsk == 8

    def test_createHistoricalTickLast(self):
        ts = int(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
        attrib_proto = TickAttribLastProto(pastLimit=False, unreported=True)
        tick_proto = HistoricalTickLastProto(
            time=ts,
            tickAttribLast=attrib_proto,
            price=150.0,
            size="12",
            exchange="NYSE",
            specialConditions="C",
        )
        tick = createHistoricalTickLast(tick_proto, timezone.utc)
        assert isinstance(tick, HistoricalTickLast)
        assert tick.time == datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert tick.tickAttribLast.unreported is True
        assert tick.price == 150.0
        assert tick.size == 12
        assert tick.exchange == "NYSE"
        assert tick.specialConditions == "C"

    def test_createHistogramDataRequestProto(self):
        contract = Contract(symbol="AMZN", secType="STK")
        proto = createHistogramDataRequestProto(5, contract, True, "1 week")
        assert isinstance(proto, HistogramDataRequestProto)
        assert proto.reqId == 5
        assert proto.contract.symbol == "AMZN"
        assert proto.useRTH is True
        assert proto.timePeriod == "1 week"

    def test_createHistogramDataEntry(self):
        entry_proto = HistogramDataEntryProto(price=2000.0, size="500")
        entry = createHistogramDataEntry(entry_proto)
        assert isinstance(entry, HistogramData)
        assert entry.price == 2000.0
        assert entry.count == 500

    def test_createHistoricalSchedule(self):
        session_proto = HistoricalSessionProto(
            startDateTime="20250101:090000",
            endDateTime="20250101:160000",
            refDate="20250101",
        )
        schedule_proto = HistoricalScheduleProto(
            startDateTime="20250101",
            endDateTime="20250131",
            timeZone="EST",
            historicalSessions=[session_proto],
        )
        schedule = createHistoricalSchedule(schedule_proto)
        assert isinstance(schedule, HistoricalSchedule)
        assert schedule.startDateTime == "20250101"
        assert schedule.endDateTime == "20250131"
        assert schedule.timeZone == "EST"
        assert len(schedule.sessions) == 1
        assert schedule.sessions[0].refDate == "20250101"
        assert schedule.sessions[0].startDateTime == "20250101:090000"
        assert schedule.sessions[0].endDateTime == "20250101:160000"

    def test_createRealTimeBarTick(self):
        ts = int(datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc).timestamp())
        bar_proto = RealTimeBarTickProto(
            time=ts,
            open=100,
            high=102,
            low=99,
            close=101,
            volume="1000",
            WAP="100.5",
            count=50,
        )
        bar = createRealTimeBarTick(bar_proto, timezone.utc)
        assert isinstance(bar, RealTimeBar)
        assert bar.time == datetime(2025, 1, 1, 10, 0, tzinfo=timezone.utc)
        assert bar.open_ == 100
        assert bar.volume == 1000

    def test_createFundamentalsDataRequestProto(self):
        contract = Contract(symbol="IBM", secType="STK")
        proto = createFundamentalsDataRequestProto(6, contract, "ReportSnapshot", [])
        assert isinstance(proto, FundamentalsDataRequestProto)
        assert proto.reqId == 6
        assert proto.contract.symbol == "IBM"
        assert proto.reportType == "ReportSnapshot"

    def test_createCancelHistoricalDataProto(self):
        proto = createCancelHistoricalDataProto(1)
        assert isinstance(proto, CancelHistoricalDataProto)
        assert proto.reqId == 1
