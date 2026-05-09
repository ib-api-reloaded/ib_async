"""Unit tests for ib_async._subscriptions.SubscriptionRegistry.

Stage D scope: scaffolding only. The registry exists, supports the full
add/lookup/close lifecycle, and Wrapper holds a fresh instance after
``reset()``. Subsequent stages migrate the actual IB.req* / cancel*
paths to use it.
"""

from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._subscriptions import (
    MktDataSub,
    MktDepthSub,
    PnLSingleSub,
    PnLSub,
    RealTimeBarsSub,
    ScannerSub,
    SubscriptionRegistry,
    TickByTickSub,
)
from ib_async.contract import Stock
from ib_async.objects import (
    PnL,
    PnLSingle,
    RealTimeBarList,
    ScanDataList,
)
from ib_async.ticker import Ticker

# ---- helpers ---------------------------------------------------------------


def _stock(conId: int) -> Stock:
    s = Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


def _ticker(contract) -> Ticker:
    return Ticker(contract=contract, defaults=ibi.IBDefaults())


def _registry_with_mock_client():
    """Build a registry whose close() will route cancels to a MagicMock client."""
    reg = SubscriptionRegistry()
    reg._wrapper = MagicMock()
    reg._wrapper.ib.client = MagicMock()
    return reg, reg._wrapper.ib.client


# ---- type identity ---------------------------------------------------------


def test_market_data_kind_resolves_per_class_and_per_instance():
    contract = _stock(1)
    md = MktDataSub(reqId=1, contract=contract, ticker=_ticker(contract))
    tbt = TickByTickSub(
        reqId=2, contract=contract, ticker=_ticker(contract), tickType="BidAsk"
    )
    depth = MktDepthSub(reqId=3, contract=contract, ticker=_ticker(contract))

    reg = SubscriptionRegistry()
    assert reg._market_data_kind(md) == "mktData"
    assert reg._market_data_kind(tbt) == "BidAsk"
    assert reg._market_data_kind(depth) == "mktDepth"

    bars = RealTimeBarsSub(reqId=4, contract=contract, bars=RealTimeBarList())
    assert reg._market_data_kind(bars) is None


# ---- registration ----------------------------------------------------------


def test_add_indexes_market_data_subscription():
    contract = _stock(42)
    ticker = _ticker(contract)
    sub = MktDataSub(reqId=10, contract=contract, ticker=ticker)

    reg = SubscriptionRegistry()
    reg.add(sub)

    assert reg.get_sub(10) is sub
    assert reg.get_ticker(10) is ticker
    assert reg.find_market_data(42, "mktData") is sub
    assert sub._registry is reg
    assert 10 in reg
    assert len(reg) == 1


def test_add_rejects_duplicate_reqid():
    contract = _stock(1)
    reg = SubscriptionRegistry()
    reg.add(MktDataSub(reqId=5, contract=contract, ticker=_ticker(contract)))
    with pytest.raises(KeyError):
        reg.add(MktDepthSub(reqId=5, contract=contract, ticker=_ticker(contract)))


def test_add_rejects_duplicate_market_data_pair():
    contract = _stock(7)
    reg = SubscriptionRegistry()
    reg.add(MktDataSub(reqId=11, contract=contract, ticker=_ticker(contract)))
    with pytest.raises(KeyError):
        # different reqId, but same (conId, "mktData") pair
        reg.add(MktDataSub(reqId=12, contract=contract, ticker=_ticker(contract)))


def test_add_distinguishes_tickbytick_kinds():
    contract = _stock(100)
    reg = SubscriptionRegistry()
    a = TickByTickSub(
        reqId=20, contract=contract, ticker=_ticker(contract), tickType="Last"
    )
    b = TickByTickSub(
        reqId=21, contract=contract, ticker=_ticker(contract), tickType="BidAsk"
    )
    reg.add(a)
    reg.add(b)
    assert reg.find_market_data(100, "Last") is a
    assert reg.find_market_data(100, "BidAsk") is b


def test_add_indexes_pnl_subscriptions():
    reg = SubscriptionRegistry()
    pnl_sub = PnLSub(
        reqId=30,
        contract=_stock(0),
        pnl=PnL(account="DU1", modelCode=""),
        account="DU1",
        modelCode="",
    )
    pnl_single_sub = PnLSingleSub(
        reqId=31,
        contract=_stock(0),
        pnlSingle=PnLSingle(account="DU1", modelCode="", conId=42),
        account="DU1",
        modelCode="",
        conId=42,
    )
    reg.add(pnl_sub)
    reg.add(pnl_single_sub)
    assert reg.get_pnl("DU1", "") is pnl_sub
    assert reg.get_pnl_single("DU1", "", 42) is pnl_single_sub


