"""Protobuf converters for news bulletins, articles, news ticks, and WSH.

Pure functions: every converter takes only proto inputs (or domain
inputs on the send side). No reads from module-level state. ``HasField``
guards every optional read.

Wire-shape notes:

* ``NewsBulletin`` carries int ``newsMsgId`` / ``newsMsgType`` and string
  ``newsMessage`` / ``originatingExch``. The wrapper consumes them as
  ``updateNewsBulletin(msgId, msgType, message, origExchange)``.
* ``NewsProviders`` is a repeated container of ``NewsProvider`` messages
  whose wire fields are ``providerCode`` / ``providerName``; the domain
  ``NewsProvider`` dataclass spells the same fields ``code`` / ``name``.
* ``HistoricalNews.time`` is a wire string — the wrapper parses it with
  ``parseIBDatetime`` so this converter passes the raw string through.
* ``TickNews.timestamp`` is wire ``int64`` (epoch milliseconds in IBKR's
  spec). The wrapper signature names the argument ``timeStamp`` (camel
  case) — args dataclass uses the wrapper's spelling.
* ``WshEventDataRequest`` is built from a ``WshEventData`` domain
  dataclass on the send side; ``None`` from the domain object skips the
  proto write entirely (mirrors IBKR's ``isValidIntValue`` gating from
  ``client_utils.createWshEventDataRequestProto``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .._pb import (
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
    NewsProvidersRequest_pb2,
    TickNews_pb2,
    WshEventData_pb2,
    WshEventDataRequest_pb2,
    WshMetaData_pb2,
    WshMetaDataRequest_pb2,
)
from ..contract import TagValue
from ..objects import (
    NewsArticle,
    NewsBulletin,
    NewsProvider,
    NewsTick,
    WshEventData,
)
from ..util import UNSET_INTEGER
from .safe import fill_tag_value_map

# ---------------------------------------------------------------------------
# Args dataclasses for converter return shapes — slotted, frozen, named.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class UpdateNewsBulletinArgs:
    """Args for ``Wrapper.updateNewsBulletin(msgId, msgType, message, origExchange)``."""

    msgId: int
    msgType: int
    message: str
    origExchange: str


@dataclass(slots=True, frozen=True)
class NewsArticleArgs:
    """Args for ``Wrapper.newsArticle(reqId, articleType, articleText)``."""

    reqId: int
    articleType: int
    articleText: str


@dataclass(slots=True, frozen=True)
class HistoricalNewsArgs:
    """Args for ``Wrapper.historicalNews(reqId, time, providerCode, articleId, headline)``."""

    reqId: int
    time: str
    providerCode: str
    articleId: str
    headline: str


@dataclass(slots=True, frozen=True)
class HistoricalNewsEndArgs:
    """Args for ``Wrapper.historicalNewsEnd(reqId, hasMore)``."""

    reqId: int
    hasMore: bool


@dataclass(slots=True, frozen=True)
class TickNewsArgs:
    """Args for ``Wrapper.tickNews(reqId, timeStamp, providerCode, articleId, headline, extraData)``."""

    reqId: int
    timeStamp: int
    providerCode: str
    articleId: str
    headline: str
    extraData: str


@dataclass(slots=True, frozen=True)
class WshMetaDataArgs:
    """Args for ``Wrapper.wshMetaData(reqId, dataJson)``."""

    reqId: int
    dataJson: str


@dataclass(slots=True, frozen=True)
class WshEventDataArgs:
    """Args for ``Wrapper.wshEventData(reqId, dataJson)``."""

    reqId: int
    dataJson: str


# ---------------------------------------------------------------------------
# NewsBulletin (msgId 14 receive) + NewsBulletinsRequest / CancelNewsBulletins
# ---------------------------------------------------------------------------


def createUpdateNewsBulletinArgs(
    proto: NewsBulletin_pb2.NewsBulletin,
) -> UpdateNewsBulletinArgs:
    """``Wrapper.updateNewsBulletin(msgId, msgType, message, origExchange)`` args.

    Wire field names ``newsMsgId`` / ``newsMsgType`` / ``newsMessage`` /
    ``originatingExch`` map to wrapper-spelled ``msgId`` / ``msgType`` /
    ``message`` / ``origExchange``.
    """
    msgId = proto.newsMsgId if proto.HasField("newsMsgId") else 0
    msgType = proto.newsMsgType if proto.HasField("newsMsgType") else 0
    message = proto.newsMessage if proto.HasField("newsMessage") else ""
    origExchange = proto.originatingExch if proto.HasField("originatingExch") else ""
    return UpdateNewsBulletinArgs(
        msgId=msgId, msgType=msgType, message=message, origExchange=origExchange
    )


def createNewsBulletin(proto: NewsBulletin_pb2.NewsBulletin) -> NewsBulletin:
    """Decode a ``NewsBulletin`` proto directly into the domain dataclass."""
    args = createUpdateNewsBulletinArgs(proto)
    return NewsBulletin(args.msgId, args.msgType, args.message, args.origExchange)


def createNewsBulletinsRequestProto(
    allMessages: bool,
) -> NewsBulletinsRequest_pb2.NewsBulletinsRequest:
    proto = NewsBulletinsRequest_pb2.NewsBulletinsRequest()
    if allMessages:
        proto.allMessages = allMessages
    return proto


def createCancelNewsBulletinsProto() -> CancelNewsBulletins_pb2.CancelNewsBulletins:
    return CancelNewsBulletins_pb2.CancelNewsBulletins()


# ---------------------------------------------------------------------------
# NewsProviders (msgId 85 receive) + NewsProvidersRequest
# ---------------------------------------------------------------------------


def createNewsProvider(proto: NewsProvider_pb2.NewsProvider) -> NewsProvider:
    """Wire fields ``providerCode`` / ``providerName`` map to domain
    ``code`` / ``name``."""
    code = proto.providerCode if proto.HasField("providerCode") else ""
    name = proto.providerName if proto.HasField("providerName") else ""
    return NewsProvider(code=code, name=name)


def createNewsProviders(
    proto: NewsProviders_pb2.NewsProviders,
) -> list[NewsProvider]:
    """Decode the repeated ``NewsProvider`` container into a list of
    domain dataclasses. The wrapper's ``newsProviders`` method takes the
    list as its only positional argument."""
    return [createNewsProvider(p) for p in proto.newsProviders]


def createNewsProvidersRequestProto() -> NewsProvidersRequest_pb2.NewsProvidersRequest:
    return NewsProvidersRequest_pb2.NewsProvidersRequest()


# ---------------------------------------------------------------------------
# NewsArticle (msgId 84 receive) + NewsArticleRequest
# ---------------------------------------------------------------------------


def createNewsArticleArgs(proto: NewsArticle_pb2.NewsArticle) -> NewsArticleArgs:
    """``Wrapper.newsArticle(reqId, articleType, articleText)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    articleType = proto.articleType if proto.HasField("articleType") else 0
    articleText = proto.articleText if proto.HasField("articleText") else ""
    return NewsArticleArgs(
        reqId=reqId, articleType=articleType, articleText=articleText
    )


