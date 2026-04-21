import ib_async as ibi
from ib_async import IB, Stock
from ib_async.ticker import Ticker


def test_tickNews_populates_contract_from_active_ticker():
    """When a ticker is registered for the incoming reqId (the normal
    streaming-news flow via reqMktData), the emitted NewsTick carries the
    originating contract as a typed snapshot."""
    ib = IB()
    contract = Stock("AAPL", "SMART", "USD")
    ib.wrapper.reqId2Ticker[1] = Ticker(contract=contract, defaults=ib.wrapper.defaults)

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


def test_tickNews_falls_back_to_reqId2Contract():
    """When no ticker is registered but the reqId exists in the generic
    request-contract map, the fallback lookup still populates the contract."""
    ib = IB()
    contract = Stock("MSFT", "SMART", "USD")
    ib.wrapper._reqId2Contract[42] = contract

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
