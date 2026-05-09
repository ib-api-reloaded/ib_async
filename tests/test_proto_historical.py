"""Negative-path-first tests for the historical-data protobuf converter.

Coverage:

* Empty / partial protos must produce safe-default args without raising.
* Garbage Decimal strings on ``volume`` / ``WAP`` / ``size`` lines —
  must coerce to ``None`` (BarData / RealTimeBar fields) or ``0.0``
  (HistoricalTick fields) per their respective domain types.
* Repeated-field decoders return correctly-sized lists.
* ``HistoricalSchedule`` unpacks repeated ``HistoricalSession`` slots.
* Send-side request envelopes carry every caller-supplied field
  including bool flags (``keepUpToDate``, ``useRTH``, ``ignoreSize``)
  whose proto3 default would silently swallow ``True``.
"""

from __future__ import annotations

from decimal import Decimal

import ib_async as ibi
from ib_async._pb import (
    CancelHeadTimestamp_pb2,
    CancelHistogramData_pb2,
    CancelHistoricalData_pb2,
    CancelHistoricalTicks_pb2,
    CancelRealTimeBars_pb2,
    HeadTimestamp_pb2,
    HeadTimestampRequest_pb2,
    HistogramData_pb2,
    HistogramDataRequest_pb2,
    HistoricalData_pb2,
    HistoricalDataBar_pb2,
    HistoricalDataEnd_pb2,
    HistoricalDataRequest_pb2,
    HistoricalDataUpdate_pb2,
    HistoricalSchedule_pb2,
    HistoricalTick_pb2,
    HistoricalTickBidAsk_pb2,
    HistoricalTickLast_pb2,
    HistoricalTicks_pb2,
    HistoricalTicksBidAsk_pb2,
    HistoricalTicksLast_pb2,
    HistoricalTicksRequest_pb2,
    RealTimeBarsRequest_pb2,
    RealTimeBarTick_pb2,
)
from ib_async._proto.historical import (
    createBarData,
    createCancelHeadTimestampProto,
    createCancelHistogramDataProto,
    createCancelHistoricalDataProto,
    createCancelHistoricalTicksProto,
    createCancelRealTimeBarsProto,
    createHeadTimestampArgs,
    createHeadTimestampRequestProto,
    createHistogramDataArgs,
    createHistogramDataRequestProto,
    createHistoricalDataEndArgs,
    createHistoricalDataRequestProto,
    createHistoricalDataUpdateArgs,
    createHistoricalScheduleArgs,
    createHistoricalTick,
    createHistoricalTickBidAsk,
    createHistoricalTickLast,
    createHistoricalTicksArgs,
    createHistoricalTicksBidAskArgs,
    createHistoricalTicksLastArgs,
    createHistoricalTicksRequestProto,
    createRealtimeBarArgs,
    createRealTimeBarsRequestProto,
    iterHistoricalDataBars,
)

# ---------------------------------------------------------------------------
# BarData / HistoricalDataBar
# ---------------------------------------------------------------------------


def test_bar_data_empty_proto_yields_all_none_numerics():
    bar = createBarData(HistoricalDataBar_pb2.HistoricalDataBar())
    assert bar.open is None
    assert bar.high is None
    assert bar.low is None
    assert bar.close is None
    assert bar.volume is None
    assert bar.average is None
    assert bar.barCount == 0


def test_bar_data_garbage_volume_string_yields_none():
    proto = HistoricalDataBar_pb2.HistoricalDataBar(
        open=150.0, high=151.0, low=149.0, close=150.5, volume="abc", WAP="garbage"
    )
    bar = createBarData(proto)
    assert bar.open == Decimal("150")
    assert bar.volume is None
    assert bar.average is None


def test_bar_data_full_round_trip_through_str_routing():
    """Wire ``open=0.1`` (double) routes through ``str()`` so Decimal
    representation is "0.1" not the 17-digit float-imprecision form."""
    proto = HistoricalDataBar_pb2.HistoricalDataBar(
        open=0.1,
        high=0.2,
        low=0.05,
        close=0.15,
        volume="1000",
        WAP="0.125",
        barCount=42,
    )
    bar = createBarData(proto)
    assert bar.open == Decimal("0.1")
    assert bar.average == Decimal("0.125")
    assert bar.volume == Decimal("1000")
    assert bar.barCount == 42


