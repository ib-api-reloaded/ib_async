"""Negative-path-first tests for the news + WSH converter.

Coverage strategy:

* Empty / partial protos must produce safe-default args without
  crashing — exercises the ``HasField`` discipline on every optional
  field.
* Send-side request envelopes must carry every caller-supplied field
  through SerializeToString → ParseFromString. Bool flags
  (``allMessages``, ``fillWatchlist``, ``fillPortfolio``,
  ``fillCompetitors``, ``hasMore``) round-trip True specifically — the
  proto3 default is False and a missing assignment would silently
  swallow a True request from the caller.
* Wire field-name mismatches (``newsMsgId`` vs ``msgId``,
  ``providerCode`` vs ``code``) round-trip to the domain spelling.
* Repeated container ``NewsProviders`` works for both empty and
  multi-element cases.
"""

from __future__ import annotations

import pytest

from ib_async._pb import (
    CancelNewsBulletins_pb2,
    CancelWshEventData_pb2,
    CancelWshMetaData_pb2,
    HistoricalNews_pb2,
    HistoricalNewsEnd_pb2,
    HistoricalNewsRequest_pb2,
    NewsArticle_pb2,
    NewsArticleRequest_pb2,
    NewsBulletin_pb2,
    NewsBulletinsRequest_pb2,
    NewsProvider_pb2,
    NewsProviders_pb2,
    TickNews_pb2,
    WshEventData_pb2,
    WshEventDataRequest_pb2,
    WshMetaData_pb2,
    WshMetaDataRequest_pb2,
)
from ib_async._proto.news import (
    createCancelNewsBulletinsProto,
    createCancelWshEventDataProto,
    createCancelWshMetaDataProto,
    createHistoricalNewsArgs,
    createHistoricalNewsEndArgs,
    createHistoricalNewsRequestProto,
    createNewsArticle,
    createNewsArticleArgs,
    createNewsArticleRequestProto,
    createNewsBulletin,
    createNewsBulletinsRequestProto,
    createNewsProvider,
    createNewsProviders,
    createNewsProvidersRequestProto,
    createNewsTick,
    createTickNewsArgs,
    createUpdateNewsBulletinArgs,
    createWshEventDataArgs,
    createWshEventDataRequestProto,
    createWshMetaDataArgs,
    createWshMetaDataRequestProto,
)
from ib_async.objects import WshEventData

# ---------------------------------------------------------------------------
# NewsBulletin → updateNewsBulletin args + domain
# ---------------------------------------------------------------------------


def test_news_bulletin_empty_proto_returns_safe_defaults():
    args = createUpdateNewsBulletinArgs(NewsBulletin_pb2.NewsBulletin())
    assert args.msgId == 0
    assert args.msgType == 0
    assert args.message == ""
    assert args.origExchange == ""


def test_news_bulletin_partial_proto_only_fills_set_fields():
    proto = NewsBulletin_pb2.NewsBulletin()
    proto.newsMsgId = 7
    proto.newsMessage = "Market closing early"
    # newsMsgType and originatingExch deliberately unset
    args = createUpdateNewsBulletinArgs(proto)
    assert args.msgId == 7
    assert args.msgType == 0
    assert args.message == "Market closing early"
    assert args.origExchange == ""


def test_news_bulletin_wire_field_names_map_to_domain():
    """Wire ``newsMsgId``/``newsMsgType``/``newsMessage``/``originatingExch``
    must map to the wrapper's ``msgId``/``msgType``/``message``/``origExchange``."""
    proto = NewsBulletin_pb2.NewsBulletin(
        newsMsgId=42,
        newsMsgType=1,
        newsMessage="Volatility halt",
        originatingExch="NYSE",
    )
    args = createUpdateNewsBulletinArgs(proto)
    assert args.msgId == 42
    assert args.msgType == 1
    assert args.message == "Volatility halt"
    assert args.origExchange == "NYSE"


def test_news_bulletin_domain_helper_round_trip():
    proto = NewsBulletin_pb2.NewsBulletin(
        newsMsgId=42, newsMsgType=1, newsMessage="halt", originatingExch="NYSE"
    )
    bulletin = createNewsBulletin(proto)
    assert bulletin.msgId == 42
    assert bulletin.msgType == 1
    assert bulletin.message == "halt"
    assert bulletin.origExchange == "NYSE"


