import ib_async as ibi
from ib_async import IB, Stock
from ib_async._subscriptions import MktDataSub
from ib_async.ticker import Ticker


def test_tickNews_populates_contract_from_active_ticker():
    """When a ticker is registered for the incoming reqId (the normal
    streaming-news flow via reqMktData), the emitted NewsTick carries the
    originating contract as a typed snapshot."""
    ib = IB()
    contract = Stock("AAPL", "SMART", "USD", conId=265598)
    ticker = Ticker(contract=contract, defaults=ib.wrapper.defaults)
    ib.wrapper.subscriptions.add(MktDataSub(reqId=1, contract=contract, ticker=ticker))

    captured: list[ibi.NewsTick] = []
    ib.tickNewsEvent += captured.append

    ib.wrapper.tickNews(
        1,
        1_700_000_000,
        "BRFG",
        "BRFG$abc",
        "Apple announces new chip",
        "",
    )

    assert len(captured) == 1
    news = captured[0]
    assert news.headline == "Apple announces new chip"
    assert news.contract is not None
    assert news.contract.symbol == "AAPL"
    assert news.contract.secType == "STK"
    # recreate() returns a new instance so the snapshot is independent of
    # later mutations on the original contract.
    assert news.contract is not contract


def test_tickNews_falls_back_to_request_contract():
    """When no Subscription is registered but a one-shot Request carries
    the originating contract, the fallback lookup still populates the
    contract on the emitted NewsTick."""
    from ib_async._requests import ReqIdKey

    ib = IB()
    contract = Stock("MSFT", "SMART", "USD")
    ib.wrapper.requests.open(ReqIdKey(42), contract=contract)

    captured: list[ibi.NewsTick] = []
    ib.tickNewsEvent += captured.append

    ib.wrapper.tickNews(42, 1_700_000_000, "BRFG", "BRFG$x", "Headline", "")

    assert len(captured) == 1
    assert captured[0].contract is not None
    assert captured[0].contract.symbol == "MSFT"


def test_tickNews_contract_none_when_reqId_unknown():
    """When neither map knows the reqId, the NewsTick still emits with
    contract=None rather than raising."""
    ib = IB()
    captured: list[ibi.NewsTick] = []
    ib.tickNewsEvent += captured.append

    ib.wrapper.tickNews(999, 1_700_000_000, "BRFG", "BRFG$x", "Headline", "")

    assert len(captured) == 1
    assert captured[0].contract is None


def test_tickNews_appends_to_ticker_news_deque_and_caps_at_maxlen():
    """Each ``tickNews`` for a known reqId appends a NewsTick onto the
    matching ``Ticker.news`` deque. The deque is sized so the oldest
    item rolls off automatically — bounded memory for the lifetime of
    the subscription. The global ``newsTicks`` list and
    ``tickNewsEvent`` still fire so the per-Ticker view is purely
    additive."""
    from ib_async.ticker import _NEWS_MAXLEN

    ib = IB()
    contract = Stock("NVDA", "SMART", "USD", conId=4815747)
    ticker = Ticker(contract=contract, defaults=ib.wrapper.defaults)
    ib.wrapper.subscriptions.add(MktDataSub(reqId=7, contract=contract, ticker=ticker))

    # One more than maxlen so we exercise eviction.
    overflow = _NEWS_MAXLEN + 2
    for i in range(overflow):
        ib.wrapper.tickNews(
            7, 1_700_000_000 + i, "BRFG", f"BRFG$art-{i}", f"Headline {i}", ""
        )

    # Bounded at maxlen, oldest evicted.
    assert len(ticker.news) == _NEWS_MAXLEN
    assert ticker.news[0].articleId == f"BRFG$art-{overflow - _NEWS_MAXLEN}"
    assert ticker.news[-1].articleId == f"BRFG$art-{overflow - 1}"
    # Global fan-out still received every item.
    assert len(ib.wrapper.newsTicks) == overflow


def test_tickNews_unknown_reqId_does_not_touch_any_ticker_deque():
    """Bulletin-style news with no matching Ticker leaves every Ticker's
    deque untouched. The global event still fires."""
    ib = IB()
    contract = Stock("IBM", "SMART", "USD", conId=8314)
    ticker = Ticker(contract=contract, defaults=ib.wrapper.defaults)
    ib.wrapper.subscriptions.add(MktDataSub(reqId=11, contract=contract, ticker=ticker))

    ib.wrapper.tickNews(999, 1_700_000_000, "BRFG", "BRFG$x", "Headline", "")

    assert len(ticker.news) == 0
    assert len(ib.wrapper.newsTicks) == 1


def test_priceSizeTick_writes_tickAttrib_to_ticker():
    """``priceSizeTick`` with a decoded ``TickAttrib`` writes the flags
    onto the Ticker so a holder of the Ticker reference can read
    pastLimit / preOpen / canAutoExecute without subscribing to the
    raw tick stream. Single-slot overwrite — the latest flags replace
    any prior set."""
    ib = IB()
    contract = Stock("AAPL", "SMART", "USD", conId=265598)
    ticker = Ticker(contract=contract, defaults=ib.wrapper.defaults)
    ib.wrapper.subscriptions.add(MktDataSub(reqId=3, contract=contract, ticker=ticker))

    assert ticker.tickAttrib is None

    # tickType 1 (BID) with stale-NBBO pastLimit flag.
    ib.wrapper.priceSizeTick(
        3, 1, 292.06, 120.0, ibi.TickAttrib(pastLimit=True)
    )
    assert ticker.tickAttrib is not None
    assert ticker.tickAttrib.pastLimit is True
    assert ticker.tickAttrib.preOpen is False

    # Next tick clears the stale flag — single-slot overwrite, no append.
    ib.wrapper.priceSizeTick(
        3, 2, 292.36, 40.0, ibi.TickAttrib(preOpen=True, canAutoExecute=True)
    )
    assert ticker.tickAttrib.pastLimit is False
    assert ticker.tickAttrib.preOpen is True
    assert ticker.tickAttrib.canAutoExecute is True

    # attrib=None (legacy frames pre-181) leaves the previous value intact.
    prior = ticker.tickAttrib
    ib.wrapper.priceSizeTick(3, 1, 292.05, 100.0, None)
    assert ticker.tickAttrib is prior
