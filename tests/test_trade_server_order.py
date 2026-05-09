"""Stage I: ``Trade.serverOrder`` is the raw TWS-authored snapshot of
the most recent ``openOrder`` callback.

Why this exists: ``trade.order`` is updated via the
``MUTABLE_ORDER_FIELDS`` allowlist so user-set fields aren't clobbered
by TWS placeholders. Any TWS field that isn't in the allowlist is
silently dropped from ``trade.order`` until the allowlist grows.
``trade.serverOrder`` always carries the full snapshot (with ``?``
placeholders stripped), so callers who need a yet-to-be-allowlisted
field can still reach it.
"""

import ib_async as ibi
from ib_async.order import Order, OrderState, OrderStatus, Trade


def _stock(conId: int) -> ibi.Stock:
    s = ibi.Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


def test_serverOrder_starts_none_and_is_set_on_first_openOrder():
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = _stock(1)
    contract.conId = 1

    twsOrder = Order(orderId=1, clientId=0, permId=42, lmtPrice=100.0)
    ib.wrapper.openOrder(1, contract, twsOrder, OrderState(status="Submitted"))

    trade = ib.wrapper.trades[(0, 1)]
    assert trade.serverOrder is not None
    assert trade.serverOrder.permId == 42
    assert trade.serverOrder.lmtPrice == 100.0


def test_serverOrder_replaced_wholesale_on_subsequent_openOrder():
    """Each openOrder fully replaces serverOrder (no merge), so callers
    always see the latest TWS snapshot."""
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = _stock(1)
    contract.conId = 1

    first = Order(orderId=1, clientId=0, permId=42, lmtPrice=100.0)
    ib.wrapper.openOrder(1, contract, first, OrderState(status="Submitted"))
    trade = ib.wrapper.trades[(0, 1)]
    firstSnapshot = trade.serverOrder

    second = Order(orderId=1, clientId=0, permId=42, lmtPrice=99.0)
    ib.wrapper.openOrder(1, contract, second, OrderState(status="Submitted"))

    assert trade.serverOrder is not firstSnapshot
    assert trade.serverOrder.lmtPrice == 99.0


def test_serverOrder_strips_placeholder_values():
    """``?`` placeholders that TWS sends for unspecified fields must not
    leak into serverOrder — the same cleanup as the new-trade path."""
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = _stock(1)
    contract.conId = 1

    twsOrder = Order(orderId=1, clientId=0, permId=42)
    twsOrder.orderRef = "?"  # placeholder
    ib.wrapper.openOrder(1, contract, twsOrder, OrderState(status="Submitted"))

    trade = ib.wrapper.trades[(0, 1)]
    assert trade.serverOrder is not None
    # Field default is "" for orderRef; placeholder removed leaves the default.
    assert trade.serverOrder.orderRef == ""


def test_serverOrder_does_not_disturb_user_authored_trade_order():
    """Pre-existing trade.order semantics (allowlist merge) must not
    change just because serverOrder now exists."""
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = _stock(1)
    contract.conId = 1

    # Simulate placeOrder having seeded the trade with the user's intent.
    userOrder = Order(orderId=1, clientId=0, permId=0, lmtPrice=100.0, account="DU1")
    trade = Trade(contract, userOrder, OrderStatus(orderId=1, status="PendingSubmit"))
    ib.wrapper.trades[(0, 1)] = trade

    # TWS reports back. lmtPrice is in the allowlist; account is not.
    twsOrder = Order(orderId=1, clientId=0, permId=42, lmtPrice=99.5, account="")
    ib.wrapper.openOrder(1, contract, twsOrder, OrderState(status="Submitted"))

    # trade.order: allowlist merge — lmtPrice updated, account stays user-set.
    assert trade.order.lmtPrice == 99.5
    assert trade.order.account == "DU1"
    assert trade.order.permId == 42
    # trade.serverOrder: full TWS snapshot — has the empty account.
    assert trade.serverOrder is not None
    assert trade.serverOrder.account == ""
    assert trade.serverOrder.lmtPrice == 99.5