# ---------------------------------------------------------------------------
# NewsBulletinsRequest / CancelNewsBulletins
# ---------------------------------------------------------------------------


def test_news_bulletins_request_proto_round_trip_with_true_flag():
    """proto3 default for unset bool is False — caller passing True
    must round-trip through SerializeToString or every subscription
    silently degrades to live-only."""
    proto = createNewsBulletinsRequestProto(True)
    decoded = NewsBulletinsRequest_pb2.NewsBulletinsRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.allMessages is True


def test_news_bulletins_request_proto_round_trip_with_false_flag():
    proto = createNewsBulletinsRequestProto(False)
    decoded = NewsBulletinsRequest_pb2.NewsBulletinsRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.allMessages is False


def test_cancel_news_bulletins_proto_serializes_empty():
    proto = createCancelNewsBulletinsProto()
    assert proto.SerializeToString() == b""


def test_cancel_news_bulletins_round_trip():
    proto = createCancelNewsBulletinsProto()
    decoded = CancelNewsBulletins_pb2.CancelNewsBulletins()
    decoded.ParseFromString(proto.SerializeToString())
    # Empty body — no fields to assert, but ParseFromString must not raise.
    assert decoded.SerializeToString() == b""


# ---------------------------------------------------------------------------
# NewsProvider / NewsProviders
# ---------------------------------------------------------------------------


def test_news_provider_empty_proto_returns_empty_strings():
    p = createNewsProvider(NewsProvider_pb2.NewsProvider())
    assert p.code == ""
    assert p.name == ""


def test_news_provider_wire_fields_map_to_domain_code_name():
    """Wire ``providerCode``/``providerName`` map to domain ``code``/``name``."""
    proto = NewsProvider_pb2.NewsProvider(providerCode="BRFG", providerName="Briefing")
    p = createNewsProvider(proto)
    assert p.code == "BRFG"
    assert p.name == "Briefing"


def test_news_providers_empty_repeated_returns_empty_list():
    assert createNewsProviders(NewsProviders_pb2.NewsProviders()) == []


def test_news_providers_two_element_repeated_round_trip():
    proto = NewsProviders_pb2.NewsProviders()
    a = proto.newsProviders.add()
    a.providerCode, a.providerName = "BRFG", "Briefing"
    b = proto.newsProviders.add()
    b.providerCode, b.providerName = "DJ-N", "Dow Jones"
    providers = createNewsProviders(proto)
    assert len(providers) == 2
    assert providers[0].code == "BRFG"
    assert providers[0].name == "Briefing"
    assert providers[1].code == "DJ-N"
    assert providers[1].name == "Dow Jones"


def test_news_providers_request_proto_serializes_empty():
    assert createNewsProvidersRequestProto().SerializeToString() == b""


# ---------------------------------------------------------------------------
# NewsArticle (msgId 84) + NewsArticleRequest
# ---------------------------------------------------------------------------


def test_news_article_empty_proto_returns_safe_defaults():
    args = createNewsArticleArgs(NewsArticle_pb2.NewsArticle())
    assert args.reqId == 0
    assert args.articleType == 0
    assert args.articleText == ""


def test_news_article_full_round_trip():
    proto = NewsArticle_pb2.NewsArticle(
        reqId=7, articleType=1, articleText="<html>...</html>"
    )
    args = createNewsArticleArgs(proto)
    assert args.reqId == 7
    assert args.articleType == 1
    assert args.articleText == "<html>...</html>"


def test_news_article_domain_helper_returns_two_field_dataclass():
    """Domain ``NewsArticle`` carries only ``articleType`` and
    ``articleText`` — ``reqId`` is the request key, not part of the
    article body."""
    proto = NewsArticle_pb2.NewsArticle(reqId=7, articleType=1, articleText="hi")
    article = createNewsArticle(proto)
    assert article.articleType == 1
    assert article.articleText == "hi"


def test_news_article_request_proto_carries_every_field():
    proto = createNewsArticleRequestProto(7, "BRFG", "BRFG$abc123")
    decoded = NewsArticleRequest_pb2.NewsArticleRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.providerCode == "BRFG"
    assert decoded.articleId == "BRFG$abc123"


