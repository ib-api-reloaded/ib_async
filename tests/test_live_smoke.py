"""Release smoke test against a running TWS / IB Gateway paper account.

Deselected by default (``live`` marker). Run before a release with TWS or
IB Gateway logged in to a paper account and API connections enabled::

    IB_PORT=7497 uv run pytest -m live tests/test_live_smoke.py -v

It places one limit order far below the market and cancels it, so it
refuses to run unless every managed account is a paper account (account
ids starting with "D"). Environment: IB_HOST (default 127.0.0.1), IB_PORT
(default 7497), IB_CLIENT_ID (default 917).
"""

import math
import os
from collections.abc import Callable

import pytest

import ib_async as ibi

pytestmark = pytest.mark.live

HOST = os.environ.get("IB_HOST", "127.0.0.1")
PORT = int(os.environ.get("IB_PORT", "7497"))
CLIENT_ID = int(os.environ.get("IB_CLIENT_ID", "917"))


def _waitFor(ib: ibi.IB, condition: Callable[[], bool], seconds: float) -> bool:
    """Let the event loop run until ``condition()`` holds or time runs out."""
    for _ in range(math.ceil(seconds / 0.25)):
        if condition():
            return True
        ib.sleep(0.25)
    return condition()


@pytest.fixture(scope="module")
def ib():
    ib = ibi.IB()
    ib.connect(HOST, PORT, clientId=CLIENT_ID, timeout=10)
    yield ib
    ib.disconnect()


@pytest.fixture(scope="module")
def spy(ib):
    [contract] = ib.qualifyContracts(ibi.Stock("SPY", "SMART", "USD"))
    return contract


@pytest.fixture(scope="module")
def referencePrice(ib, spy) -> float:
    """A current SPY price, from delayed data where the paper account has
    no real-time subscription."""
    ib.reqMarketDataType(4)  # delayed-frozen when real-time is unavailable
    ticker = ib.reqMktData(spy)
    try:
        _waitFor(ib, lambda: (ticker.marketPrice() or ticker.close or 0) > 0, 15)
    finally:
        ib.cancelMktData(spy)
    price = ticker.marketPrice() or ticker.close
    assert price and price > 0, f"no SPY price received: {ticker}"
    return float(price)


def test_connected_with_accounts(ib):
    assert ib.isConnected()
    assert ib.client.serverVersion() >= ib.client.MinClientVersion
    assert ib.managedAccounts()


def test_server_clock(ib):
    assert ib.reqCurrentTime().year >= 2024
    if ib.client.serverVersion() >= 213:
        millis = ib.run(ib.reqCurrentTimeInMillisAsync())
        assert millis > 1_600_000_000_000


def test_market_data(referencePrice):
    assert referencePrice > 0


def test_what_if_order(ib, spy, referencePrice):
    order = ibi.LimitOrder("BUY", 1, round(referencePrice * 0.5, 2))
    state = ib.whatIfOrder(spy, order)
    assert state.initMarginAfter not in ("", None), state


def test_place_and_cancel_order(ib, spy, referencePrice):
    accounts = ib.managedAccounts()
    if not all(account.startswith("D") for account in accounts):
        pytest.skip(f"refusing to place orders on non-paper accounts {accounts}")

    order = ibi.LimitOrder("BUY", 1, round(referencePrice * 0.5, 2), tif="DAY")
    trade = ib.placeOrder(spy, order)
    accepted = {"PreSubmitted", "Submitted"}
    assert _waitFor(
        ib, lambda: trade.orderStatus.status in accepted or trade.isDone(), 15
    ), trade
    assert trade.orderStatus.status in accepted, trade.log

    ib.cancelOrder(trade.order)
    assert _waitFor(ib, trade.isDone, 15), trade
    assert trade.orderStatus.status == ibi.OrderStatus.Cancelled, trade.log

    completed = ib.reqCompletedOrders(apiOnly=True)
    match = [t for t in completed if t.order.permId == trade.order.permId]
    assert match, "cancelled order missing from completed orders"
    assert match[0].orderStatus.status == ibi.OrderStatus.Cancelled
