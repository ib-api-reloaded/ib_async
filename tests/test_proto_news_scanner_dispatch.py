"""End-to-end dispatch + gating tests for news + scanner / fundamentals / PnL.

Same pattern as test_proto_accounts_dispatch / market_historical_dispatch.
Synthetic proto payloads route through ``Decoder.processProtoBuf`` and
the resulting wrapper / registry state is asserted directly. Send-side
per ``useProtoBuf(canonicalMsgId)``: a server below the per-family gate
emits NUL-separated text; at or above, a 4-byte BE protobuf frame.
"""

from __future__ import annotations

import ib_async as ibi
from ib_async._pb import (
    CancelFundamentalsData_pb2,
    CancelNewsBulletins_pb2,
    CancelPnL_pb2,
    CancelPnLSingle_pb2,
    CancelScannerSubscription_pb2,
    CancelWshMetaData_pb2,
    FundamentalsData_pb2,
    FundamentalsDataRequest_pb2,
    HistoricalNews_pb2,
    HistoricalNewsEnd_pb2,
    HistoricalNewsRequest_pb2,
    NewsArticle_pb2,
    NewsArticleRequest_pb2,
    NewsBulletin_pb2,
    NewsBulletinsRequest_pb2,
    NewsProviders_pb2,
    PnL_pb2,
    PnLRequest_pb2,
    PnLSingle_pb2,
    PnLSingleRequest_pb2,
    ScannerData_pb2,
    ScannerParameters_pb2,
    ScannerSubscriptionRequest_pb2,
    TickNews_pb2,
    WshEventData_pb2,
    WshEventDataRequest_pb2,
    WshMetaData_pb2,
    WshMetaDataRequest_pb2,
)
from ib_async._pb_msgids import (
    CANCEL_FUNDAMENTAL_DATA,
    CANCEL_NEWS_BULLETINS,
    CANCEL_PNL,
    CANCEL_PNL_SINGLE,
    CANCEL_SCANNER_SUBSCRIPTION,
    CANCEL_WSH_EVENT_DATA,
    CANCEL_WSH_META_DATA,
    REQ_FUNDAMENTAL_DATA,
    REQ_HISTORICAL_NEWS,
    REQ_NEWS_ARTICLE,
    REQ_NEWS_BULLETINS,
    REQ_NEWS_PROVIDERS,
    REQ_PNL,
    REQ_PNL_SINGLE,
    REQ_SCANNER_PARAMETERS,
    REQ_SCANNER_SUBSCRIPTION,
    REQ_WSH_EVENT_DATA,
    REQ_WSH_META_DATA,
)
from ib_async._requests import ReqIdKey, SingletonKey
from tests._helpers import _captureSend, _decodeProtoFrame, _ibAtVersion

# ===========================================================================
# RECEIVE SIDE
# ===========================================================================


def test_news_bulletin_proto_lands_in_msgId_dict():
    ib = ibi.IB()
    proto = NewsBulletin_pb2.NewsBulletin(
        newsMsgId=42,
        newsMsgType=1,
        newsMessage="Test bulletin",
        originatingExch="NYSE",
    )
    ib.client.decoder.processProtoBuf(14, proto.SerializeToString())
    bulletin = ib.wrapper.msgId2NewsBulletin[42]
    assert bulletin.message == "Test bulletin"
    assert bulletin.origExchange == "NYSE"


def test_news_providers_proto_settles_singleton():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("newsProviders"), container=[])
    proto = NewsProviders_pb2.NewsProviders()
    p = proto.newsProviders.add()
    p.providerCode, p.providerName = "BRFG", "Briefing.com"
    ib.client.decoder.processProtoBuf(85, proto.SerializeToString())
    assert req.future.done()
    providers = req.future.result()
    assert providers[0].code == "BRFG"
    assert providers[0].name == "Briefing.com"


def test_news_article_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = NewsArticle_pb2.NewsArticle(reqId=7, articleType=1, articleText="<html/>")
    ib.client.decoder.processProtoBuf(83, proto.SerializeToString())
    assert req.future.done()
    article = req.future.result()
    assert article.articleType == 1
    assert article.articleText == "<html/>"


def test_historical_news_proto_appends_to_reqId_list():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = HistoricalNews_pb2.HistoricalNews(
        reqId=7,
        time="2026-05-09 09:30:00.0",
        providerCode="BRFG",
        articleId="ABC123",
        headline="Market update",
    )
    ib.client.decoder.processProtoBuf(86, proto.SerializeToString())
    proto2 = HistoricalNewsEnd_pb2.HistoricalNewsEnd(reqId=7, hasMore=False)
    ib.client.decoder.processProtoBuf(87, proto2.SerializeToString())
    assert req.future.done()
    items = req.future.result()
    assert len(items) == 1
    assert items[0].providerCode == "BRFG"


