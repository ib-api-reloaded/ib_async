"""110 and 321 refuse the request they name.

For a working order they are warnings: TWS refused a modification or a
cancel, and the order goes on as it was. For a what-if order, a data
request or a new order TWS has not accepted, nothing else follows, so they
end it; before, the caller waited forever (IB.RequestTimeout is 0 by
default) and a refused new order stayed in openTrades().
"""

from __future__ import annotations

import asyncio
import dataclasses
from decimal import Decimal

import pytest

import ib_async as ibi
from ib_async import OrderStatus, Trade
from ib_async._requests import ReqIdKey, WhatIfKey
from ib_async.util import getLoop
from tests._session import Session, errorFrame, ready
from tests._sim import CONTRACT, PlacedOrder, SimulatedTws

REFUSED_REQUEST = [110, 321]
READ_ONLY = (
    "Error validating request.-'bN' : cause - The API interface is currently "
    "in Read-Only mode."
)
# IBKR's text for each code, 321 as sent in Read-Only mode.
REFUSAL_TEXTS = {
    110: "The price does not conform to the minimum price variation for this contract.",
    321: READ_ONLY,
}


def whatIfOrderId(session: Session) -> int:
    [request] = session.ib.wrapper.requests
    assert isinstance(request.key, WhatIfKey)
    return request.key.orderId


def startWhatIf(session: Session) -> asyncio.Future[ibi.OrderState]:
    return asyncio.ensure_future(
        session.ib.whatIfOrderAsync(
            ibi.Stock("XXX", "SMART", "USD"), ibi.MarketOrder("BUY", 100)
        ),
        loop=session.loop,
    )


@pytest.mark.parametrize("code", REFUSED_REQUEST)
def test_a_refused_what_if_answers_the_refusal(code: int) -> None:
    session = Session()
    ready(session)
    whatIf = startWhatIf(session)
    session.run()

    text = REFUSAL_TEXTS[code]
    session.receive(errorFrame(whatIfOrderId(session), code, text))

    state = whatIf.result()
    assert (state.whatIfErrorCode, state.whatIfErrorString) == (code, text)
    assert session.ib.trades() == []


def test_a_refused_what_if_raises_when_asked_to() -> None:
    session = Session()
    ready(session)
    session.ib.RaiseRequestErrors = True
    whatIf = startWhatIf(session)
    session.run()

    session.receive(errorFrame(whatIfOrderId(session), 321, READ_ONLY))

    error = whatIf.exception()
    assert isinstance(error, ibi.RequestError) and error.code == 321


def test_a_snapshot_refused_with_321_ends() -> None:
    session = Session()
    ready(session)
    tickers = asyncio.ensure_future(
        session.ib.reqTickersAsync(ibi.Stock("AAPL", "SMART", "USD", conId=265598)),
        loop=session.loop,
    )
    session.run()
    [sub] = session.ib.wrapper.subscriptions

    text = "Snapshot market data subscription is not applicable to generic ticks"
    session.receive(errorFrame(sub.reqId, 321, text))
    session.run()
    assert tickers.done() and tickers.exception() is None
    assert len(session.ib.wrapper.subscriptions) == 0


def test_contract_details_refused_with_321_end() -> None:
    tws = SimulatedTws(getLoop())
    request = tws.start(tws.ib.reqContractDetailsAsync(CONTRACT))
    [ask] = tws.asks
    tws.refuse(ask, 321)
    assert request.result() == []
    assert len(tws.wrapper.requests) == 0
    tws.assertEachEndCountedOnce()


def test_account_updates_for_an_unknown_model_end_on_321() -> None:
    """IBKR answers an unknown model name with 321 ("Model name 'M' is
    incorrect")."""
    tws = SimulatedTws(getLoop())
    request = tws.start(tws.ib.reqAccountUpdatesMultiAsync("DU1", "M"))
    [ask] = tws.asks
    tws.refuse(ask, 321)
    assert request.done() and request.exception() is None
    assert len(tws.wrapper.requests) == 0
    tws.assertEachEndCountedOnce()


def test_positions_for_an_unknown_model_end_on_321() -> None:
    tws = SimulatedTws(getLoop())
    request = tws.start(tws.ib.reqPositionsMultiAsync("DU1", "M"))
    [ask] = tws.asks
    tws.refuse(ask, 321)
    assert request.result() == []
    assert len(tws.wrapper.requests) == 0
    tws.assertEachEndCountedOnce()


