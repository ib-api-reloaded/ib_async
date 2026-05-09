"""Late-callback safety: streaming handlers must no-op after settlement.

After a request settles (its end-of-stream callback has fired), any
stray data callback for the same key must be a silent no-op rather
than a KeyError. The pre-Stage-B code at completedOrder did
``self._results["completedOrders"].append(trade)`` with no guard, so
a second wave of completedOrder events arriving after the first
completedOrdersEnd raised KeyError. The Stage-B migration through
``self.requests.append(...)`` makes this safe by construction.
"""

import ib_async as ibi
from ib_async._requests import ReqIdKey, SingletonKey
from ib_async.contract import ContractDetails
from ib_async.order import Order, OrderState


def test_completed_order_after_end_is_noop():
    ib = ibi.IB()
    ib.wrapper.requests.open(SingletonKey("completedOrders"))
    ib.wrapper.completedOrdersEnd()  # settles the request

    # Second wave arrives — must not raise.
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 1
    order = Order(orderId=1, permId=42)
    ib.wrapper.completedOrder(contract, order, OrderState(status="Filled"))


def test_open_order_after_end_emits_live_event():
    """openOrder after openOrderEnd should fire the live openOrderEvent
    instead of accumulating into the (settled) request."""
    ib = ibi.IB()
    ib.wrapper.requests.open(SingletonKey("openOrders"))
    ib.wrapper.openOrderEnd()

    seen: list = []
    ib.openOrderEvent += seen.append

    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 2
    order = Order(orderId=2, clientId=0, permId=99)
    ib.wrapper.openOrder(2, contract, order, OrderState(status="Submitted"))

    assert len(seen) == 1
    assert seen[0].order.permId == 99


def test_historical_data_after_end_is_noop():
    ib = ibi.IB()
    ib.wrapper.requests.open(ReqIdKey(7))
    ib.wrapper.historicalDataEnd(7, "", "")

    # Stray bar — must not raise.
    from ib_async.objects import BarData

    bar = BarData(date="20251020 15:00:00", open=1, high=2, low=0, close=1, volume=10)
    ib.wrapper.historicalData(7, bar)


def test_contract_details_after_end_is_noop():
    ib = ibi.IB()
    ib.wrapper.requests.open(ReqIdKey(11))
    ib.wrapper.contractDetailsEnd(11)
    # Stray late callback — no-op.
    ib.wrapper.contractDetails(11, ContractDetails())


def test_historical_news_after_end_is_noop():
    ib = ibi.IB()
    ib.wrapper.requests.open(ReqIdKey(13))
    ib.wrapper.historicalNewsEnd(13, False)
    ib.wrapper.historicalNews(13, "20251020 15:00:00 UTC", "BZ", "a", "h")


def test_position_after_end_still_emits_live_event():
    """A position update arriving after the snapshot has settled is a
    live update, not stale data — emit positionEvent regardless."""
    ib = ibi.IB()
    ib.wrapper.requests.open(SingletonKey("positions"))
    ib.wrapper.positionEnd()

    seen: list = []
    ib.positionEvent += seen.append

    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 3
    ib.wrapper.position("DU000000", contract, 100, 50.0)

    assert len(seen) == 1
    # And the snapshot list is not corrupted by the late update.
    assert SingletonKey("positions") not in ib.wrapper.requests


def test_extend_no_op_on_settled_historical_ticks():
    from ib_async.objects import HistoricalTick

    ib = ibi.IB()
    ib.wrapper.requests.open(ReqIdKey(99))
    ib.wrapper.requests.set_result(ReqIdKey(99))  # settle
    # Late chunk — must not raise.
    ib.wrapper.historicalTicks(99, [HistoricalTick(0, 0.0, 0.0)], False)
    assert ReqIdKey(99) not in ib.wrapper.requests
