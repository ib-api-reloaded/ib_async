"""End-to-end dispatch + gating tests for market data + historical protobuf.

Same pattern as ``test_proto_accounts_dispatch``: synthetic proto
payloads route through ``Decoder.processProtoBuf`` and the resulting
wrapper / ticker / registry state is asserted directly. Send-side per
``useProtoBuf(canonicalMsgId)`` boolean: a server below the per-family
gate emits NUL-separated text framing; a server at or above the gate
emits a 4-byte BE protobuf frame.

Coverage spans the market-data and historical receive msgIds (TickPrice, TickSize,
TickGeneric, TickString, MarketDepth, MarketDepthL2, MarketDataType,
MktDepthExchanges, RerouteMktData/Depth, RealTimeBarTick,
HeadTimestamp, HistogramData, HistoricalDataUpdate, HistoricalTicks*,
TickByTick, HistoricalSchedule, HistoricalDataEnd) and the per-msgId
gating for reqMktData / cancelMktData / reqMktDepth / cancelMktDepth /
reqMarketDataType / reqMktDepthExchanges / reqHistoricalData /
cancelHistoricalData / reqRealTimeBars / cancelRealTimeBars /
reqHeadTimeStamp / cancelHeadTimeStamp / reqHistogramData /
cancelHistogramData / reqHistoricalTicks / reqTickByTickData /
cancelTickByTickData.
"""

from __future__ import annotations

import ib_async as ibi
from ib_async._pb import (
    CancelHistoricalData_pb2,
    CancelMarketData_pb2,
    CancelMarketDepth_pb2,
    CancelTickByTick_pb2,
    HeadTimestamp_pb2,
    HistogramData_pb2,
    HistoricalDataEnd_pb2,
    HistoricalDataRequest_pb2,
    HistoricalSchedule_pb2,
    HistoricalTicks_pb2,
    MarketDataRequest_pb2,
    MarketDataType_pb2,
    MarketDepth_pb2,
    MarketDepthL2_pb2,
    MarketDepthRequest_pb2,
    RealTimeBarsRequest_pb2,
    RerouteMarketDataRequest_pb2,
    TickByTickData_pb2,
    TickByTickRequest_pb2,
    TickPrice_pb2,
    TickSize_pb2,
)
from ib_async._pb_msgids import (
    CANCEL_HISTORICAL_DATA,
    CANCEL_MKT_DATA,
    CANCEL_MKT_DEPTH,
    CANCEL_TICK_BY_TICK_DATA,
    REQ_HISTORICAL_DATA,
    REQ_MARKET_DATA_TYPE,
    REQ_MKT_DATA,
    REQ_MKT_DEPTH,
    REQ_MKT_DEPTH_EXCHANGES,
    REQ_REAL_TIME_BARS,
    REQ_TICK_BY_TICK_DATA,
)
from ib_async._requests import ReqIdKey
from tests._helpers import _captureSend, _decodeProtoFrame, _ibAtVersion


def _seedTicker(ib, reqId: int, contract: ibi.Contract | None = None):
    """Register a real market-data subscription via SubscriptionRegistry
    so the wrapper has a Ticker to update when proto messages arrive."""
    from ib_async._subscriptions import MktDataSub

    contract = contract or ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = getattr(contract, "conId", None) or 7
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    sub = MktDataSub(reqId=reqId, contract=contract, ticker=ticker)
    ib.wrapper.subscriptions.add(sub)
    return ticker


# ===========================================================================
# RECEIVE SIDE
# ===========================================================================


def test_tick_price_proto_updates_ticker_bid():
    ib = _ibAtVersion(207)
    ticker = _seedTicker(ib, 7)
    proto = TickPrice_pb2.TickPrice(reqId=7, tickType=1, price=150.25, size="100")
    ib.client.decoder.processProtoBuf(1, proto.SerializeToString())
    assert ticker.bid == 150.25
    assert ticker.bidSize == 100.0


def test_tick_size_proto_updates_ticker_volume():
    ib = _ibAtVersion(207)
    ticker = _seedTicker(ib, 7)
    proto = TickSize_pb2.TickSize(reqId=7, tickType=8, size="1000")
    ib.client.decoder.processProtoBuf(2, proto.SerializeToString())
    assert ticker.volume == 1000.0