def createNewsArticle(proto: NewsArticle_pb2.NewsArticle) -> NewsArticle:
    """Decode a ``NewsArticle`` proto directly into the domain dataclass."""
    args = createNewsArticleArgs(proto)
    return NewsArticle(args.articleType, args.articleText)


def createNewsArticleRequestProto(
    reqId: int,
    providerCode: str,
    articleId: str,
    newsArticleOptions: list[TagValue] | None = None,
) -> NewsArticleRequest_pb2.NewsArticleRequest:
    """Build a ``NewsArticleRequest`` envelope.

    ``newsArticleOptions`` is the documented TagValue trailer the binary
    path sends as a single concatenated string after ``articleId``. The
    proto wire spells it ``newsArticleOptions`` (a
    ``map<string, string>``); empty / ``None`` leaves the field unset —
    matching IBKR's ``client_utils.createNewsArticleRequestProto``.
    """
    proto = NewsArticleRequest_pb2.NewsArticleRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    if providerCode:
        proto.providerCode = providerCode
    if articleId:
        proto.articleId = articleId
    fill_tag_value_map(newsArticleOptions, proto.newsArticleOptions)
    return proto


# ---------------------------------------------------------------------------
# HistoricalNews (msgId 86) + HistoricalNewsEnd (msgId 87) + request
# ---------------------------------------------------------------------------