# ---------------------------------------------------------------------------
# HistoricalData / End / Update
# ---------------------------------------------------------------------------


def test_iter_historical_data_bars_empty():
    args = iterHistoricalDataBars(HistoricalData_pb2.HistoricalData())
    assert args.reqId == -1
    assert args.bars == []


def test_iter_historical_data_bars_round_trip():
    proto = HistoricalData_pb2.HistoricalData(reqId=7)
    a = proto.historicalDataBars.add()
    a.date, a.open, a.close, a.barCount = "20260509", 150.0, 151.0, 100
    b = proto.historicalDataBars.add()
    b.date, b.open, b.close, b.barCount = "20260510", 151.0, 152.0, 110
    args = iterHistoricalDataBars(proto)
    assert args.reqId == 7
    assert len(args.bars) == 2
    assert args.bars[0].open == Decimal("150")
    assert args.bars[1].close == Decimal("152")


def test_historical_data_end_empty_proto():
    args = createHistoricalDataEndArgs(HistoricalDataEnd_pb2.HistoricalDataEnd())
    assert (args.reqId, args.start, args.end) == (-1, "", "")


def test_historical_data_end_full_round_trip():
    proto = HistoricalDataEnd_pb2.HistoricalDataEnd(
        reqId=7, startDateStr="20260101", endDateStr="20260509"
    )
    args = createHistoricalDataEndArgs(proto)
    assert (args.reqId, args.start, args.end) == (7, "20260101", "20260509")


def test_historical_data_update_empty_proto():
    args = createHistoricalDataUpdateArgs(
        HistoricalDataUpdate_pb2.HistoricalDataUpdate()
    )
    assert args.reqId == -1
    assert args.bar.open is None


def test_historical_data_update_round_trip():
    proto = HistoricalDataUpdate_pb2.HistoricalDataUpdate(reqId=7)
    proto.historicalDataBar.open = 150.25
    proto.historicalDataBar.barCount = 5
    args = createHistoricalDataUpdateArgs(proto)
    assert args.reqId == 7
    assert args.bar.open == Decimal("150.25")
    assert args.bar.barCount == 5


# ---------------------------------------------------------------------------
# RealTimeBarTick (msgId 50)
# ---------------------------------------------------------------------------


def test_realtime_bar_empty_proto_yields_none_numerics():
    args = createRealtimeBarArgs(RealTimeBarTick_pb2.RealTimeBarTick())
    assert (args.reqId, args.time, args.count) == (0, 0, 0)
    assert args.open_ is None
    assert args.wap is None


def test_realtime_bar_full_round_trip():
    proto = RealTimeBarTick_pb2.RealTimeBarTick(
        reqId=7,
        time=1700000000,
        open=150.0,
        high=151.0,
        low=149.0,
        close=150.5,
        volume="1000",
        WAP="150.25",
        count=10,
    )
    args = createRealtimeBarArgs(proto)
    assert args.open_ == Decimal("150")
    assert args.close == Decimal("150.5")
    assert args.volume == Decimal("1000")
    assert args.wap == Decimal("150.25")


# ---------------------------------------------------------------------------
# HeadTimestamp
# ---------------------------------------------------------------------------


def test_head_timestamp_empty_proto():
    args = createHeadTimestampArgs(HeadTimestamp_pb2.HeadTimestamp())
    assert (args.reqId, args.headTimestamp) == (-1, "")


def test_head_timestamp_round_trip():
    proto = HeadTimestamp_pb2.HeadTimestamp(reqId=7, headTimestamp="20100101 09:30:00")
    args = createHeadTimestampArgs(proto)
    assert (args.reqId, args.headTimestamp) == (7, "20100101 09:30:00")


# ---------------------------------------------------------------------------
# HistogramData
# ---------------------------------------------------------------------------


def test_histogram_data_empty_proto():
    args = createHistogramDataArgs(HistogramData_pb2.HistogramData())
    assert args.reqId == -1
    assert args.items == []


