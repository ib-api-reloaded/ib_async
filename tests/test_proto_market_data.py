"""Negative-path-first tests for the market-data protobuf converter.

Coverage strategy mirrors ``test_proto_accounts``:

* Empty / partial protos must produce safe-default args without
  crashing — exercises HasField guards.
* Wire-string sizes ("nan", "", garbage) must coerce to ``0.0`` for
  wrapper-side comparisons, never raise.
* TickByTickData oneof dispatch must produce the right branch
  dataclass per inner-message variant.
* Send-side request envelopes must carry every caller-supplied field
  including bool flags (``snapshot``, ``regulatorySnapshot``,
  ``isSmartDepth``, ``ignoreSize``) whose proto3 default would
  otherwise silently swallow ``True``.
"""

from __future__ import annotations

import ib_async as ibi
from ib_async._pb import (
    CancelMarketData_pb2,
    CancelMarketDepth_pb2,
    CancelTickByTick_pb2,
    DepthMarketDataDescription_pb2,
    MarketDataRequest_pb2,
    MarketDataType_pb2,
    MarketDataTypeRequest_pb2,
    MarketDepth_pb2,
    MarketDepthExchanges_pb2,
    MarketDepthL2_pb2,
    MarketDepthRequest_pb2,
    RerouteMarketDataRequest_pb2,
    RerouteMarketDepthRequest_pb2,
    TickByTickData_pb2,
    TickByTickRequest_pb2,
    TickGeneric_pb2,
    TickOptionComputation_pb2,
    TickPrice_pb2,
    TickReqParams_pb2,
    TickSize_pb2,
    TickSnapshotEnd_pb2,
    TickString_pb2,
)
from ib_async._proto.market_data import (
    TickByTickAllLastArgs,
    TickByTickBidAskArgs,
    TickByTickMidPointArgs,
    createCancelMarketDataProto,
    createCancelMarketDepthProto,
    createCancelTickByTickProto,
    createDepthMktDataDescription,
    createMarketDataRequestProto,
    createMarketDataTypeArgs,
    createMarketDataTypeRequestProto,
    createMarketDepthExchangesList,
    createMarketDepthExchangesRequestProto,
    createMarketDepthRequestProto,
    createPriceSizeTickArgs,
    createRerouteMktDataReqArgs,
    createRerouteMktDepthReqArgs,
    createTickByTickRequestProto,
    createTickGenericArgs,
    createTickOptionComputationArgs,
    createTickReqParamsArgs,
    createTickSizeArgs,
    createTickSnapshotEndReqId,
    createTickStringArgs,
    createUpdateMktDepthArgs,
    createUpdateMktDepthL2Args,
    dispatchTickByTick,
)

# ---------------------------------------------------------------------------
# TickPrice — combined price + size
# ---------------------------------------------------------------------------


def test_tick_price_empty_proto_is_zero_args():
    args = createPriceSizeTickArgs(TickPrice_pb2.TickPrice())
    assert args.reqId == 0
    assert args.tickType == 0
    assert args.price == 0.0
    assert args.size == 0.0


def test_tick_price_garbage_size_string_is_zero():
    """Wire ``size`` is string; "abc" must coerce to 0.0, not raise."""
    proto = TickPrice_pb2.TickPrice(reqId=1, tickType=4, price=150.25, size="abc")
    args = createPriceSizeTickArgs(proto)
    assert args.reqId == 1
    assert args.tickType == 4
    assert args.price == 150.25
    assert args.size == 0.0


def test_tick_price_nan_size_is_zero():
    proto = TickPrice_pb2.TickPrice(reqId=1, tickType=4, price=150.25, size="nan")
    args = createPriceSizeTickArgs(proto)
    assert args.size == 0.0


def test_tick_price_full_round_trip():
    proto = TickPrice_pb2.TickPrice(reqId=1, tickType=4, price=150.25, size="100")
    args = createPriceSizeTickArgs(proto)
    assert args.reqId == 1
    assert args.tickType == 4
    assert args.price == 150.25
    assert args.size == 100.0


def test_tick_price_attrMask_is_silently_dropped():
    """Match binary path: attrMask is read but not surfaced."""
    proto = TickPrice_pb2.TickPrice(
        reqId=1, tickType=4, price=150.25, size="100", attrMask=3
    )
    args = createPriceSizeTickArgs(proto)
    # PriceSizeTickArgs has exactly 4 named fields; no attrMask slot.
    assert not hasattr(args, "attrMask")


