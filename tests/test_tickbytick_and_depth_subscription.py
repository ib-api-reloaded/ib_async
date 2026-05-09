"""Stage F: tick-by-tick and market-depth subscriptions go through the
SubscriptionRegistry the same way mktData does after Stage E.

  * Double subscribe to the same (contract, kind) returns the existing
    Ticker — no second wire request, no leaked reqId.
  * Distinct tick-by-tick kinds for the same contract coexist (Last,
    AllLast, BidAsk, MidPoint).
  * Cancel finds the subscription via the registry, sends the cancel
    via the IB client, and removes every bookkeeping trace.
"""

from unittest.mock import MagicMock

import ib_async as ibi
from ib_async._subscriptions import MktDepthSub, TickByTickSub


def _wired_ib():
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.side_effect = iter(range(200, 1000))
    ib.client.isConnected.return_value = False
    return ib


def _stock(conId: int) -> ibi.Stock:
    s = ibi.Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


# ---- tick-by-tick ---------------------------------------------------------


def test_double_reqTickByTickData_returns_same_ticker():
    ib = _wired_ib()
    contract = _stock(11)

    a = ib.reqTickByTickData(contract, "Last")
    b = ib.reqTickByTickData(contract, "Last")

    assert a is b
    assert ib.client.reqTickByTickData.call_count == 1
    sub = ib.wrapper.subscriptions.find_market_data(11, "Last")
    assert isinstance(sub, TickByTickSub)
    assert sub.tickType == "Last"


def test_distinct_tickbytick_kinds_coexist():
    ib = _wired_ib()
    contract = _stock(12)

    last = ib.reqTickByTickData(contract, "Last")
    bidask = ib.reqTickByTickData(contract, "BidAsk")

    # The same Ticker is pooled per-contract — different reqIds, different
    # kinds, but one underlying Ticker.
    assert last is bidask
    assert ib.client.reqTickByTickData.call_count == 2
    assert ib.wrapper.subscriptions.find_market_data(12, "Last") is not None
    assert ib.wrapper.subscriptions.find_market_data(12, "BidAsk") is not None


def test_cancelTickByTickData_closes_via_registry():
    ib = _wired_ib()
    contract = _stock(13)
    ib.reqTickByTickData(contract, "BidAsk")

    ok = ib.cancelTickByTickData(contract, "BidAsk")
    assert ok is True

    ib.client.cancelTickByTickData.assert_called_once()
    assert ib.wrapper.subscriptions.find_market_data(13, "BidAsk") is None
    # Other kinds (none in this test) untouched: registry has no
    # tickByTick entries left for this contract.
    assert ib.wrapper.subscriptions.find_market_data(13, "Last") is None


def test_cancelTickByTickData_only_kills_matching_kind():
    """Closing one tickByTick subscription must not affect another
    kind on the same contract."""
    ib = _wired_ib()
    contract = _stock(14)
    ib.reqTickByTickData(contract, "Last")
    ib.reqTickByTickData(contract, "BidAsk")

    ib.cancelTickByTickData(contract, "Last")

    assert ib.wrapper.subscriptions.find_market_data(14, "Last") is None
    assert ib.wrapper.subscriptions.find_market_data(14, "BidAsk") is not None
    assert ib.client.cancelTickByTickData.call_count == 1


# ---- market depth ---------------------------------------------------------


def test_double_reqMktDepth_returns_same_ticker():
    ib = _wired_ib()
    contract = _stock(21)

    a = ib.reqMktDepth(contract)
    b = ib.reqMktDepth(contract)

    assert a is b
    assert ib.client.reqMktDepth.call_count == 1
    sub = ib.wrapper.subscriptions.find_market_data(21, "mktDepth")
    assert isinstance(sub, MktDepthSub)


def test_cancelMktDepth_closes_via_registry_and_clears_dom():
    ib = _wired_ib()
    contract = _stock(22)
    ticker = ib.reqMktDepth(contract, isSmartDepth=True)
    # Seed the DOM lists so we can verify the cancel-time clearing.
    ticker.domBids.append(object())
    ticker.domAsks.append(object())
    ticker.domBidsDict[0] = object()
    ticker.domAsksDict[0] = object()

    ib.cancelMktDepth(contract, isSmartDepth=True)

    ib.client.cancelMktDepth.assert_called_once()
    (called_reqId, called_smart), _ = ib.client.cancelMktDepth.call_args
    assert called_smart is True
    assert ib.wrapper.subscriptions.find_market_data(22, "mktDepth") is None
    # DOM state cleared on cancel.
    assert ticker.domBids == []
    assert ticker.domAsks == []
    assert ticker.domBidsDict == {}
    assert ticker.domAsksDict == {}


def test_mktdata_and_mktdepth_can_coexist_on_same_contract():
    """Different kinds on the same contract are independently tracked,
    and a Ticker pool is shared so both subscriptions feed one Ticker."""
    ib = _wired_ib()
    contract = _stock(31)

    md_ticker = ib.reqMktData(contract)
    depth_ticker = ib.reqMktDepth(contract)

    assert md_ticker is depth_ticker
    assert ib.wrapper.subscriptions.find_market_data(31, "mktData") is not None
    assert ib.wrapper.subscriptions.find_market_data(31, "mktDepth") is not None

    ib.cancelMktData(contract)
    assert ib.wrapper.subscriptions.find_market_data(31, "mktData") is None
    assert ib.wrapper.subscriptions.find_market_data(31, "mktDepth") is not None
