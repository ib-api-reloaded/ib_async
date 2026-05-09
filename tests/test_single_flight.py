"""Single-flight semantics for globally-keyed wrapper requests.

Concurrent callers of requests keyed by a fixed string (``"openOrders"``,
``"completedOrders"``, ``"positions"``, ...) must share one in-flight
future. Without that, the second caller's ``startReq`` would overwrite the
first caller's future and the first caller would block forever on the next
end-of-stream callback.
"""

import asyncio

import pytest

import ib_async as ibi
from ib_async.order import Order, OrderState

pytestmark = pytest.mark.asyncio


async def test_open_orders_concurrent_callers_share_future():
    ib = ibi.IB()
    f1, isNew1 = ib.wrapper.startReqOrAttach("openOrders")
    f2, isNew2 = ib.wrapper.startReqOrAttach("openOrders")

    assert isNew1 is True
    assert isNew2 is False
    assert f1 is f2

    contract = ibi.Stock("ABC", "SMART", "USD")
    order = Order(orderId=1, clientId=0, permId=42)
    orderState = OrderState(status="Submitted")
    ib.wrapper.openOrder(1, contract, order, orderState)
    ib.wrapper.openOrderEnd()

    # Both attached awaiters resolve from the single end-of-stream callback.
    r1, r2 = await asyncio.gather(f1, f2)
    assert r1 is r2
    assert len(r1) == 1
    assert r1[0].order.permId == 42


async def test_completed_orders_concurrent_callers_share_future():
    ib = ibi.IB()
    f1, isNew1 = ib.wrapper.startReqOrAttach("completedOrders")
    f2, isNew2 = ib.wrapper.startReqOrAttach("completedOrders")

    assert isNew1 is True
    assert isNew2 is False
    assert f1 is f2

    contract = ibi.Stock("ABC", "SMART", "USD")
    order = Order(orderId=2, clientId=0, permId=99)
    orderState = OrderState(status="Filled")
    ib.wrapper.completedOrder(contract, order, orderState)
    ib.wrapper.completedOrdersEnd()

    r1, r2 = await asyncio.gather(f1, f2)
    assert r1 is r2
    assert len(r1) == 1
    assert r1[0].order.permId == 99


async def test_attach_reissues_after_settle():
    """After a request settles, the next caller starts a fresh request."""
    ib = ibi.IB()
    f1, isNew1 = ib.wrapper.startReqOrAttach("positions")
    assert isNew1 is True
    ib.wrapper.positionEnd()
    await f1

    f2, isNew2 = ib.wrapper.startReqOrAttach("positions")
    assert isNew2 is True
    assert f2 is not f1