# ---------------------------------------------------------------------------
# TickSize / TickGeneric / TickString
# ---------------------------------------------------------------------------


def test_tick_size_empty():
    args = createTickSizeArgs(TickSize_pb2.TickSize())
    assert args.reqId == 0
    assert args.tickType == 0
    assert args.size == 0.0


def test_tick_size_round_trip():
    proto = TickSize_pb2.TickSize(reqId=7, tickType=0, size="500")
    args = createTickSizeArgs(proto)
    assert args.reqId == 7
    assert args.tickType == 0
    assert args.size == 500.0


def test_tick_generic_round_trip():
    proto = TickGeneric_pb2.TickGeneric(reqId=7, tickType=23, value=42.5)
    args = createTickGenericArgs(proto)
    assert args.reqId == 7
    assert args.tickType == 23
    assert args.value == 42.5


def test_tick_string_empty_value():
    proto = TickString_pb2.TickString(reqId=7, tickType=45)
    args = createTickStringArgs(proto)
    assert args.reqId == 7
    assert args.tickType == 45
    assert args.value == ""


def test_tick_string_round_trip():
    proto = TickString_pb2.TickString(reqId=7, tickType=45, value="20260509 09:30:00")
    args = createTickStringArgs(proto)
    assert args.reqId == 7
    assert args.tickType == 45
    assert args.value == "20260509 09:30:00"


# ---------------------------------------------------------------------------
# TickReqParams / TickSnapshotEnd
# ---------------------------------------------------------------------------


def test_tick_req_params_empty():
    args = createTickReqParamsArgs(TickReqParams_pb2.TickReqParams())
    assert args.reqId == 0
    assert args.minTick == 0.0
    assert args.bboExchange == ""
    assert args.snapshotPermissions == 0


def test_tick_req_params_round_trip():
    proto = TickReqParams_pb2.TickReqParams(
        reqId=7, minTick="0.01", bboExchange="ARCA", snapshotPermissions=3
    )
    args = createTickReqParamsArgs(proto)
    assert args.reqId == 7
    assert args.minTick == 0.01
    assert args.bboExchange == "ARCA"
    assert args.snapshotPermissions == 3


def test_tick_snapshot_end_returns_minus_one_on_empty():
    assert createTickSnapshotEndReqId(TickSnapshotEnd_pb2.TickSnapshotEnd()) == -1


def test_tick_snapshot_end_round_trip():
    proto = TickSnapshotEnd_pb2.TickSnapshotEnd(reqId=42)
    assert createTickSnapshotEndReqId(proto) == 42


# ---------------------------------------------------------------------------
# TickOptionComputation
# ---------------------------------------------------------------------------


def test_tick_option_computation_empty_proto():
    args = createTickOptionComputationArgs(
        TickOptionComputation_pb2.TickOptionComputation()
    )
    assert args.reqId == 0
    assert args.tickType == 0
    assert args.tickAttrib == 0
    assert args.impliedVol == 0.0
    assert args.undPrice == 0.0


def test_tick_option_computation_full_round_trip():
    proto = TickOptionComputation_pb2.TickOptionComputation(
        reqId=7,
        tickType=10,
        tickAttrib=1,
        impliedVol=0.25,
        delta=0.5,
        optPrice=10.50,
        pvDividend=0.0,
        gamma=0.05,
        vega=0.10,
        theta=-0.02,
        undPrice=150.0,
    )
    args = createTickOptionComputationArgs(proto)
    assert args.reqId == 7
    assert args.tickType == 10
    assert args.tickAttrib == 1
    assert args.impliedVol == 0.25
    assert args.delta == 0.5
    assert args.optPrice == 10.50
    assert args.pvDividend == 0.0
    assert args.gamma == 0.05
    assert args.vega == 0.10
    assert args.theta == -0.02
    assert args.undPrice == 150.0


# ---------------------------------------------------------------------------
# TickByTickData oneof dispatch
# ---------------------------------------------------------------------------


def test_tick_by_tick_no_oneof_set_returns_none():
    proto = TickByTickData_pb2.TickByTickData(reqId=7, tickType=1)
    assert dispatchTickByTick(proto) is None


