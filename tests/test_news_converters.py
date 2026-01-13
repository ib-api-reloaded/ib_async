"""
Tests for news_converters.
"""

from ib_async.contract import TagValue
from ib_async.objects import (
    HistoricalNews,
    NewsArticle,
    NewsBulletin,
    NewsProvider,
    NewsTick,
)
from ib_async.protobuf.CancelNewsBulletins_pb2 import (
    CancelNewsBulletins as CancelNewsBulletinsProto,
)
from ib_async.protobuf.HistoricalNews_pb2 import HistoricalNews as HistoricalNewsProto
from ib_async.protobuf.HistoricalNewsRequest_pb2 import (
    HistoricalNewsRequest as HistoricalNewsRequestProto,
)
from ib_async.protobuf.NewsArticle_pb2 import NewsArticle as NewsArticleProto
from ib_async.protobuf.NewsArticleRequest_pb2 import (
    NewsArticleRequest as NewsArticleRequestProto,
)
from ib_async.protobuf.NewsBulletin_pb2 import (
    NewsBulletin as NewsBulletinProto,
)
from ib_async.protobuf.NewsBulletinsRequest_pb2 import (
    NewsBulletinsRequest as NewsBulletinsRequestProto,
)
from ib_async.protobuf.NewsProviders_pb2 import (
    NewsProviders as NewsProvidersProto,
)
from ib_async.protobuf.NewsProvidersRequest_pb2 import (
    NewsProvidersRequest as NewsProvidersRequestProto,
)
from ib_async.protobuf.TickNews_pb2 import TickNews as TickNewsProto
from ib_async.protobuf_converters.news_converters import (
    createCancelNewsBulletinsProto,
    createHistoricalNews,
    createHistoricalNewsRequestProto,
    createNewProviders,
    createNewsArticle,
    createNewsArticleRequestProto,
    createNewsBulletin,
    createNewsBulletinsRequestProto,
    createNewsProvidersRequestProto,
    createTickNews,
)


class TestNewsConverters:
    def test_createNewsBulletinsRequestProto(self):
        proto = createNewsBulletinsRequestProto(True)
        assert isinstance(proto, NewsBulletinsRequestProto)
        assert proto.allMessages is True

        proto_false = createNewsBulletinsRequestProto(False)
        assert not proto_false.allMessages

    def test_createCancelNewsBulletinsProto(self):
        proto = createCancelNewsBulletinsProto()
        assert isinstance(proto, CancelNewsBulletinsProto)

    def test_createNewsBulletin(self):
        proto = NewsBulletinProto(
            newsMsgId=1,
            newsMsgType=2,
            newsMessage="Test message",
            originatingExch="NYSE",
        )
        bulletin = createNewsBulletin(proto)
        assert isinstance(bulletin, NewsBulletin)
        assert bulletin.msgId == 1
        assert bulletin.msgType == 2
        assert bulletin.message == "Test message"
        assert bulletin.origExchange == "NYSE"

    def test_createNewsProvidersRequestProto(self):
        proto = createNewsProvidersRequestProto()
        assert isinstance(proto, NewsProvidersRequestProto)

    def test_createNewsArticleRequestProto(self):
        options = [TagValue("opt1", "val1")]
        proto = createNewsArticleRequestProto(1, "BZ", "article123", options)
        assert isinstance(proto, NewsArticleRequestProto)
        assert proto.reqId == 1
        assert proto.providerCode == "BZ"
        assert proto.articleId == "article123"
        assert "opt1" in proto.newsArticleOptions
        assert proto.newsArticleOptions["opt1"] == "val1"

    def test_createHistoricalNewsRequestProto(self):
        options = [TagValue("opt2", "val2")]
        proto = createHistoricalNewsRequestProto(
            2,
            12345,
            "BZ,FLY",
            "20230101-00:00:00",
            "20230102-00:00:00",
            100,
            options,
        )
        assert isinstance(proto, HistoricalNewsRequestProto)
        assert proto.reqId == 2
        assert proto.conId == 12345
        assert proto.providerCodes == "BZ,FLY"
        assert proto.startDateTime == "20230101-00:00:00"
        assert proto.endDateTime == "20230102-00:00:00"
        assert proto.totalResults == 100
        assert "opt2" in proto.historicalNewsOptions
        assert proto.historicalNewsOptions["opt2"] == "val2"

    def test_createNewProviders(self):
        providers_proto = NewsProvidersProto()
        p1 = providers_proto.newsProviders.add()
        p1.providerCode = "BZ"
        p1.providerName = "Benzinga"
        p2 = providers_proto.newsProviders.add()
        p2.providerCode = "FLY"
        p2.providerName = "Fly on the Wall"

        providers = createNewProviders(providers_proto)
        assert isinstance(providers, list)
        assert len(providers) == 2
        assert isinstance(providers[0], NewsProvider)
        assert providers[0].code == "BZ"
        assert providers[0].name == "Benzinga"
        assert providers[1].code == "FLY"
        assert providers[1].name == "Fly on the Wall"

    def test_createNewsArticle(self):
        article_proto = NewsArticleProto(
            articleType=0, articleText="This is the article body."
        )
        article = createNewsArticle(article_proto)
        assert isinstance(article, NewsArticle)
        assert article.articleType == 0
        assert article.articleText == "This is the article body."

    def test_createHistoricalNews(self):
        news_proto = HistoricalNewsProto(
            time="2023-01-01 12:00:00.0",
            providerCode="BZ",
            articleId="news1",
            headline="Breaking News",
        )
        news = createHistoricalNews(news_proto)
        assert isinstance(news, HistoricalNews)
        assert news.providerCode == "BZ"
        assert news.articleId == "news1"
        assert news.headline == "Breaking News"

    def test_createTickNews(self):
        tick_proto = TickNewsProto(
            timestamp=1672531200,
            providerCode="RTRS",
            articleId="tick1",
            headline="Market Update",
            extraData="Extra info",
        )
        tick = createTickNews(tick_proto)
        assert isinstance(tick, NewsTick)
        assert tick.timeStamp == 1672531200
        assert tick.providerCode == "RTRS"
        assert tick.articleId == "tick1"
        assert tick.headline == "Market Update"
        assert tick.extraData == "Extra info"
