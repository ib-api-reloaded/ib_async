"""Single-flight semantics for globally-keyed wrapper requests.

Concurrent callers of requests keyed by a fixed string (``"openOrders"``,
``"completedOrders"``, ``"positions"``, ...) share one request: it is sent
once, and its one answer settles every caller's own future.
"""

from __future__ import annotations

import asyncio

import pytest

import ib_async as ibi
from ib_async._requests import SingletonKey
from ib_async.order import Order, OrderState

pytestmark = pytest.mark.asyncio


async def test_open_orders_concurrent_callers_share_one_answer():
    ib = ibi.IB()
    s1 = ib.wrapper.requests.share(SingletonKey("openOrders"))
    s2 = ib.wrapper.requests.share(SingletonKey("openOrders"))

    assert (s1.isNew, s2.isNew) == (True, False)
    f1, f2 = s1.future, s2.future
    assert f1 is not f2

    contract = ibi.Stock("ABC", "SMART", "USD")
    order = Order(orderId=1, clientId=0, permId=42)
    orderState = OrderState(status="Submitted")
    ib.wrapper.openOrder(1, contract, order, orderState)
    ib.wrapper.openOrderEnd()

    # Both callers resolve from the single end-of-stream callback.
    r1, r2 = await asyncio.gather(f1, f2)
    assert r1 is r2
    assert len(r1) == 1
    assert r1[0].order.permId == 42


async def test_completed_orders_concurrent_callers_share_one_answer():
    ib = ibi.IB()
    s1 = ib.wrapper.requests.share(SingletonKey("completedOrders"))
    s2 = ib.wrapper.requests.share(SingletonKey("completedOrders"))

    assert (s1.isNew, s2.isNew) == (True, False)
    f1, f2 = s1.future, s2.future

    contract = ibi.Stock("ABC", "SMART", "USD")
    order = Order(orderId=2, clientId=0, permId=99)
    orderState = OrderState(status="Filled")
    ib.wrapper.completedOrder(contract, order, orderState)
    ib.wrapper.completedOrdersEnd()

    r1, r2 = await asyncio.gather(f1, f2)
    assert r1 is r2
    assert len(r1) == 1
    assert r1[0].order.permId == 99


async def test_a_request_is_sent_again_after_it_settles():
    """After a request settles, the next caller starts a fresh request."""
    ib = ibi.IB()
    s1 = ib.wrapper.requests.share(SingletonKey("positions"))
    assert s1.isNew is True
    ib.wrapper.positionEnd()
    await s1.future

    s2 = ib.wrapper.requests.share(SingletonKey("positions"))
    assert s2.isNew is True
    assert s2.future is not s1.future