def test_tick_by_tick_all_last_dispatch():
    proto = TickByTickData_pb2.TickByTickData(reqId=7, tickType=1)
    inner = proto.historicalTickLast
    inner.time = 1700000000
    inner.price = 150.25
    inner.size = "100"
    inner.exchange = "ARCA"
    inner.specialConditions = ""
    inner.tickAttribLast.pastLimit = True
    inner.tickAttribLast.unreported = False
    args = dispatchTickByTick(proto)
    assert isinstance(args, TickByTickAllLastArgs)
    assert args.reqId == 7
    assert args.tickType == 1
    assert args.time == 1700000000
    assert args.price == 150.25
    assert args.size == 100.0
    assert args.exchange == "ARCA"
    assert args.specialConditions == ""
    assert args.tickAttribLast.pastLimit is True


def test_tick_by_tick_bid_ask_dispatch():
    proto = TickByTickData_pb2.TickByTickData(reqId=7, tickType=3)
    inner = proto.historicalTickBidAsk
    inner.time = 1700000000
    inner.priceBid = 150.0
    inner.priceAsk = 150.5
    inner.sizeBid = "100"
    inner.sizeAsk = "200"
    inner.tickAttribBidAsk.askPastHigh = True
    args = dispatchTickByTick(proto)
    assert isinstance(args, TickByTickBidAskArgs)
    assert args.reqId == 7
    assert args.time == 1700000000
    assert args.bidPrice == 150.0
    assert args.askPrice == 150.5
    assert args.bidSize == 100.0
    assert args.askSize == 200.0
    assert args.tickAttribBidAsk.askPastHigh is True


def test_tick_by_tick_mid_point_dispatch():
    proto = TickByTickData_pb2.TickByTickData(reqId=7, tickType=4)
    inner = proto.historicalTickMidPoint
    inner.time = 1700000000
    inner.price = 150.25
    args = dispatchTickByTick(proto)
    assert isinstance(args, TickByTickMidPointArgs)
    assert args.reqId == 7
    assert args.time == 1700000000
    assert args.midPoint == 150.25


# ---------------------------------------------------------------------------
# MarketDataType
# ---------------------------------------------------------------------------


def test_market_data_type_empty():
    args = createMarketDataTypeArgs(MarketDataType_pb2.MarketDataType())
    assert args.reqId == 0
    assert args.marketDataType == 0


def test_market_data_type_round_trip():
    proto = MarketDataType_pb2.MarketDataType(reqId=7, marketDataType=3)
    args = createMarketDataTypeArgs(proto)
    assert args.reqId == 7
    assert args.marketDataType == 3


# ---------------------------------------------------------------------------
# MarketDepth / MarketDepthL2
# ---------------------------------------------------------------------------


def test_update_mkt_depth_empty_proto_is_zero_args():
    """MarketDepth without inner data — sane defaults, no crash."""
    args = createUpdateMktDepthArgs(MarketDepth_pb2.MarketDepth())
    assert args.reqId == 0
    assert args.position == 0
    assert args.operation == 0
    assert args.side == 0
    assert args.price == 0.0
    assert args.size == 0.0


def test_update_mkt_depth_full_round_trip():
    proto = MarketDepth_pb2.MarketDepth(reqId=7)
    proto.marketDepthData.position = 0
    proto.marketDepthData.operation = 0
    proto.marketDepthData.side = 1
    proto.marketDepthData.price = 150.0
    proto.marketDepthData.size = "100"
    args = createUpdateMktDepthArgs(proto)
    assert args.reqId == 7
    assert args.position == 0
    assert args.operation == 0
    assert args.side == 1
    assert args.price == 150.0
    assert args.size == 100.0


def test_update_mkt_depth_l2_carries_market_maker_and_smart_depth():
    proto = MarketDepthL2_pb2.MarketDepthL2(reqId=7)
    proto.marketDepthData.position = 1
    proto.marketDepthData.marketMaker = "ARCA"
    proto.marketDepthData.operation = 1
    proto.marketDepthData.side = 0
    proto.marketDepthData.price = 150.5
    proto.marketDepthData.size = "200"
    proto.marketDepthData.isSmartDepth = True
    args = createUpdateMktDepthL2Args(proto)
    assert args.reqId == 7
    assert args.position == 1
    assert args.marketMaker == "ARCA"
    assert args.operation == 1
    assert args.side == 0
    assert args.price == 150.5
    assert args.size == 200.0
    assert args.isSmartDepth is True


def test_update_mkt_depth_l2_garbage_size_is_zero():
    proto = MarketDepthL2_pb2.MarketDepthL2(reqId=7)
    proto.marketDepthData.size = "abc"
    args = createUpdateMktDepthL2Args(proto)
    assert args.size == 0.0


