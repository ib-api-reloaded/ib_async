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

import pytest

import ib_async as ibi
from ib_async._requests import SingletonKey
from ib_async.order import Order, OrderState, OrderStatus


def _completed(
    ib: ibi.IB,
    permId: int,
    status: str,
    clientId: int = 169,
    completedStatus: str = "",
):
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 100 + permId
    order = Order(orderId=9000 + permId, permId=permId, clientId=clientId)
    ib.wrapper.requests.open(SingletonKey("completedOrders"))
    ib.wrapper.completedOrder(
        contract, order, OrderState(status=status, completedStatus=completedStatus)
    )
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


# TWS API 10.51 fills ``completedStatus`` with descriptive text and
# leaves ``status`` empty; these cases mirror that wire shape.
TWS_1051_PHRASINGS = [
    ("Filled Size: 10", OrderStatus.Filled),
    ("Filled Size: 0.5", OrderStatus.Filled),
    ("Filled Size: 1,000", OrderStatus.Filled),
    ("Cancelled by Trader", OrderStatus.Cancelled),
    (
        "Cancelled by System:\nCancel parent on new cancelling order",
        OrderStatus.Cancelled,
    ),
]


@pytest.mark.parametrize(("text", "terminal"), TWS_1051_PHRASINGS)
def test_terminal_from_completed_maps_tws_1051_phrasings(text, terminal):
    assert OrderStatus.terminalFromCompleted(text) == terminal


@pytest.mark.parametrize("status", sorted(OrderStatus.DoneStates))
def test_terminal_from_completed_keeps_plain_done_states(status):
    assert OrderStatus.terminalFromCompleted(status) == status


@pytest.mark.parametrize(
    "text",
    ["", "Submitted", "SomeNewBrokerStatus", "Filled Size:", "Cancelled by "],
)
def test_terminal_from_completed_rejects_everything_else(text):
    assert OrderStatus.terminalFromCompleted(text) is None


@pytest.mark.parametrize(("text", "terminal"), TWS_1051_PHRASINGS)
def test_tws_1051_completed_status_text_reports_its_terminal_state(
    caplog, text, terminal
):
    ib = ibi.IB()
    trade = _completed(ib, 50, status="", completedStatus=text)

    assert trade.isDone()
    assert trade.orderStatus.status == terminal
    assert trade not in ib.openTrades()
    assert "reported non-terminal status" not in caplog.text
    assert any(f"raw status {text!r}" in entry.message for entry in trade.log)


def test_tws_1051_text_terminalizes_an_existing_live_trade_correctly():
    """The completed echo for an order this session already saw live
    must land on Filled, not the Inactive fallback."""
    ib = ibi.IB()
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 151
    order = Order(orderId=9051, permId=51, clientId=169)
    ib.wrapper.requests.open(SingletonKey("openOrders"))
    ib.wrapper.openOrder(9051, contract, order, OrderState(status="Submitted"))
    ib.wrapper.openOrderEnd()
    live = ib.wrapper.permId2Trade[51]

    ib.wrapper.requests.open(SingletonKey("completedOrders"))
    ib.wrapper.completedOrder(
        contract, order, OrderState(status="", completedStatus="Filled Size: 10")
    )
    ib.wrapper.completedOrdersEnd()

    assert live.orderStatus.status == OrderStatus.Filled
    assert live not in ib.openTrades()