def test_321_ends_the_answer_owed_to_an_abandoned_request() -> None:
    """A caller that stopped waiting leaves the answer owed; IBKR's refusal
    is that answer."""
    tws = SimulatedTws(getLoop())
    request = tws.start(tws.ib.reqContractDetailsAsync(CONTRACT))
    [ask] = tws.asks
    assert ask.reqId is not None
    request.cancel()
    tws.run()
    assert tws.wrapper.requests.answering(ReqIdKey(ask.reqId))

    tws.refuse(ask, 321)
    assert not tws.wrapper.requests.answering(ReqIdKey(ask.reqId))


class Placed:
    """An order at a simulated TWS and the cancelled events it fired."""

    def __init__(self, *, accepted: bool) -> None:
        self.tws = SimulatedTws(getLoop())
        self.trade: Trade = self.tws.ib.placeOrder(
            CONTRACT, ibi.LimitOrder("BUY", 5, 50.00)
        )
        self.tws.run()
        self.placed: PlacedOrder = self.tws.orders[self.trade.order.orderId]
        self.cancelled: list[Trade] = []
        self.trade.cancelledEvent += self.cancelled.append
        if accepted:
            self.tws.acknowledge(self.placed)

    def error(self, code: int, text: str | None = None) -> None:
        """Send error ``code`` for the order, with IBKR's text for a
        refusal unless ``text`` is given."""
        if text is None:
            text = REFUSAL_TEXTS[code]
        self.tws.wrapper.error(self.placed.orderId, code, text, "")
        self.tws.run()

    def assertEnded(self) -> None:
        assert self.trade.orderStatus.status == OrderStatus.Cancelled
        assert self.cancelled == [self.trade]
        assert self.trade not in self.tws.ib.openTrades()

    def assertWorking(self) -> None:
        assert self.trade.orderStatus.status == OrderStatus.ValidationError
        assert self.cancelled == []
        assert self.trade in self.tws.ib.openTrades()


@pytest.mark.parametrize("code", REFUSED_REQUEST)
def test_a_refused_new_order_ends(code: int) -> None:
    order = Placed(accepted=False)
    order.error(code)
    order.assertEnded()


@pytest.mark.parametrize("notice", [10349, 404, 481])
@pytest.mark.parametrize("code", REFUSED_REQUEST)
def test_a_new_order_refused_after_a_notice_ends(code: int, notice: int) -> None:
    """A notice before TWS's first status makes the order ValidationError;
    the order is still not accepted, so the refusal ends it."""
    order = Placed(accepted=False)
    order.error(notice, "notice")
    order.error(code)
    order.assertEnded()


@pytest.mark.parametrize("code", REFUSED_REQUEST)
def test_a_new_order_cancelled_then_refused_ends(code: int) -> None:
    order = Placed(accepted=False)
    order.tws.ib.cancelOrder(order.trade.order)
    order.tws.run()
    order.error(code)
    order.assertEnded()


@pytest.mark.parametrize("code", REFUSED_REQUEST)
def test_a_refused_modification_leaves_the_order_working(code: int) -> None:
    order = Placed(accepted=True)
    order.trade.order.lmtPrice = Decimal(51)
    order.tws.ib.placeOrder(CONTRACT, order.trade.order)
    order.tws.run()
    order.error(code)
    order.assertWorking()


@pytest.mark.parametrize("code", REFUSED_REQUEST)
def test_a_refused_modification_while_pending_submit_leaves_the_order_working(
    code: int,
) -> None:
    """TWS reports PendingSubmit with the permId it assigned: it has the
    order, so the refusal was of the modification."""
    order = Placed(accepted=False)
    order.tws._orderStatus(order.placed, "PendingSubmit")
    order.tws.run()
    order.trade.order.lmtPrice = Decimal(51)
    order.tws.ib.placeOrder(CONTRACT, order.trade.order)
    order.tws.run()
    order.error(code)
    order.assertWorking()


@pytest.mark.parametrize("code", REFUSED_REQUEST)
def test_an_order_tws_sent_back_without_a_status_stays_working(code: int) -> None:
    """openOrder before any status: TWS has the order."""
    order = Placed(accepted=False)
    order.tws.wrapper.openOrder(
        order.placed.orderId,
        order.placed.contract,
        dataclasses.replace(order.placed.order),
        ibi.OrderState(status="PreSubmitted"),
    )
    order.tws.run()
    order.error(code)
    order.assertWorking()


def test_a_notice_then_110_after_a_status_leaves_the_order_working() -> None:
    order = Placed(accepted=True)
    order.error(10349, "notice")
    order.error(110)
    order.assertWorking()


def test_a_cancel_refused_with_321_leaves_the_order_working() -> None:
    """Read-Only API mode refuses a cancel as it refuses an order."""
    order = Placed(accepted=True)
    order.tws.ib.cancelOrder(order.trade.order)
    order.tws.run()
    order.error(321)
    order.assertWorking()
    assert order.placed.working