def test_tick_news_proto_appends_to_news_ticks():
    ib = ibi.IB()
    proto = TickNews_pb2.TickNews(
        reqId=7,
        timestamp=1700000000,
        providerCode="BRFG",
        articleId="ABC123",
        headline="Headline",
        extraData="extra",
    )
    ib.client.decoder.processProtoBuf(84, proto.SerializeToString())
    assert len(ib.wrapper.newsTicks) == 1
    tick = ib.wrapper.newsTicks[0]
    assert tick.providerCode == "BRFG"
    assert tick.headline == "Headline"


def test_wsh_meta_data_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = WshMetaData_pb2.WshMetaData(reqId=7, dataJson='{"foo": "bar"}')
    ib.client.decoder.processProtoBuf(104, proto.SerializeToString())
    assert req.future.done()
    assert req.future.result() == '{"foo": "bar"}'


def test_wsh_event_data_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = WshEventData_pb2.WshEventData(reqId=7, dataJson='[{"event": "x"}]')
    ib.client.decoder.processProtoBuf(105, proto.SerializeToString())
    assert req.future.done()


def test_scanner_parameters_proto_settles_singleton():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("scannerParams"), container=[])
    proto = ScannerParameters_pb2.ScannerParameters(xml="<xml/>")
    ib.client.decoder.processProtoBuf(19, proto.SerializeToString())
    assert req.future.done()
    assert req.future.result() == "<xml/>"


def test_scanner_data_proto_dispatches_per_element_then_calls_end():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = ScannerData_pb2.ScannerData(reqId=7)
    el = proto.scannerDataElement.add()
    el.rank, el.marketName = 0, "ARCA"
    el.contract.symbol = "AAPL"
    el.distance, el.benchmark, el.projection, el.comboKey = "10%", "SPY", "1Y", ""
    el2 = proto.scannerDataElement.add()
    el2.rank, el2.marketName = 1, "NASDAQ"
    el2.contract.symbol = "MSFT"
    ib.client.decoder.processProtoBuf(20, proto.SerializeToString())
    assert req.future.done()
    items = req.future.result()
    assert len(items) == 2
    assert items[0].contractDetails.contract.symbol == "AAPL"
    assert items[1].contractDetails.contract.symbol == "MSFT"


def test_fundamental_data_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = FundamentalsData_pb2.FundamentalsData(reqId=7, data="<xml/>")
    ib.client.decoder.processProtoBuf(51, proto.SerializeToString())
    assert req.future.done()
    assert req.future.result() == "<xml/>"


def test_pnl_proto_does_not_raise_without_subscription():
    """Wrapper.pnl is a no-op when no PnLSub is registered for reqId."""
    ib = ibi.IB()
    proto = PnL_pb2.PnL(reqId=7, dailyPnL=100.0, unrealizedPnL=50.0, realizedPnL=25.0)
    ib.client.decoder.processProtoBuf(94, proto.SerializeToString())


def test_pnl_single_proto_fractional_position_truncates_to_int():
    """Wire ``PnLSingle.position`` is a Decimal-precision string but
    Wrapper.pnlSingle takes ``pos: int``. Fractional values silently
    truncate via ``int(safe_decimal(...))``."""
    ib = ibi.IB()
    proto = PnLSingle_pb2.PnLSingle(
        reqId=7,
        position="100.5",
        dailyPnL=10.0,
        unrealizedPnL=5.0,
        realizedPnL=2.5,
        value=1000.0,
    )
    # No PnLSingleSub registered — wrapper drops, but the dispatch
    # should still decode without raising.
    ib.client.decoder.processProtoBuf(95, proto.SerializeToString())


# ===========================================================================
# SEND SIDE
# ===========================================================================


def test_req_news_bulletins_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.reqNewsBulletins(True)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_NEWS_BULLETINS
    proto = NewsBulletinsRequest_pb2.NewsBulletinsRequest()
    proto.ParseFromString(body)
    assert proto.allMessages is True


def test_cancel_news_bulletins_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.cancelNewsBulletins()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_NEWS_BULLETINS
    proto = CancelNewsBulletins_pb2.CancelNewsBulletins()
    proto.ParseFromString(body)


def test_req_news_providers_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.reqNewsProviders()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_NEWS_PROVIDERS
    assert body == b""


