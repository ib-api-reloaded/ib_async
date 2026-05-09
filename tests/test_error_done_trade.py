"""Late/replayed errors for already-finished orders must not mutate them.

`self.trades` is never evicted, so an error arriving for a long-finished
orderId would otherwise:
  - flip its status to ValidationError on the warning branch
  - set its `advancedError` on the error branch

Both are wrong: a Filled or Cancelled order is final.
"""

import ib_async as ibi
from ib_async.order import Order, OrderState, OrderStatus, Trade


def _doneTrade(ib, *, orderId=1, permId=42, status=OrderStatus.Filled):
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 12345
    order = Order(orderId=orderId, clientId=ib.wrapper.clientId, permId=permId)
    orderStatus = OrderStatus(orderId=orderId, status=status)
    trade = Trade(contract, order, orderStatus, [], [])
    ib.wrapper.trades[(ib.wrapper.clientId, orderId)] = trade
    return trade


def test_warning_error_does_not_mutate_filled_trade():
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    trade = _doneTrade(ib, orderId=1, status=OrderStatus.Filled)

    # 105 is in the warning code set
    ib.wrapper.error(reqId=1, errorCode=105, errorString="late warning",
                     advancedOrderRejectJson="")

    assert trade.orderStatus.status == OrderStatus.Filled
    assert trade.log == []


def test_error_does_not_set_advancedError_on_cancelled_trade():
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    trade = _doneTrade(ib, orderId=2, status=OrderStatus.Cancelled)
    assert trade.advancedError == ""

    # 201 is a non-warning order error code
    ib.wrapper.error(reqId=2, errorCode=201, errorString="late reject",
                     advancedOrderRejectJson='{"foo":"bar"}')

    assert trade.advancedError == ""
    assert trade.orderStatus.status == OrderStatus.Cancelled


def test_warning_error_still_mutates_live_trade():
    """Sanity: the live-trade path must remain intact."""
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    trade = _doneTrade(ib, orderId=3, status=OrderStatus.Submitted)

    ib.wrapper.error(reqId=3, errorCode=105, errorString="live warning",
                     advancedOrderRejectJson="")

    assert trade.orderStatus.status == OrderStatus.ValidationError
    assert len(trade.log) == 1