def test_histogram_data_repeated_round_trip():
    proto = HistogramData_pb2.HistogramData(reqId=7)
    a = proto.histogramDataEntries.add()
    a.price, a.size = 150.0, "100"
    b = proto.histogramDataEntries.add()
    b.price, b.size = 150.5, "200"
    args = createHistogramDataArgs(proto)
    assert args.reqId == 7
    assert len(args.items) == 2
    assert args.items[0].price == 150.0
    assert args.items[0].count == 100
    assert args.items[1].count == 200


def test_histogram_data_garbage_size_yields_zero_count():
    proto = HistogramData_pb2.HistogramData(reqId=7)
    e = proto.histogramDataEntries.add()
    e.price, e.size = 150.0, "abc"
    args = createHistogramDataArgs(proto)
    assert args.items[0].count == 0


# ---------------------------------------------------------------------------
# HistoricalSchedule
# ---------------------------------------------------------------------------


def test_historical_schedule_empty_proto():
    args = createHistoricalScheduleArgs(HistoricalSchedule_pb2.HistoricalSchedule())
    assert args.reqId == -1
    assert (args.startDateTime, args.endDateTime, args.timeZone) == ("", "", "")
    assert args.sessions == []


def test_historical_schedule_full_round_trip():
    proto = HistoricalSchedule_pb2.HistoricalSchedule(
        reqId=7,
        startDateTime="20260509 09:30:00",
        endDateTime="20260509 16:00:00",
        timeZone="US/Eastern",
    )
    s = proto.historicalSessions.add()
    s.startDateTime, s.endDateTime, s.refDate = "09:30:00", "12:00:00", "20260509"
    s2 = proto.historicalSessions.add()
    s2.startDateTime, s2.endDateTime, s2.refDate = "13:00:00", "16:00:00", "20260509"
    args = createHistoricalScheduleArgs(proto)
    assert args.reqId == 7
    assert args.timeZone == "US/Eastern"
    assert len(args.sessions) == 2
    assert args.sessions[0].refDate == "20260509"


# ---------------------------------------------------------------------------
# HistoricalTick / BidAsk / Last
# ---------------------------------------------------------------------------


def test_historical_tick_empty_proto():
    t = createHistoricalTick(HistoricalTick_pb2.HistoricalTick())
    assert t.time == 0
    assert t.price == 0.0
    assert t.size == 0.0


def test_historical_tick_garbage_size():
    proto = HistoricalTick_pb2.HistoricalTick(time=1700000000, price=150.0, size="abc")
    t = createHistoricalTick(proto)
    assert t.size == 0.0


def test_historical_tick_bid_ask_round_trip_with_attrib():
    proto = HistoricalTickBidAsk_pb2.HistoricalTickBidAsk(
        time=1700000000, priceBid=150.0, priceAsk=150.5, sizeBid="100", sizeAsk="200"
    )
    proto.tickAttribBidAsk.askPastHigh = True
    t = createHistoricalTickBidAsk(proto)
    assert t.priceBid == 150.0
    assert t.sizeAsk == 200.0
    assert t.tickAttribBidAsk is not None
    assert t.tickAttribBidAsk.askPastHigh is True


def test_historical_tick_last_round_trip():
    proto = HistoricalTickLast_pb2.HistoricalTickLast(
        time=1700000000,
        price=150.25,
        size="100",
        exchange="ARCA",
        specialConditions="",
    )
    proto.tickAttribLast.pastLimit = True
    t = createHistoricalTickLast(proto)
    assert t.price == 150.25
    assert t.exchange == "ARCA"
    assert t.tickAttribLast is not None
    assert t.tickAttribLast.pastLimit is True


# ---------------------------------------------------------------------------
# HistoricalTicks / BidAsk / Last (batched)
# ---------------------------------------------------------------------------


def test_historical_ticks_empty_proto():
    args = createHistoricalTicksArgs(HistoricalTicks_pb2.HistoricalTicks())
    assert args.reqId == -1
    assert args.ticks == []
    assert args.done is False


