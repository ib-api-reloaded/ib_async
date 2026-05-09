"""Cancellation must fully unregister the reqId from the ticker maps.

A leak in the reqId -> Ticker map would cause two problems:
  - unbounded growth of reqId2Ticker over the life of the connection
  - late ticks delivered for a cancelled reqId would still mutate the
    (logically unsubscribed) Ticker
"""

import ib_async as ibi


def test_end_ticker_pops_reqid_to_ticker():
    ib = ibi.IB()
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 12345
    reqId = 7

    ticker = ib.wrapper.startTicker(reqId, contract, "mktData")
    assert ib.wrapper.reqId2Ticker[reqId] is ticker
    assert ib.wrapper.ticker2ReqId["mktData"][ticker] == reqId
    assert ib.wrapper._reqId2Contract[reqId] is contract

    returnedReqId = ib.wrapper.endTicker(ticker, "mktData")
    assert returnedReqId == reqId
    assert reqId not in ib.wrapper.reqId2Ticker
    assert ticker not in ib.wrapper.ticker2ReqId["mktData"]
    assert reqId not in ib.wrapper._reqId2Contract


def test_late_tick_after_cancel_is_dropped():
    ib = ibi.IB()
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 12345
    reqId = 8

    ticker = ib.wrapper.startTicker(reqId, contract, "mktData")
    ib.wrapper.endTicker(ticker, "mktData")

    # A stray priceSizeTick after cancel must be a no-op, not silently
    # mutate the now-unsubscribed Ticker. The handler does an early-return
    # via reqId2Ticker.get(reqId), so neither bid nor pendingTickers move.
    ib.wrapper.priceSizeTick(reqId, 1, 123.45, 100)
    assert ticker not in ib.wrapper.pendingTickers