def createHistoricalNewsArgs(
    proto: HistoricalNews_pb2.HistoricalNews,
) -> HistoricalNewsArgs:
    """``Wrapper.historicalNews(reqId, time, providerCode, articleId, headline)`` args.

    The wrapper parses ``time`` with ``parseIBDatetime`` so the converter
    passes the raw wire string through unmodified — no datetime coercion
    here.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    time = proto.time if proto.HasField("time") else ""
    providerCode = proto.providerCode if proto.HasField("providerCode") else ""
    articleId = proto.articleId if proto.HasField("articleId") else ""
    headline = proto.headline if proto.HasField("headline") else ""
    return HistoricalNewsArgs(
        reqId=reqId,
        time=time,
        providerCode=providerCode,
        articleId=articleId,
        headline=headline,
    )


def createHistoricalNewsEndArgs(
    proto: HistoricalNewsEnd_pb2.HistoricalNewsEnd,
) -> HistoricalNewsEndArgs:
    """``Wrapper.historicalNewsEnd(reqId, hasMore)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    hasMore = proto.hasMore if proto.HasField("hasMore") else False
    return HistoricalNewsEndArgs(reqId=reqId, hasMore=hasMore)


def createHistoricalNewsRequestProto(
    reqId: int,
    conId: int,
    providerCodes: str,
    startDateTime: str,
    endDateTime: str,
    totalResults: int,
    historicalNewsOptions: list[TagValue] | None = None,
) -> HistoricalNewsRequest_pb2.HistoricalNewsRequest:
    """Build a ``HistoricalNewsRequest`` envelope.

    ``historicalNewsOptions`` is the documented TagValue trailer the
    binary path sends after ``totalResults``. The proto wire spells it
    ``historicalNewsOptions`` (a ``map<string, string>``); empty /
    ``None`` leaves the field unset — matching IBKR's
    ``client_utils.createHistoricalNewsRequestProto``.
    """
    proto = HistoricalNewsRequest_pb2.HistoricalNewsRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    if conId != UNSET_INTEGER:
        proto.conId = conId
    if providerCodes:
        proto.providerCodes = providerCodes
    if startDateTime:
        proto.startDateTime = startDateTime
    if endDateTime:
        proto.endDateTime = endDateTime
    if totalResults != UNSET_INTEGER:
        proto.totalResults = totalResults
    fill_tag_value_map(historicalNewsOptions, proto.historicalNewsOptions)
    return proto


# ---------------------------------------------------------------------------
# TickNews (msgId 84 binary, dispatched to tickNews)
# ---------------------------------------------------------------------------