# ---------------------------------------------------------------------------
# DepthMktDataDescription / MarketDepthExchanges
# ---------------------------------------------------------------------------


def test_depth_mkt_data_description_empty():
    d = createDepthMktDataDescription(
        DepthMarketDataDescription_pb2.DepthMarketDataDescription()
    )
    assert d.exchange == ""
    assert d.aggGroup == 0


def test_depth_mkt_data_description_full_round_trip():
    proto = DepthMarketDataDescription_pb2.DepthMarketDataDescription(
        exchange="ARCA",
        secType="STK",
        listingExch="NYSE",
        serviceDataType="L2",
        aggGroup=3,
    )
    d = createDepthMktDataDescription(proto)
    assert d.exchange == "ARCA"
    assert d.secType == "STK"
    assert d.aggGroup == 3


def test_market_depth_exchanges_empty_returns_empty_list():
    assert (
        createMarketDepthExchangesList(MarketDepthExchanges_pb2.MarketDepthExchanges())
        == []
    )


def test_market_depth_exchanges_repeated():
    proto = MarketDepthExchanges_pb2.MarketDepthExchanges()
    a = proto.depthMarketDataDescriptions.add()
    a.exchange = "ARCA"
    b = proto.depthMarketDataDescriptions.add()
    b.exchange = "NASDAQ"
    descs = createMarketDepthExchangesList(proto)
    assert len(descs) == 2
    assert descs[0].exchange == "ARCA"
    assert descs[1].exchange == "NASDAQ"


# ---------------------------------------------------------------------------
# Reroute requests (msgId 64 / 65)
# ---------------------------------------------------------------------------


def test_reroute_mkt_data_req_round_trip():
    proto = RerouteMarketDataRequest_pb2.RerouteMarketDataRequest(
        reqId=7, conId=12345, exchange="SMART"
    )
    args = createRerouteMktDataReqArgs(proto)
    assert args.reqId == 7
    assert args.conId == 12345
    assert args.exchange == "SMART"


def test_reroute_mkt_depth_req_round_trip():
    proto = RerouteMarketDepthRequest_pb2.RerouteMarketDepthRequest(
        reqId=7, conId=12345, exchange="SMART"
    )
    args = createRerouteMktDepthReqArgs(proto)
    assert args.reqId == 7
    assert args.conId == 12345
    assert args.exchange == "SMART"


# ===========================================================================
# Send-side request envelopes
# ===========================================================================


def test_market_data_request_proto_round_trips_every_field():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createMarketDataRequestProto(7, contract, "100,101", True, False)
    decoded = MarketDataRequest_pb2.MarketDataRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.contract.symbol == "AAPL"
    assert decoded.contract.secType == "STK"
    assert decoded.genericTickList == "100,101"
    assert decoded.snapshot is True
    assert decoded.regulatorySnapshot is False


def test_cancel_market_data_round_trip():
    proto = createCancelMarketDataProto(7)
    decoded = CancelMarketData_pb2.CancelMarketData()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


def test_market_data_type_request_round_trip():
    proto = createMarketDataTypeRequestProto(3)
    decoded = MarketDataTypeRequest_pb2.MarketDataTypeRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.marketDataType == 3


def test_market_depth_request_round_trip():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createMarketDepthRequestProto(7, contract, 5, True)
    decoded = MarketDepthRequest_pb2.MarketDepthRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.numRows == 5
    assert decoded.isSmartDepth is True
    assert decoded.contract.symbol == "AAPL"


def test_cancel_market_depth_round_trip_with_smart_depth_flag():
    proto = createCancelMarketDepthProto(7, True)
    decoded = CancelMarketDepth_pb2.CancelMarketDepth()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.isSmartDepth is True


def test_market_depth_exchanges_request_serializes_empty():
    assert createMarketDepthExchangesRequestProto().SerializeToString() == b""


def test_tick_by_tick_request_round_trip():
    contract = ibi.Stock("AAPL", "SMART", "USD")
    proto = createTickByTickRequestProto(7, contract, "BidAsk", 100, True)
    decoded = TickByTickRequest_pb2.TickByTickRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.tickType == "BidAsk"
    assert decoded.numberOfTicks == 100
    assert decoded.ignoreSize is True
    assert decoded.contract.symbol == "AAPL"


def test_cancel_tick_by_tick_round_trip():
    proto = createCancelTickByTickProto(7)
    decoded = CancelTickByTick_pb2.CancelTickByTick()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
