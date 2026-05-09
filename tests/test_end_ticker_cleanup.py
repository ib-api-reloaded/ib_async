"""Cancellation must fully unregister the reqId from the registry.

A leak in the reqId → Ticker mapping would cause two problems:
  - unbounded growth of the mapping over the life of the connection
  - late ticks delivered for a cancelled reqId would still mutate the
    (logically unsubscribed) Ticker

The registry's flat ``ticker_by_reqid`` view (used by every tick
handler) and its ``by_market_data_key`` index (used by the cancel
path) must both be dropped on ``Subscription.close()``.
"""

import ib_async as ibi
from ib_async._subscriptions import MktDataSub


def test_subscription_close_removes_registry_ticker_view():
    """Closing a Subscription removes the per-reqId ticker view used by
    the tick hot path, so late ticks find no ticker and become no-ops."""
    ib = ibi.IB()
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 12345
    reqId = 8

    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    sub = MktDataSub(reqId=reqId, contract=contract, ticker=ticker)
    ib.wrapper.subscriptions.add(sub)

    assert ib.wrapper.subscriptions.get_ticker(reqId) is ticker
    assert ib.wrapper.subscriptions.find_market_data(12345, "mktData") is sub

    sub.close(send_cancel=False)

    assert ib.wrapper.subscriptions.get_ticker(reqId) is None
    assert ib.wrapper.subscriptions.find_market_data(12345, "mktData") is None

    # A stray priceSizeTick after cancel is a no-op via the registry's
    # early-return guard.
    ib.wrapper.priceSizeTick(reqId, 1, 123.45, 100)
    assert ticker not in ib.wrapper.pendingTickers