def createTickNewsArgs(proto: TickNews_pb2.TickNews) -> TickNewsArgs:
    """``Wrapper.tickNews(reqId, timeStamp, providerCode, articleId, headline, extraData)`` args.

    The wrapper itself synthesizes the per-reqId ``Contract`` snapshot
    that lands on the resulting ``NewsTick`` — this converter only
    produces the positional args the wrapper consumes.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    timeStamp = proto.timestamp if proto.HasField("timestamp") else 0
    providerCode = proto.providerCode if proto.HasField("providerCode") else ""
    articleId = proto.articleId if proto.HasField("articleId") else ""
    headline = proto.headline if proto.HasField("headline") else ""
    extraData = proto.extraData if proto.HasField("extraData") else ""
    return TickNewsArgs(
        reqId=reqId,
        timeStamp=timeStamp,
        providerCode=providerCode,
        articleId=articleId,
        headline=headline,
        extraData=extraData,
    )


def createNewsTick(proto: TickNews_pb2.TickNews) -> NewsTick:
    """Decode a ``TickNews`` proto directly into the domain ``NewsTick``.

    The contract field is left as ``None`` here — the wrapper attaches
    its per-reqId snapshot when it receives the args. Tests that need a
    full ``NewsTick`` with contract populate ``contract=`` themselves.
    """
    args = createTickNewsArgs(proto)
    return NewsTick(
        args.timeStamp, args.providerCode, args.articleId, args.headline, args.extraData
    )


# ---------------------------------------------------------------------------
# WshMetaData (msgId 104 receive) + request / cancel
# ---------------------------------------------------------------------------


def createWshMetaDataArgs(proto: WshMetaData_pb2.WshMetaData) -> WshMetaDataArgs:
    """``Wrapper.wshMetaData(reqId, dataJson)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    dataJson = proto.dataJson if proto.HasField("dataJson") else ""
    return WshMetaDataArgs(reqId=reqId, dataJson=dataJson)


def createWshMetaDataRequestProto(
    reqId: int,
) -> WshMetaDataRequest_pb2.WshMetaDataRequest:
    proto = WshMetaDataRequest_pb2.WshMetaDataRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


def createCancelWshMetaDataProto(
    reqId: int,
) -> CancelWshMetaData_pb2.CancelWshMetaData:
    proto = CancelWshMetaData_pb2.CancelWshMetaData()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# WshEventData (msgId 105 receive) + request / cancel
# ---------------------------------------------------------------------------


def createWshEventDataArgs(proto: WshEventData_pb2.WshEventData) -> WshEventDataArgs:
    """``Wrapper.wshEventData(reqId, dataJson)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    dataJson = proto.dataJson if proto.HasField("dataJson") else ""
    return WshEventDataArgs(reqId=reqId, dataJson=dataJson)


def createWshEventDataRequestProto(
    reqId: int, data: WshEventData
) -> WshEventDataRequest_pb2.WshEventDataRequest:
    """Build a ``WshEventDataRequest`` from a domain ``WshEventData``.

    Every field on the domain dataclass is written into the proto —
    including the bool flags (``fillWatchlist``, ``fillPortfolio``,
    ``fillCompetitors``) whose proto3 default would otherwise silently
    swallow a ``True`` if we relied on default-skipping.
    """
    proto = WshEventDataRequest_pb2.WshEventDataRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    # ``conId`` and ``totalLimit`` default to ``None`` on the domain
    # ``WshEventData`` dataclass — the universal unset marker. Writing
    # the field with no user-supplied value would have IBKR's server
    # interpret a sentinel as a real contract id and reject the
    # subscription. Skip the write when the domain value is ``None``,
    # mirroring IBKR's ``isValidIntValue`` gating from
    # ``client_utils.createWshEventDataRequestProto``.
    if data.conId is not None:
        proto.conId = data.conId
    if data.filter:
        proto.filter = data.filter
    if data.fillWatchlist:
        proto.fillWatchlist = data.fillWatchlist
    if data.fillPortfolio:
        proto.fillPortfolio = data.fillPortfolio
    if data.fillCompetitors:
        proto.fillCompetitors = data.fillCompetitors
    if data.startDate:
        proto.startDate = data.startDate
    if data.endDate:
        proto.endDate = data.endDate
    if data.totalLimit is not None:
        proto.totalLimit = data.totalLimit
    return proto


def createCancelWshEventDataProto(
    reqId: int,
) -> CancelWshEventData_pb2.CancelWshEventData:
    proto = CancelWshEventData_pb2.CancelWshEventData()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto
