"""Completed-order replay must never fabricate permanently-open ghost trades.

If ``reqCompletedOrders`` replay materializes Trades whose
``orderStatus.status`` is not a DoneState (unset/unrecognized
``completedStatus``), they would live in ``openTrades()``/``openOrders()``
forever — rendered as open orders no client could cancel (and with
``orderStatus.clientId`` defaulted to 0, per-client cancel matching would
skip them). The completed-orders channel is terminal BY DEFINITION: any trade
it creates or touches must satisfy ``Trade.isDone()``, preserve the raw
broker status in the trade log, and carry the owning clientId.
"""

import ib_async as ibi
from ib_async._requests import SingletonKey
from ib_async.order import Order, OrderState, OrderStatus


def _completed(ib: ibi.IB, permId: int, status: str, clientId: int = 169):
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 100 + permId
    order = Order(orderId=9000 + permId, permId=permId, clientId=clientId)
    ib.wrapper.requests.open(SingletonKey("completedOrders"))
    ib.wrapper.completedOrder(contract, order, OrderState(status=status))
    ib.wrapper.completedOrdersEnd()
    return ib.wrapper.permId2Trade[permId]


def test_unset_status_classifies_inactive_and_stays_out_of_open_trades():
    ib = ibi.IB()
    trade = _completed(ib, 42, status="")

    assert trade.isDone()
    assert trade.orderStatus.status == OrderStatus.Inactive
    assert trade not in ib.openTrades()
    assert trade in ib.trades()
    # Ground truth preserved: the raw broker status is journaled on the trade.
    assert any("raw status ''" in entry.message for entry in trade.log)


def test_unrecognized_status_classifies_inactive_with_raw_log():
    ib = ibi.IB()
    trade = _completed(ib, 43, status="SomeNewBrokerStatus")

    assert trade.isDone()
    assert trade.orderStatus.status == OrderStatus.Inactive
    assert trade not in ib.openTrades()
    assert any(
        "raw status 'SomeNewBrokerStatus'" in entry.message for entry in trade.log
    )


def test_recognized_terminal_status_is_preserved_verbatim():
    ib = ibi.IB()
    trade = _completed(ib, 44, status="Filled")

    assert trade.isDone()
    assert trade.orderStatus.status == "Filled"
    assert trade not in ib.openTrades()
    # No raw-status annotation when the broker status was already terminal.
    assert not any("raw status" in entry.message for entry in trade.log)


def test_completed_trade_carries_owning_client_id():
    ib = ibi.IB()
    trade = _completed(ib, 45, status="Cancelled", clientId=169)

    assert trade.orderStatus.clientId == 169


def test_existing_live_trade_is_normalized_terminal_by_completed_echo():
    ib = ibi.IB()
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 146
    order = Order(orderId=9046, permId=46, clientId=169)
    # A live openOrder snapshot wires up the Trade first.
    ib.wrapper.requests.open(SingletonKey("openOrders"))
    ib.wrapper.openOrder(9046, contract, order, OrderState(status="Submitted"))
    ib.wrapper.openOrderEnd()
    live = ib.wrapper.permId2Trade[46]
    assert not live.isDone()

    # The completed echo with an unrecognized status must still terminalize it.
    ib.wrapper.requests.open(SingletonKey("completedOrders"))
    ib.wrapper.completedOrder(contract, order, OrderState(status=""))
    ib.wrapper.completedOrdersEnd()

    assert live.isDone()
    assert live.orderStatus.status == OrderStatus.Inactive
    assert live not in ib.openTrades()
