"""Stage J: ``Wrapper.connectionClosed`` is the single teardown path.

Every awaiter shape must be woken on disconnect — Future,
ticker.updateEvent, bars.updateEvent, scanner dataList.updateEvent,
trade.statusEvent, etc. — otherwise user code blocks forever past
the daily server-side reset.
"""

from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey, SingletonKey
from ib_async._subscriptions import (
    MktDataSub,
    PnLSub,
    RealTimeBarsSub,
    ScannerSub,
)
from ib_async.objects import PnL, RealTimeBarList, ScanDataList
from ib_async.order import Order, OrderStatus, Trade
from ib_async.ticker import Ticker


def _stock(conId: int) -> ibi.Stock:
    s = ibi.Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


# ---- requests --------------------------------------------------------------


async def test_disconnect_fails_inflight_request_futures():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("openOrders"))
    future = req.future

    ib.wrapper.connectionClosed()

    with pytest.raises(ConnectionError, match="Socket disconnect"):
        future.result()


async def test_disconnect_fails_reqid_keyed_request_futures():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7))
    future = req.future
    ib.wrapper.connectionClosed()
    with pytest.raises(ConnectionError):
        future.result()
    assert ReqIdKey(7) not in ib.wrapper.requests


# ---- subscriptions ---------------------------------------------------------


def test_disconnect_closes_realtime_bars_subscription():
    ib = ibi.IB()
    contract = _stock(1)
    bars = RealTimeBarList()
    sub = RealTimeBarsSub(reqId=10, contract=contract, bars=bars)
    ib.wrapper.subscriptions.add(sub)

    ib.wrapper.connectionClosed()

    assert sub.closed is True
    assert bars.updateEvent.done() is True
    assert ib.wrapper.subscriptions.get_sub(10) is None


def test_disconnect_closes_scanner_subscription():
    ib = ibi.IB()
    contract = _stock(1)
    dataList = ScanDataList()
    sub = ScannerSub(reqId=11, contract=contract, dataList=dataList)
    ib.wrapper.subscriptions.add(sub)

    ib.wrapper.connectionClosed()

    assert sub.closed is True
    assert dataList.updateEvent.done() is True


def test_disconnect_closes_mktdata_subscription_without_sending_cancel():
    """The socket is gone — sub.close() must NOT try to send a cancel."""
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.isConnected.return_value = False
    contract = _stock(1)
    ticker = Ticker(contract=contract, defaults=ibi.IBDefaults())
    sub = MktDataSub(reqId=12, contract=contract, ticker=ticker)
    ib.wrapper.subscriptions.add(sub)

    ib.wrapper.connectionClosed()

    ib.client.cancelMktData.assert_not_called()
    assert sub.closed is True


def test_disconnect_closes_pnl_subscription():
    ib = ibi.IB()
    pnl = PnL(account="DU1", modelCode="")
    sub = PnLSub(
        reqId=13,
        contract=ibi.contract.Contract(),
        pnl=pnl,
        account="DU1",
        modelCode="",
    )
    ib.wrapper.subscriptions.add(sub)

    ib.wrapper.connectionClosed()

    assert sub.closed is True
    assert ib.wrapper.subscriptions.get_pnl("DU1", "") is None


# ---- pooled tickers --------------------------------------------------------


def test_disconnect_sets_done_on_pooled_ticker_update_events():
    """Tickers are pooled per-contract; disconnect must wake every one."""
    ib = ibi.IB()
    contract = _stock(1)
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)

    ib.wrapper.connectionClosed()

    assert ticker.updateEvent.done() is True


# ---- trades ----------------------------------------------------------------


def test_disconnect_transitions_live_trade_to_inactive():
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = _stock(1)
    order = Order(orderId=1, clientId=0)
    trade = Trade(
        contract,
        order,
        OrderStatus(orderId=1, status=OrderStatus.Submitted),
    )
    ib.wrapper.trades[(0, 1)] = trade

    statuses: list = []
    trade.statusEvent += statuses.append

    ib.wrapper.connectionClosed()

    # Final transition delivered before set_done.
    assert trade.orderStatus.status == OrderStatus.Inactive
    assert len(statuses) == 1
    assert statuses[0].orderStatus.status == OrderStatus.Inactive
    # Audit log captured the transition.
    assert any(
        entry.message == "Disconnected" and entry.status == OrderStatus.Inactive
        for entry in trade.log
    )


def test_disconnect_does_not_overwrite_done_trade_status():
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = _stock(1)
    order = Order(orderId=2, clientId=0)
    trade = Trade(
        contract,
        order,
        OrderStatus(orderId=2, status=OrderStatus.Filled),
    )
    ib.wrapper.trades[(0, 2)] = trade

    ib.wrapper.connectionClosed()

    # Already-done trades keep their terminal status.
    assert trade.orderStatus.status == OrderStatus.Filled


def test_disconnect_sets_done_on_every_trade_event():
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = _stock(1)
    order = Order(orderId=3, clientId=0)
    trade = Trade(
        contract,
        order,
        OrderStatus(orderId=3, status=OrderStatus.Submitted),
    )
    ib.wrapper.trades[(0, 3)] = trade

    ib.wrapper.connectionClosed()

    for event in (
        trade.statusEvent,
        trade.modifyEvent,
        trade.fillEvent,
        trade.filledEvent,
        trade.commissionReportEvent,
        trade.cancelEvent,
        trade.cancelledEvent,
    ):
        assert event.done() is True


# ---- bulk teardown ---------------------------------------------------------


def test_disconnect_clears_wrapper_state():
    ib = ibi.IB()
    ib.wrapper.requests.open(SingletonKey("openOrders"))
    contract = _stock(1)
    bars = RealTimeBarList()
    ib.wrapper.subscriptions.add(
        RealTimeBarsSub(reqId=20, contract=contract, bars=bars)
    )
    ib.wrapper.subscriptions.get_or_create_ticker(contract)

    ib.wrapper.connectionClosed()

    assert len(ib.wrapper.requests) == 0
    assert len(ib.wrapper.subscriptions) == 0
    assert ib.wrapper.subscriptions.pooled_tickers() == []
    assert ib.wrapper.trades == {}