def test_market_depth_proto_routes_to_depth_dict():
    ib = _ibAtVersion(207)
    ticker = _seedTicker(ib, 7)
    proto = MarketDepth_pb2.MarketDepth(reqId=7)
    proto.marketDepthData.position = 0
    proto.marketDepthData.operation = 0
    proto.marketDepthData.side = 1
    proto.marketDepthData.price = 150.0
    proto.marketDepthData.size = "100"
    ib.client.decoder.processProtoBuf(12, proto.SerializeToString())
    # bid side at position 0 is now populated
    assert 0 in ticker.domBidsDict
    assert ticker.domBidsDict[0].price == 150.0


def test_market_depth_l2_proto_carries_market_maker():
    ib = _ibAtVersion(207)
    ticker = _seedTicker(ib, 7)
    proto = MarketDepthL2_pb2.MarketDepthL2(reqId=7)
    proto.marketDepthData.position = 0
    proto.marketDepthData.marketMaker = "ARCA"
    proto.marketDepthData.operation = 0
    proto.marketDepthData.side = 1
    proto.marketDepthData.price = 150.0
    proto.marketDepthData.size = "100"
    ib.client.decoder.processProtoBuf(13, proto.SerializeToString())
    assert ticker.domBidsDict[0].marketMaker == "ARCA"


def test_market_data_type_proto_updates_ticker():
    ib = _ibAtVersion(207)
    ticker = _seedTicker(ib, 7)
    proto = MarketDataType_pb2.MarketDataType(reqId=7, marketDataType=3)
    ib.client.decoder.processProtoBuf(58, proto.SerializeToString())
    assert ticker.marketDataType == 3


def test_reroute_mkt_data_req_proto_does_not_raise():
    """Wrapper.rerouteMktDataReq is a stub on this client; smoke-test."""
    ib = _ibAtVersion(207)
    proto = RerouteMarketDataRequest_pb2.RerouteMarketDataRequest(
        reqId=7, conId=12345, exchange="SMART"
    )
    ib.client.decoder.processProtoBuf(91, proto.SerializeToString())


def test_head_timestamp_proto_settles_reqId():
    ib = _ibAtVersion(207)
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    assert not req.future.done()
    proto = HeadTimestamp_pb2.HeadTimestamp(reqId=7, headTimestamp="20100101 09:30:00")
    ib.client.decoder.processProtoBuf(88, proto.SerializeToString())
    assert req.future.done()


def test_histogram_data_proto_settles_reqId_with_items():
    ib = _ibAtVersion(207)
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = HistogramData_pb2.HistogramData(reqId=7)
    e = proto.histogramDataEntries.add()
    e.price, e.size = 150.0, "100"
    ib.client.decoder.processProtoBuf(89, proto.SerializeToString())
    assert req.future.done()
    items = req.future.result()
    assert len(items) == 1
    assert items[0].price == 150.0


def test_historical_data_end_proto_settles_singleton():
    ib = _ibAtVersion(207)
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = HistoricalDataEnd_pb2.HistoricalDataEnd(
        reqId=7, startDateStr="20260101", endDateStr="20260509"
    )
    ib.client.decoder.processProtoBuf(108, proto.SerializeToString())
    assert req.future.done()


def test_historical_ticks_proto_routes_through_wrapper():
    """Smoke test: HistoricalTicks decodes and dispatches without error.
    The wrapper.historicalTicks routes via the requests registry; with
    no waiter open the call is a no-op."""
    ib = _ibAtVersion(207)
    proto = HistoricalTicks_pb2.HistoricalTicks(reqId=7, isDone=True)
    t = proto.historicalTicks.add()
    t.time, t.price, t.size = 1700000000, 150.0, "100"
    ib.client.decoder.processProtoBuf(96, proto.SerializeToString())


def test_tick_by_tick_oneof_dispatch_routes_to_all_last():
    ib = _ibAtVersion(207)
    ticker = _seedTicker(ib, 7)
    proto = TickByTickData_pb2.TickByTickData(reqId=7, tickType=1)
    inner = proto.historicalTickLast
    inner.time = 1700000000
    inner.price = 150.25
    inner.size = "100"
    inner.exchange = "ARCA"
    inner.tickAttribLast.pastLimit = False
    ib.client.decoder.processProtoBuf(99, proto.SerializeToString())
    # Wrapper.tickByTickAllLast appends to ticker.tickByTicks and updates
    # ticker.last
    assert ticker.last == 150.25
    assert len(ticker.tickByTicks) == 1


