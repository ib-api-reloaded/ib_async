"""News objects converter."""

from datetime import datetime
from typing import cast

from ..contract import TagValue
from ..objects import HistoricalNews, NewsArticle, NewsBulletin, NewsProvider, NewsTick
from ..protobuf.CancelNewsBulletins_pb2 import (
    CancelNewsBulletins as CancelNewsBulletinsProto,
)
from ..protobuf.HistoricalNews_pb2 import HistoricalNews as HistoricalNewsProto
from ..protobuf.HistoricalNewsRequest_pb2 import (
    HistoricalNewsRequest as HistoricalNewsRequestProto,
)
from ..protobuf.NewsArticle_pb2 import NewsArticle as NewsArticleProto
from ..protobuf.NewsArticleRequest_pb2 import (
    NewsArticleRequest as NewsArticleRequestProto,
)
from ..protobuf.NewsBulletin_pb2 import NewsBulletin as NewsBulletinProto
from ..protobuf.NewsBulletinsRequest_pb2 import (
    NewsBulletinsRequest as NewsBulletinsRequestProto,
)
from ..protobuf.NewsProviders_pb2 import NewsProviders as NewsProvidersProto
from ..protobuf.NewsProvidersRequest_pb2 import (
    NewsProvidersRequest as NewsProvidersRequestProto,
)
from ..protobuf.TickNews_pb2 import TickNews as TickNewsProto
from ..protobuf_converters.base_converters import fillTagValueList
from ..util import EPOCH, isValidIntValue, parseIBDatetime


def createNewsBulletinsRequestProto(allMessages: bool) -> NewsBulletinsRequestProto:
    newsBulletinsRequestProto = NewsBulletinsRequestProto()
    if allMessages:
        newsBulletinsRequestProto.allMessages = allMessages
    return newsBulletinsRequestProto


def createCancelNewsBulletinsProto() -> CancelNewsBulletinsProto:
    cancelNewsBulletinsProto = CancelNewsBulletinsProto()
    return cancelNewsBulletinsProto


def createNewsBulletin(newsBulletinProto: NewsBulletinProto) -> NewsBulletin:
    msgId = (
        newsBulletinProto.newsMsgId if newsBulletinProto.HasField("newsMsgId") else 0
    )
    msgType = (
        newsBulletinProto.newsMsgType
        if newsBulletinProto.HasField("newsMsgType")
        else 0
    )
    message = (
        newsBulletinProto.newsMessage
        if newsBulletinProto.HasField("newsMessage")
        else ""
    )
    originExch = (
        newsBulletinProto.originatingExch
        if newsBulletinProto.HasField("originatingExch")
        else ""
    )

    return NewsBulletin(msgId, msgType, message, originExch)


def createNewsProvidersRequestProto() -> NewsProvidersRequestProto:
    newsProvidersRequestProto = NewsProvidersRequestProto()
    return newsProvidersRequestProto


def createNewsArticleRequestProto(
    reqId: int,
    providerCode: str,
    articleId: str,
    newsArticleOptionsList: list[TagValue],
) -> NewsArticleRequestProto:
    newsArticleRequestProto = NewsArticleRequestProto()
    if isValidIntValue(reqId):
        newsArticleRequestProto.reqId = reqId
    if providerCode:
        newsArticleRequestProto.providerCode = providerCode
    if articleId:
        newsArticleRequestProto.articleId = articleId
    fillTagValueList(newsArticleOptionsList, newsArticleRequestProto.newsArticleOptions)
    return newsArticleRequestProto


def createHistoricalNewsRequestProto(
    reqId: int,
    conId: int,
    providerCodes: str,
    startDateTime: str,
    endDateTime: str,
    totalResults: int,
    historicalNewsOptionsList: list[TagValue],
) -> HistoricalNewsRequestProto:
    historicalNewsRequestProto = HistoricalNewsRequestProto()
    if isValidIntValue(reqId):
        historicalNewsRequestProto.reqId = reqId
    if isValidIntValue(conId):
        historicalNewsRequestProto.conId = conId
    if providerCodes:
        historicalNewsRequestProto.providerCodes = providerCodes
    if startDateTime:
        historicalNewsRequestProto.startDateTime = startDateTime
    if endDateTime:
        historicalNewsRequestProto.endDateTime = endDateTime
    if isValidIntValue(totalResults):
        historicalNewsRequestProto.totalResults = totalResults
    fillTagValueList(
        historicalNewsOptionsList, historicalNewsRequestProto.historicalNewsOptions
    )
    return historicalNewsRequestProto


def createNewProviders(newsProvidersProto: NewsProvidersProto) -> list[NewsProvider]:
    newsProviders = []
    if newsProvidersProto.newsProviders:
        for newsProviderProto in newsProvidersProto.newsProviders:
            code = (
                newsProviderProto.providerCode
                if newsProviderProto.HasField("providerCode")
                else ""
            )
            name = (
                newsProviderProto.providerName
                if newsProviderProto.HasField("providerName")
                else ""
            )
            newsProvider = NewsProvider(code, name)
            newsProviders.append(newsProvider)
    return newsProviders


def createNewsArticle(newsArticleProto: NewsArticleProto) -> NewsArticle:
    articleType = (
        newsArticleProto.articleType if newsArticleProto.HasField("articleType") else 0
    )
    articleText = (
        newsArticleProto.articleText if newsArticleProto.HasField("articleText") else ""
    )
    return NewsArticle(articleType, articleText)


def createHistoricalNews(historicalNewsProto: HistoricalNewsProto) -> HistoricalNews:
    time = (
        parseIBDatetime(historicalNewsProto.time)
        if historicalNewsProto.HasField("time")
        else EPOCH
    )
    time = cast(datetime, time)
    providerCode = (
        historicalNewsProto.providerCode
        if historicalNewsProto.HasField("providerCode")
        else ""
    )
    articleId = (
        historicalNewsProto.articleId
        if historicalNewsProto.HasField("articleId")
        else ""
    )
    headline = (
        historicalNewsProto.headline if historicalNewsProto.HasField("headline") else ""
    )
    return HistoricalNews(time, providerCode, articleId, headline)


def createTickNews(tickNewsProto: TickNewsProto) -> NewsTick:
    timestamp = tickNewsProto.timestamp if tickNewsProto.HasField("timestamp") else 0
    providerCode = (
        tickNewsProto.providerCode if tickNewsProto.HasField("providerCode") else ""
    )
    articleId = tickNewsProto.articleId if tickNewsProto.HasField("articleId") else ""
    headline = tickNewsProto.headline if tickNewsProto.HasField("headline") else ""
    extraData = tickNewsProto.extraData if tickNewsProto.HasField("extraData") else ""
    return NewsTick(timestamp, providerCode, articleId, headline, extraData)