# ---------------------------------------------------------------------------
# HistoricalNews / HistoricalNewsEnd / HistoricalNewsRequest
# ---------------------------------------------------------------------------


def test_historical_news_empty_proto_returns_safe_defaults():
    args = createHistoricalNewsArgs(HistoricalNews_pb2.HistoricalNews())
    assert args.reqId == 0
    assert args.time == ""
    assert args.providerCode == ""
    assert args.articleId == ""
    assert args.headline == ""


def test_historical_news_passes_time_through_as_raw_string():
    """The wrapper parses ``time`` itself with ``parseIBDatetime``; the
    converter must NOT pre-parse — that would double-parse and break."""
    proto = HistoricalNews_pb2.HistoricalNews(
        reqId=7,
        time="2026-05-09 10:00:00.0",
        providerCode="BRFG",
        articleId="BRFG$abc",
        headline="Earnings beat",
    )
    args = createHistoricalNewsArgs(proto)
    assert args.reqId == 7
    assert args.time == "2026-05-09 10:00:00.0"
    assert args.providerCode == "BRFG"
    assert args.articleId == "BRFG$abc"
    assert args.headline == "Earnings beat"


def test_historical_news_garbage_time_string_passes_through_unmodified():
    """Garbage input is the wrapper's problem to handle — converter must
    not crash, just pass the string along."""
    proto = HistoricalNews_pb2.HistoricalNews(reqId=1, time="not-a-date")
    args = createHistoricalNewsArgs(proto)
    assert args.time == "not-a-date"


def test_historical_news_end_empty_proto():
    args = createHistoricalNewsEndArgs(HistoricalNewsEnd_pb2.HistoricalNewsEnd())
    assert args.reqId == 0
    assert args.hasMore is False


def test_historical_news_end_has_more_true_round_trip():
    """proto3 default for ``hasMore`` is False; True round-trip is the
    regression hazard."""
    proto = HistoricalNewsEnd_pb2.HistoricalNewsEnd(reqId=7, hasMore=True)
    args = createHistoricalNewsEndArgs(proto)
    assert args.reqId == 7
    assert args.hasMore is True


def test_historical_news_request_proto_round_trip_carries_every_field():
    proto = createHistoricalNewsRequestProto(
        reqId=7,
        conId=265598,
        providerCodes="BRFG+DJ-N",
        startDateTime="2026-05-01 00:00:00",
        endDateTime="2026-05-09 00:00:00",
        totalResults=100,
    )
    decoded = HistoricalNewsRequest_pb2.HistoricalNewsRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.conId == 265598
    assert decoded.providerCodes == "BRFG+DJ-N"
    assert decoded.startDateTime == "2026-05-01 00:00:00"
    assert decoded.endDateTime == "2026-05-09 00:00:00"
    assert decoded.totalResults == 100


# ---------------------------------------------------------------------------
# TickNews (binary msgId 84 — handler dispatches to tickNews)
# ---------------------------------------------------------------------------


def test_tick_news_empty_proto_returns_safe_defaults():
    args = createTickNewsArgs(TickNews_pb2.TickNews())
    assert args.reqId == 0
    assert args.timeStamp == 0
    assert args.providerCode == ""
    assert args.articleId == ""
    assert args.headline == ""
    assert args.extraData == ""


def test_tick_news_wire_timestamp_int64_maps_to_camelCase_timeStamp():
    """Wire field is ``timestamp`` (lowercase); wrapper signature uses
    ``timeStamp`` (camel). Args dataclass mirrors the wrapper."""
    proto = TickNews_pb2.TickNews(
        reqId=7,
        timestamp=1_715_000_000_000,
        providerCode="BRFG",
        articleId="BRFG$abc",
        headline="Halt",
        extraData="x",
    )
    args = createTickNewsArgs(proto)
    assert args.reqId == 7
    assert args.timeStamp == 1_715_000_000_000
    assert args.providerCode == "BRFG"
    assert args.articleId == "BRFG$abc"
    assert args.headline == "Halt"
    assert args.extraData == "x"


def test_tick_news_domain_helper_yields_news_tick_without_contract():
    """Contract is attached by the wrapper from its per-reqId snapshot
    — the converter leaves ``contract`` as None."""
    proto = TickNews_pb2.TickNews(
        reqId=7,
        timestamp=1_715_000_000_000,
        providerCode="BRFG",
        articleId="BRFG$abc",
        headline="Halt",
        extraData="x",
    )
    tick = createNewsTick(proto)
    assert tick.timeStamp == 1_715_000_000_000
    assert tick.providerCode == "BRFG"
    assert tick.articleId == "BRFG$abc"
    assert tick.headline == "Halt"
    assert tick.extraData == "x"
    assert tick.contract is None


# ---------------------------------------------------------------------------
# WshMetaData (msgId 104) + request / cancel
# ---------------------------------------------------------------------------


def test_wsh_meta_data_empty_proto():
    args = createWshMetaDataArgs(WshMetaData_pb2.WshMetaData())
    assert args.reqId == 0
    assert args.dataJson == ""


def test_wsh_meta_data_full_round_trip():
    proto = WshMetaData_pb2.WshMetaData(reqId=7, dataJson='{"k":"v"}')
    args = createWshMetaDataArgs(proto)
    assert args.reqId == 7
    assert args.dataJson == '{"k":"v"}'


def test_wsh_meta_data_request_proto_round_trip():
    proto = createWshMetaDataRequestProto(7)
    decoded = WshMetaDataRequest_pb2.WshMetaDataRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


def test_cancel_wsh_meta_data_round_trip():
    proto = createCancelWshMetaDataProto(7)
    decoded = CancelWshMetaData_pb2.CancelWshMetaData()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# WshEventData (msgId 105) + request / cancel — the bool-flag landmine
# ---------------------------------------------------------------------------


def test_wsh_event_data_empty_proto():
    args = createWshEventDataArgs(WshEventData_pb2.WshEventData())
    assert args.reqId == 0
    assert args.dataJson == ""


def test_wsh_event_data_full_round_trip():
    proto = WshEventData_pb2.WshEventData(reqId=7, dataJson='{"events":[]}')
    args = createWshEventDataArgs(proto)
    assert args.reqId == 7
    assert args.dataJson == '{"events":[]}'


def test_wsh_event_data_request_proto_round_trip_all_flags_true():
    """proto3 default for ``fillWatchlist``/``fillPortfolio``/``fillCompetitors``
    is False — every bool flag must round-trip True or the user's
    request silently changes shape on the wire."""
    data = WshEventData(
        conId=265598,
        filter='{"event":"earnings"}',
        fillWatchlist=True,
        fillPortfolio=True,
        fillCompetitors=True,
        startDate="2026-05-01",
        endDate="2026-05-09",
        totalLimit=100,
    )
    proto = createWshEventDataRequestProto(7, data)
    decoded = WshEventDataRequest_pb2.WshEventDataRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.conId == 265598
    assert decoded.filter == '{"event":"earnings"}'
    assert decoded.fillWatchlist is True
    assert decoded.fillPortfolio is True
    assert decoded.fillCompetitors is True
    assert decoded.startDate == "2026-05-01"
    assert decoded.endDate == "2026-05-09"
    assert decoded.totalLimit == 100


def test_wsh_event_data_request_proto_round_trip_all_flags_false():
    data = WshEventData(
        conId=265598,
        filter="",
        fillWatchlist=False,
        fillPortfolio=False,
        fillCompetitors=False,
        startDate="",
        endDate="",
        totalLimit=0,
    )
    proto = createWshEventDataRequestProto(7, data)
    decoded = WshEventDataRequest_pb2.WshEventDataRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.conId == 265598
    assert decoded.fillWatchlist is False
    assert decoded.fillPortfolio is False
    assert decoded.fillCompetitors is False


def test_cancel_wsh_event_data_round_trip():
    proto = createCancelWshEventDataProto(7)
    decoded = CancelWshEventData_pb2.CancelWshEventData()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# Cross-cutting: empty-body envelopes serialize to empty bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        createNewsProvidersRequestProto,
        createCancelNewsBulletinsProto,
    ],
)
def test_empty_body_request_envelopes_serialize_to_empty_bytes(factory):
    """Empty body must serialize to zero bytes so the wire framing is
    just the 4-byte msgId, no trailing payload."""
    assert factory().SerializeToString() == b""