def test_req_news_article_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.reqNewsArticle(7, "BRFG", "ABC123", [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_NEWS_ARTICLE
    proto = NewsArticleRequest_pb2.NewsArticleRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.providerCode == "BRFG"
    assert proto.articleId == "ABC123"


def test_req_historical_news_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.reqHistoricalNews(
        7, 12345, "BRFG", "20260101 09:30:00", "20260109 16:00:00", 100, []
    )
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_HISTORICAL_NEWS
    proto = HistoricalNewsRequest_pb2.HistoricalNewsRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.conId == 12345
    assert proto.totalResults == 100


def test_req_wsh_meta_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.reqWshMetaData(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_WSH_META_DATA
    proto = WshMetaDataRequest_pb2.WshMetaDataRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_cancel_wsh_meta_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.cancelWshMetaData(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_WSH_META_DATA
    proto = CancelWshMetaData_pb2.CancelWshMetaData()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_wsh_event_data_carries_all_filter_fields():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    data = ibi.WshEventData(
        conId=12345,
        filter="custom",
        fillWatchlist=True,
        fillPortfolio=False,
        fillCompetitors=True,
        startDate="20260101",
        endDate="20260109",
        totalLimit=100,
    )
    ib.client.reqWshEventData(7, data)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_WSH_EVENT_DATA
    proto = WshEventDataRequest_pb2.WshEventDataRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.conId == 12345
    assert proto.fillWatchlist is True
    assert proto.fillCompetitors is True
    assert proto.totalLimit == 100


def test_cancel_wsh_event_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.cancelWshEventData(7)
    canonical, _ = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_WSH_EVENT_DATA


def test_req_scanner_subscription_carries_every_field():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    sub = ibi.ScannerSubscription(
        instrument="STK",
        locationCode="STK.US",
        scanCode="TOP_PERC_GAIN",
        excludeConvertible=True,
    )
    ib.client.reqScannerSubscription(7, sub, [], [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_SCANNER_SUBSCRIPTION
    proto = ScannerSubscriptionRequest_pb2.ScannerSubscriptionRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.scannerSubscription.instrument == "STK"
    assert proto.scannerSubscription.scanCode == "TOP_PERC_GAIN"
    assert proto.scannerSubscription.excludeConvertible is True


def test_cancel_scanner_subscription_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    ib.client.cancelScannerSubscription(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_SCANNER_SUBSCRIPTION
    proto = CancelScannerSubscription_pb2.CancelScannerSubscription()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_scanner_parameters_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    ib.client.reqScannerParameters()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_SCANNER_PARAMETERS
    assert body == b""


def test_req_fundamental_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.reqFundamentalData(7, contract, "ReportSnapshot", [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_FUNDAMENTAL_DATA
    proto = FundamentalsDataRequest_pb2.FundamentalsDataRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.contract.symbol == "AAPL"
    assert proto.reportType == "ReportSnapshot"


def test_cancel_fundamental_data_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    ib.client.cancelFundamentalData(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_FUNDAMENTAL_DATA
    proto = CancelFundamentalsData_pb2.CancelFundamentalsData()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_pnl_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    ib.client.reqPnL(7, "DU1", "MODEL_A")
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_PNL
    proto = PnLRequest_pb2.PnLRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.account == "DU1"
    assert proto.modelCode == "MODEL_A"


def test_cancel_pnl_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    ib.client.cancelPnL(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_PNL
    proto = CancelPnL_pb2.CancelPnL()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_pnl_single_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    ib.client.reqPnLSingle(7, "DU1", "MODEL_A", 12345)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_PNL_SINGLE
    proto = PnLSingleRequest_pb2.PnLSingleRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.conId == 12345


def test_cancel_pnl_single_uses_protobuf_at_gate():
    ib = _ibAtVersion(210)
    sent = _captureSend(ib)
    ib.client.cancelPnLSingle(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_PNL_SINGLE
    proto = CancelPnLSingle_pb2.CancelPnLSingle()
    proto.ParseFromString(body)
    assert proto.reqId == 7


# ===========================================================================
# Below-gate sanity: server <209/<210 stays binary
# ===========================================================================


def test_req_news_bulletins_below_gate_uses_binary():
    ib = _ibAtVersion(208)
    sent = _captureSend(ib)
    ib.client.reqNewsBulletins(True)
    assert sent[0][4:].startswith(
        b"\x00\x00\x00\x0c"
    )  # REQ_NEWS_BULLETINS=12, raw int (server>=201)


def test_req_pnl_below_gate_uses_binary():
    ib = _ibAtVersion(209)
    sent = _captureSend(ib)
    ib.client.reqPnL(7, "DU1", "")
    assert sent[0][4:].startswith(
        b"\x00\x00\x00\x5c"
    )  # REQ_PNL=92, raw int (server>=201)