def test_historical_ticks_round_trip_with_done_flag():
    proto = HistoricalTicks_pb2.HistoricalTicks(reqId=7, isDone=True)
    a = proto.historicalTicks.add()
    a.time, a.price, a.size = 1700000000, 150.0, "100"
    b = proto.historicalTicks.add()
    b.time, b.price, b.size = 1700000010, 150.5, "150"
    args = createHistoricalTicksArgs(proto)
    assert args.reqId == 7
    assert len(args.ticks) == 2
    assert args.ticks[0].price == 150.0
    assert args.ticks[1].size == 150.0
    assert args.done is True


def test_historical_ticks_bid_ask_carries_done():
    proto = HistoricalTicksBidAsk_pb2.HistoricalTicksBidAsk(reqId=7, isDone=True)
    t = proto.historicalTicksBidAsk.add()
    t.time, t.priceBid, t.priceAsk = 1700000000, 150.0, 150.5
    t.sizeBid, t.sizeAsk = "100", "200"
    args = createHistoricalTicksBidAskArgs(proto)
    assert (args.reqId, len(args.ticks), args.done) == (7, 1, True)


def test_historical_ticks_last_carries_done():
    proto = HistoricalTicksLast_pb2.HistoricalTicksLast(reqId=7, isDone=False)
    t = proto.historicalTicksLast.add()
    t.time, t.price, t.size = 1700000000, 150.0, "100"
    t.exchange = "ARCA"
    args = createHistoricalTicksLastArgs(proto)
    assert (args.reqId, len(args.ticks), args.done) == (7, 1, False)
    assert args.ticks[0].exchange == "ARCA"


# ===========================================================================
# Send-side request envelopes
# ===========================================================================


def test_historical_data_request_round_trip_with_keepUpToDate_flag():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createHistoricalDataRequestProto(
        7,
        contract,
        "20260509 16:00:00",
        "1 D",
        "1 hour",
        "TRADES",
        1,
        1,
        True,
    )
    decoded = HistoricalDataRequest_pb2.HistoricalDataRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.barSizeSetting == "1 hour"
    assert decoded.duration == "1 D"
    assert decoded.useRTH is True
    assert decoded.whatToShow == "TRADES"
    assert decoded.formatDate == 1
    assert decoded.keepUpToDate is True


def test_cancel_historical_data_round_trip():
    proto = createCancelHistoricalDataProto(7)
    decoded = CancelHistoricalData_pb2.CancelHistoricalData()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


def test_real_time_bars_request_round_trip():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createRealTimeBarsRequestProto(7, contract, 5, "TRADES", True)
    decoded = RealTimeBarsRequest_pb2.RealTimeBarsRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.barSize == 5
    assert decoded.useRTH is True


def test_cancel_real_time_bars_round_trip():
    proto = createCancelRealTimeBarsProto(7)
    decoded = CancelRealTimeBars_pb2.CancelRealTimeBars()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


def test_head_timestamp_request_round_trip():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createHeadTimestampRequestProto(7, contract, 1, "TRADES", 1)
    decoded = HeadTimestampRequest_pb2.HeadTimestampRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.useRTH is True
    assert decoded.whatToShow == "TRADES"


def test_cancel_head_timestamp_round_trip():
    proto = createCancelHeadTimestampProto(7)
    decoded = CancelHeadTimestamp_pb2.CancelHeadTimestamp()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


def test_histogram_data_request_round_trip():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createHistogramDataRequestProto(7, contract, True, "1 month")
    decoded = HistogramDataRequest_pb2.HistogramDataRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.useRTH is True
    assert decoded.timePeriod == "1 month"


def test_cancel_histogram_data_round_trip():
    proto = createCancelHistogramDataProto(7)
    decoded = CancelHistogramData_pb2.CancelHistogramData()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


def test_historical_ticks_request_round_trip():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createHistoricalTicksRequestProto(
        7,
        contract,
        "20260101 09:30:00",
        "20260101 16:00:00",
        100,
        "TRADES",
        1,
        True,
    )
    decoded = HistoricalTicksRequest_pb2.HistoricalTicksRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.numberOfTicks == 100
    assert decoded.whatToShow == "TRADES"
    assert decoded.useRTH is True
    assert decoded.ignoreSize is True


def test_cancel_historical_ticks_round_trip():
    proto = createCancelHistoricalTicksProto(7)
    decoded = CancelHistoricalTicks_pb2.CancelHistoricalTicks()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