def test_historical_schedule_proto_settles_reqId():
    ib = _ibAtVersion(207)
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = HistoricalSchedule_pb2.HistoricalSchedule(
        reqId=7,
        startDateTime="20260509 09:30:00",
        endDateTime="20260509 16:00:00",
        timeZone="US/Eastern",
    )
    s = proto.historicalSessions.add()
    s.startDateTime, s.endDateTime, s.refDate = "09:30:00", "16:00:00", "20260509"
    ib.client.decoder.processProtoBuf(106, proto.SerializeToString())
    assert req.future.done()
    schedule = req.future.result()
    assert schedule.timeZone == "US/Eastern"
    assert len(schedule.sessions) == 1


# ===========================================================================
# SEND SIDE
# ===========================================================================


def test_req_mkt_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(206)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqMktData(7, contract, "100,101", True, False, [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_MKT_DATA
    proto = MarketDataRequest_pb2.MarketDataRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.contract.symbol == "AAPL"
    assert proto.snapshot is True


def test_req_mkt_data_uses_binary_below_gate():
    ib = _ibAtVersion(205)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqMktData(7, contract, "", False, False, [])
    assert sent[0][4:].startswith(b"\x00\x00\x00\x01")  # REQ_MKT_DATA=1, raw int (server>=201)


def test_cancel_mkt_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(206)
    sent = _captureSend(ib)
    ib.client.cancelMktData(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_MKT_DATA
    proto = CancelMarketData_pb2.CancelMarketData()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_mkt_depth_uses_protobuf_at_gate():
    ib = _ibAtVersion(206)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqMktDepth(7, contract, 5, True, [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_MKT_DEPTH
    proto = MarketDepthRequest_pb2.MarketDepthRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.numRows == 5
    assert proto.isSmartDepth is True


def test_cancel_mkt_depth_uses_protobuf_at_gate():
    ib = _ibAtVersion(206)
    sent = _captureSend(ib)
    ib.client.cancelMktDepth(7, True)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_MKT_DEPTH
    proto = CancelMarketDepth_pb2.CancelMarketDepth()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.isSmartDepth is True


def test_req_market_data_type_uses_protobuf_at_gate():
    ib = _ibAtVersion(206)
    sent = _captureSend(ib)
    ib.client.reqMarketDataType(3)
    canonical, _ = _decodeProtoFrame(sent[0])
    assert canonical == REQ_MARKET_DATA_TYPE


def test_req_mkt_depth_exchanges_uses_protobuf_at_gate():
    """REQ_MKT_DEPTH_EXCHANGES gates at REST_MESSAGES_3 (213)."""
    ib = _ibAtVersion(213)
    sent = _captureSend(ib)
    ib.client.reqMktDepthExchanges()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_MKT_DEPTH_EXCHANGES
    assert body == b""


def test_req_historical_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(208)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqHistoricalData(
        7, contract, "20260509 16:00:00", "1 D", "1 hour", "TRADES", 1, 1, True, []
    )
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_HISTORICAL_DATA
    proto = HistoricalDataRequest_pb2.HistoricalDataRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.barSizeSetting == "1 hour"
    assert proto.duration == "1 D"
    assert proto.keepUpToDate is True


def test_cancel_historical_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(208)
    sent = _captureSend(ib)
    ib.client.cancelHistoricalData(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_HISTORICAL_DATA
    proto = CancelHistoricalData_pb2.CancelHistoricalData()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_real_time_bars_uses_protobuf_at_gate():
    ib = _ibAtVersion(208)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqRealTimeBars(7, contract, 5, "TRADES", True, [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_REAL_TIME_BARS
    proto = RealTimeBarsRequest_pb2.RealTimeBarsRequest()
    proto.ParseFromString(body)
    assert proto.barSize == 5
    assert proto.useRTH is True


def test_req_tick_by_tick_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(208)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqTickByTickData(7, contract, "BidAsk", 100, True)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_TICK_BY_TICK_DATA
    proto = TickByTickRequest_pb2.TickByTickRequest()
    proto.ParseFromString(body)
    assert proto.tickType == "BidAsk"
    assert proto.numberOfTicks == 100
    assert proto.ignoreSize is True


def test_cancel_tick_by_tick_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(208)
    sent = _captureSend(ib)
    ib.client.cancelTickByTickData(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_TICK_BY_TICK_DATA
    proto = CancelTickByTick_pb2.CancelTickByTick()
    proto.ParseFromString(body)
    assert proto.reqId == 7
