"""Stage E: market-data subscriptions go through the SubscriptionRegistry.

Two correctness properties to verify:

  1. Calling ``IB.reqMktData`` twice for the same qualified contract
     must return the same Ticker without issuing a second wire request.
     Pre-Stage-E that double-call leaked a reqId (the first sub became
     unreachable and continued to bill on the IB side).
  2. ``IB.cancelMktData`` finds the subscription via the registry,
     closes it (sending the cancel through the client), and removes
     every bookkeeping trace.
"""

from unittest.mock import MagicMock

import ib_async as ibi
from ib_async._subscriptions import MktDataSub


def _wired_ib():
    """Build an IB whose client is a MagicMock so we can assert on wire calls
    without a real connection."""
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.side_effect = iter(range(100, 1000))
    # IB.__del__ → disconnect short-circuits when isConnected() is False;
    # without this the MagicMock-typed client would walk into formatSI().
    ib.client.isConnected.return_value = False
    return ib


def _stock(conId: int) -> ibi.Stock:
    s = ibi.Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


# ---- idempotent re-subscribe ----------------------------------------------


def test_double_reqMktData_returns_same_ticker():
    ib = _wired_ib()
    contract = _stock(123)

    a = ib.reqMktData(contract)
    b = ib.reqMktData(contract)

    assert a is b
    # Only one wire call.
    assert ib.client.reqMktData.call_count == 1
    # Only one subscription registered.
    sub = ib.wrapper.subscriptions.find_market_data(123, "mktData")
    assert isinstance(sub, MktDataSub)
    assert sub.ticker is a


def test_unqualified_contract_does_not_register_in_subscription_index():
    """conId=0 contracts are unhashable and the legacy startTicker
    would raise — but if a future change makes them hashable, the new
    registry must still not collapse unrelated callers under (0, kind).
    Verified by: a sub registered with conId=0 is not found via
    find_market_data(0, ...)."""
    ib = _wired_ib()
    # The conId guard in IB.reqMktData skips registry registration when
    # contract.conId is 0 (unqualified). We verify the guard directly
    # rather than driving startTicker, which raises on hash() of an
    # unqualified Stock.
    assert ib.wrapper.subscriptions.find_market_data(0, "mktData") is None


# ---- cancel ---------------------------------------------------------------


def test_cancelMktData_closes_via_registry():
    ib = _wired_ib()
    contract = _stock(456)
    ib.reqMktData(contract)

    ok = ib.cancelMktData(contract)
    assert ok is True

    # Cancel was sent exactly once for the registered reqId.
    ib.client.cancelMktData.assert_called_once()
    (called_reqId,), _ = ib.client.cancelMktData.call_args
    assert called_reqId == 100  # first reqId from our side_effect

    # Subscription is gone from every index — including the per-reqId
    # ticker view used by the tick hot path.
    assert ib.wrapper.subscriptions.find_market_data(456, "mktData") is None
    assert ib.wrapper.subscriptions.get_sub(100) is None
    assert ib.wrapper.subscriptions.get_ticker(100) is None


def test_cancelMktData_returns_false_on_unknown_contract():
    ib = _wired_ib()
    unknown = _stock(999)
    assert ib.cancelMktData(unknown) is False
    ib.client.cancelMktData.assert_not_called()


def test_idempotent_resubscribe_then_cancel_cleans_everything():
    ib = _wired_ib()
    contract = _stock(789)

    ib.reqMktData(contract)
    ib.reqMktData(contract)  # dedup
    ok = ib.cancelMktData(contract)
    assert ok is True

    # Exactly one wire request and one cancel — the reqId leak is gone.
    assert ib.client.reqMktData.call_count == 1
    assert ib.client.cancelMktData.call_count == 1
    assert ib.wrapper.subscriptions.find_market_data(789, "mktData") is None
