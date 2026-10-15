"""Public input validation raises ValueError (asserts vanish under -O), and
unknown wire data is tolerated."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async import util
from ib_async._subscriptions import MktDataSub


def test_forex_pair_must_be_six_letters():
    assert ibi.Forex("EURUSD").symbol == "EUR"
    with pytest.raises(ValueError, match="6 letters"):
        ibi.Forex("EURUS")


def test_bracket_order_action_must_be_buy_or_sell():
    with pytest.raises(ValueError, match="BUY"):
        ibi.IB().bracketOrder("HOLD", 1, 100, 110, 90)


@pytest.mark.parametrize("step", [0, -1])
def test_time_range_step_must_be_positive(step):
    with pytest.raises(ValueError, match="positive"):
        next(util.timeRange("10:00:00", "11:00:00", step))


def test_format_si_rejects_out_of_range_values():
    with pytest.raises(ValueError, match="too large"):
        util.formatSI(1e30)


def test_unmapped_tick_types_are_skipped(caplog):
    ib = ibi.IB()
    contract = ibi.Stock("SPY", "SMART", "USD")
    contract.conId = 756733
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    ib.wrapper.subscriptions.add(MktDataSub(reqId=5, contract=contract, ticker=ticker))
    with caplog.at_level(logging.DEBUG, logger="ib_async.wrapper"):
        ib.wrapper.priceSizeTick(5, 9999, 1.0, 1, ibi.TickAttrib())
        ib.wrapper.tickSize(5, 9999, 1)
        ib.wrapper.tickGeneric(5, 9999, 1.0)
    assert sum("unmapped tickType 9999" in r.getMessage() for r in caplog.records) == 3


def test_modifying_a_finished_order_is_sent_with_a_warning(caplog):
    ib = ibi.IB()
    ib.client = MagicMock()
    contract = ibi.Stock("SPY", "SMART", "USD")
    order = ibi.LimitOrder("BUY", 1, 100, orderId=42)
    trade = ib.placeOrder(contract, order)
    trade.orderStatus.status = ibi.OrderStatus.Inactive

    with caplog.at_level(logging.WARNING, logger="ib_async.ib"):
        assert ib.placeOrder(contract, order) is trade
    assert ib.client.placeOrder.call_count == 2
    assert "already Inactive" in caplog.text