# ---- close -----------------------------------------------------------------


def test_close_sends_cancel_and_unregisters():
    reg, client = _registry_with_mock_client()
    contract = _stock(1)
    sub = MktDataSub(reqId=50, contract=contract, ticker=_ticker(contract))
    reg.add(sub)

    sub.close()

    client.cancelMktData.assert_called_once_with(50)
    assert sub.closed is True
    assert sub._registry is None
    assert reg.get_sub(50) is None
    assert reg.get_ticker(50) is None
    assert reg.find_market_data(1, "mktData") is None


def test_close_is_idempotent():
    reg, client = _registry_with_mock_client()
    contract = _stock(1)
    sub = MktDepthSub(reqId=51, contract=contract, ticker=_ticker(contract))
    reg.add(sub)

    sub.close()
    sub.close()  # second call must not raise or re-cancel
    sub.close()

    client.cancelMktDepth.assert_called_once_with(51, False)


def test_close_with_send_cancel_false_skips_client_call():
    reg, client = _registry_with_mock_client()
    contract = _stock(1)
    sub = MktDataSub(reqId=52, contract=contract, ticker=_ticker(contract))
    reg.add(sub)

    sub.close(send_cancel=False)

    client.cancelMktData.assert_not_called()
    assert reg.get_sub(52) is None


def test_close_skips_cancel_for_snapshot_mktdata():
    reg, client = _registry_with_mock_client()
    contract = _stock(1)
    sub = MktDataSub(
        reqId=53, contract=contract, ticker=_ticker(contract), snapshot=True
    )
    reg.add(sub)

    sub.close()

    # Snapshots auto-complete; cancel must NOT be sent.
    client.cancelMktData.assert_not_called()
    assert sub.closed is True


def test_close_sets_done_on_realtime_bars_update_event():
    reg, _ = _registry_with_mock_client()
    contract = _stock(1)
    bars = RealTimeBarList()
    sub = RealTimeBarsSub(reqId=60, contract=contract, bars=bars)
    reg.add(sub)

    sub.close()

    # eventkit's set_done leaves the event in a state where it raises
    # on further awaiters; we just verify the call landed by checking
    # that the event no longer accepts new connections cleanly.
    assert bars.updateEvent.done() is True


def test_close_sets_done_on_scanner_data_list():
    reg, _ = _registry_with_mock_client()
    contract = _stock(1)
    dataList = ScanDataList()
    sub = ScannerSub(reqId=61, contract=contract, dataList=dataList)
    reg.add(sub)
    sub.close()
    assert dataList.updateEvent.done() is True


def test_close_does_not_set_done_on_shared_ticker():
    """Ticker is pooled across mktData/tickByTick/mktDepth — closing one
    must not break the others' event stream."""
    reg, _ = _registry_with_mock_client()
    contract = _stock(1)
    ticker = _ticker(contract)
    md = MktDataSub(reqId=70, contract=contract, ticker=ticker)
    tbt = TickByTickSub(reqId=71, contract=contract, ticker=ticker, tickType="Last")
    reg.add(md)
    reg.add(tbt)

    md.close()

    # The shared Ticker's updateEvent must still be live for tickByTick.
    assert ticker.updateEvent.done() is False


# ---- close_all -------------------------------------------------------------


def test_close_all_drops_every_subscription():
    reg, _ = _registry_with_mock_client()
    c1, c2 = _stock(1), _stock(2)
    reg.add(MktDataSub(reqId=80, contract=c1, ticker=_ticker(c1)))
    reg.add(MktDepthSub(reqId=81, contract=c2, ticker=_ticker(c2)))
    reg.add(RealTimeBarsSub(reqId=82, contract=c1, bars=RealTimeBarList()))

    reg.close_all(send_cancel=False)

    assert len(reg) == 0
    assert reg.get_sub(80) is None
    assert reg.get_sub(81) is None
    assert reg.get_sub(82) is None


# ---- Wrapper integration ---------------------------------------------------


def test_wrapper_has_fresh_subscription_registry():
    ib = ibi.IB()
    assert isinstance(ib.wrapper.subscriptions, SubscriptionRegistry)
    assert len(ib.wrapper.subscriptions) == 0


def test_wrapper_reset_replaces_subscription_registry():
    ib = ibi.IB()
    first = ib.wrapper.subscriptions
    contract = _stock(1)
    first.add(MktDataSub(reqId=90, contract=contract, ticker=_ticker(contract)))
    assert len(first) == 1

    ib.wrapper.reset()
    assert ib.wrapper.subscriptions is not first
    assert len(ib.wrapper.subscriptions) == 0
