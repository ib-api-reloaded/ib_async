"""whatIf order responses must resolve the future opened by IB.whatIfOrderAsync.

The whatIf flow is:

  1. ``IB.whatIfOrderAsync`` opens a request keyed on the orderId and
     sends ``placeOrder(orderId, contract, whatIfOrder)``.
  2. IB responds via ``openOrder`` with ``order.whatIf=True`` and a
     populated ``initMarginChange`` on the OrderState.
  3. ``Wrapper.openOrder``'s whatIf branch settles the request.

The opener and the settler must agree on the key. The discriminated
``WhatIfKey`` keeps this flow distinct from regular reqId-keyed
requests so a stray contract-details error on the same numeric id
cannot accidentally resolve a margin-impact future.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._requests import WhatIfKey
from ib_async.order import Order, OrderState


def _wired_ib():
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.return_value = 555
    ib.client.isConnected.return_value = False
    ib.wrapper.clientId = 0
    return ib


def test_whatIf_response_settles_future():
    ib = _wired_ib()
    contract = ibi.Stock("ABC", "SMART", "USD", conId=1)
    order = ibi.MarketOrder("BUY", 100)

    future = ib.whatIfOrderAsync(contract, order)

    # Registered as WhatIfKey, not ReqIdKey.
    assert WhatIfKey(555) in ib.wrapper.requests

    # Simulate IB's openOrder callback for a whatIf response.
    twsOrder = Order(orderId=555, clientId=0, whatIf=True)
    state = OrderState(status="PreSubmitted")
    state.initMarginChange = "1234.5"
    ib.wrapper.openOrder(555, contract, twsOrder, state)

    # Future must now resolve to the OrderState with margin info.
    assert future.done()
    assert future.result() is state
    # Registry entry is gone.
    assert WhatIfKey(555) not in ib.wrapper.requests


def test_whatIf_error_settles_future():
    """Wire-level errors (e.g. 110 invalid price) must reach the whatIf
    future even though the registry has it under ``WhatIfKey``, not
    ``ReqIdKey``. The error handler resolves the wire reqId via
    ``RequestRegistry.find_by_reqid`` and settles whichever typed key
    was actually used at open time.
    """

    ib = _wired_ib()
    ib.RaiseRequestErrors = True
    contract = ibi.Stock("ABC", "SMART", "USD", conId=1)
    order = ibi.MarketOrder("BUY", 100)

    future = ib.whatIfOrderAsync(contract, order)

    # Simulate the IB error callback for an invalid price.
    ib.wrapper.error(
        reqId=555,
        errorCode=110,
        errorString="The price does not conform to the minimum price variation",
        advancedOrderRejectJson="",
    )

    assert future.done()
    with pytest.raises(ibi.RequestError) as exc_info:
        future.result()
    assert exc_info.value.code == 110
    assert WhatIfKey(555) not in ib.wrapper.requests


def test_whatIf_refusal_answers_a_refused_OrderState():
    """Under the default `RaiseRequestErrors=False` a refused preview answers
    an OrderState carrying the broker's code and reason — never the request
    registry's empty-list accumulator, which handed callers `[]` typed as
    OrderState (2026-09-29: code 201 "MARGIN CALCULATION IS NOT SUPPORTED FOR
    THIS CONTRACT" crashed a caller on `[].numeric()`).
    """
    ib = _wired_ib()
    assert ib.RaiseRequestErrors is False
    contract = ibi.Future("SPSOX", "202612", "CME", conId=815824306)
    order = ibi.LimitOrder("BUY", 1, 12812.0)
    reason = (
        "Order rejected - reason:MARGIN CALCULATION IS NOT SUPPORTED FOR THIS "
        "CONTRACT.  PRODUCT IS CURRENTLY UNAVAILABLE FOR TRADING"
    )

    future = ib.whatIfOrderAsync(contract, order)

    ib.wrapper.error(
        reqId=555,
        errorCode=201,
        errorString=reason,
        advancedOrderRejectJson="",
    )

    assert future.done()
    state = future.result()
    assert isinstance(state, OrderState)
    assert state.whatIfRefused
    assert state.whatIfErrorCode == 201
    assert state.whatIfErrorString == reason
    assert WhatIfKey(555) not in ib.wrapper.requests


def test_answered_whatIf_is_not_refused():
    assert not OrderState(initMarginChange="1234.5").whatIfRefused


@pytest.mark.parametrize("margin", ["", "1.7976931348623157E308"])
def test_whatIf_reply_without_margins_does_not_settle_request(margin):
    """TWS sends a first what-if reply without margins and a second reply
    with them. In the first reply the margin is an empty field on the
    protobuf path or the unset double on the binary path. Only the reply
    with margins settles the request."""
    ib = _wired_ib()
    contract = ibi.Stock("ABC", "SMART", "USD", conId=1)
    future = ib.whatIfOrderAsync(contract, ibi.MarketOrder("BUY", 100))
    twsOrder = Order(orderId=555, clientId=0, whatIf=True)

    ib.wrapper.openOrder(555, contract, twsOrder, OrderState(initMarginChange=margin))
    assert not future.done()

    state = OrderState(initMarginChange="1234.5")
    ib.wrapper.openOrder(555, contract, twsOrder, state)
    assert future.done() and future.result() is state
