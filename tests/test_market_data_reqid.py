"""``IB.marketDataReqId`` finds the request id of a live stream.

* Each streaming kind (mktData, mktDepth, the four tick-by-tick types)
  reports the reqId it was sent with, found by contract or by Ticker.
* Kinds on one contract each keep their own reqId, though they share
  one Ticker.
* A cancelled stream, a contract never subscribed, and a snapshot have
  no reqId.
* A subscription moved to a new reqId reports the new one.
* A bag is found by its legs.
* An unknown kind is refused.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async.contract import Bag, ComboLeg


def _wired_ib():
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.side_effect = iter(range(300, 1000))
    ib.client.isConnected.return_value = False
    return ib


def _stock(conId: int) -> ibi.Stock:
    s = ibi.Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


def test_each_stream_kind_reports_the_reqId_it_was_sent_with():
    ib = _wired_ib()
    contract = _stock(21)

    ticker = ib.reqMktData(contract)
    ib.reqMktDepth(contract)
    for tickType in ("Last", "AllLast", "BidAsk", "MidPoint"):
        ib.reqTickByTickData(contract, tickType)

    sent = {
        "mktData": ib.client.reqMktData.call_args.args[0],
        "mktDepth": ib.client.reqMktDepth.call_args.args[0],
    }
    for call in ib.client.reqTickByTickData.call_args_list:
        sent[call.args[2]] = call.args[0]
    assert len(set(sent.values())) == 6

    for kind, reqId in sent.items():
        assert ib.marketDataReqId(contract, kind) == reqId
        assert ib.marketDataReqId(ticker, kind) == reqId


def test_the_kind_defaults_to_mktData():
    ib = _wired_ib()
    contract = _stock(22)
    ib.reqMktData(contract)

    assert ib.marketDataReqId(contract) == ib.client.reqMktData.call_args.args[0]


def test_a_kind_never_requested_has_no_reqId():
    ib = _wired_ib()
    contract = _stock(23)
    ticker = ib.reqTickByTickData(contract, "BidAsk")

    assert ib.marketDataReqId(contract, "Last") is None
    assert ib.marketDataReqId(ticker, "mktData") is None
    assert ib.marketDataReqId(_stock(99)) is None


def test_a_cancelled_stream_has_no_reqId():
    ib = _wired_ib()
    contract = _stock(24)
    ib.reqMktData(contract)
    ib.reqMktDepth(contract)
    ib.reqTickByTickData(contract, "Last")

    ib.cancelMktData(contract)
    ib.cancelMktDepth(contract)
    ib.cancelTickByTickData(contract, "Last")

    assert ib.marketDataReqId(contract) is None
    assert ib.marketDataReqId(contract, "mktDepth") is None
    assert ib.marketDataReqId(contract, "Last") is None


def test_a_snapshot_has_no_reqId():
    ib = _wired_ib()
    contract = _stock(25)

    snapshot = ib.reqMktData(contract, snapshot=True)

    assert ib.marketDataReqId(contract) is None
    assert ib.marketDataReqId(snapshot) is None


def test_a_snapshot_ticker_is_not_matched_to_the_stream_on_its_contract():
    ib = _wired_ib()
    contract = _stock(26)
    # A snapshot taken before the stream starts has a private Ticker.
    snapshot = ib.reqMktData(contract, snapshot=True)
    stream = ib.reqMktData(contract)
    assert snapshot is not stream

    assert ib.marketDataReqId(stream) is not None
    assert ib.marketDataReqId(snapshot) is None


def test_a_moved_subscription_reports_its_new_reqId():
    ib = _wired_ib()
    contract = _stock(27)
    ib.reqMktData(contract)
    sub = ib.wrapper.subscriptions.find_market_data_for_contract(contract, "mktData")

    ib.wrapper.subscriptions.move(sub, 777)

    assert ib.marketDataReqId(contract) == 777


def test_a_bag_is_found_by_its_legs():
    ib = _wired_ib()
    legs = [ComboLeg(conId=c, ratio=1, action="BUY", exchange="SMART") for c in (1, 2)]
    bag = Bag(symbol="SPX", exchange="SMART", currency="USD", comboLegs=legs)
    other = Bag(
        symbol="SPX",
        exchange="SMART",
        currency="USD",
        comboLegs=[
            ComboLeg(conId=c, ratio=1, action="BUY", exchange="SMART") for c in (1, 3)
        ],
    )

    ib.reqMktData(bag)

    assert ib.marketDataReqId(bag) == ib.client.reqMktData.call_args.args[0]
    assert ib.marketDataReqId(other) is None


def test_an_unqualified_contract_has_no_reqId():
    ib = _wired_ib()

    assert ib.marketDataReqId(ibi.Stock("ABC", "SMART", "USD")) is None


def test_an_unknown_kind_is_refused():
    ib = _wired_ib()

    with pytest.raises(ValueError, match="tickByTick"):
        ib.marketDataReqId(_stock(28), "tickByTick")
