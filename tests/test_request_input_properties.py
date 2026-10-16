"""A request made with any Contract or Order a user may pass sends exactly
one frame, or is refused before it sends anything.

The client connects to a recording connection at the newest server
version, so the protobuf converters encode every request. For each request
method and each generated Contract and Order, the test checks that the
method sends one frame, or raises ValueError or TypeError and sends
nothing. If a frame went out before the exception, the server would hold a
request that the caller believes was refused.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async.order import Order
from tests._property import examples
from tests._session import Session, ready
from tests._strategies import orders, userContracts

Request = Callable[[ibi.IB, ibi.Contract, Order], object]

REQUESTS: dict[str, Request] = {
    "reqMktData": lambda ib, c, o: ib.reqMktData(c),
    "reqMktDepth": lambda ib, c, o: ib.reqMktDepth(c),
    "reqTickByTickData": lambda ib, c, o: ib.reqTickByTickData(c, "Last"),
    "reqRealTimeBars": lambda ib, c, o: ib.reqRealTimeBars(c, 5, "TRADES", True),
    "reqHistoricalData": lambda ib, c, o: ib.reqHistoricalDataAsync(
        c, "", "1 D", "1 min", "TRADES", True
    ),
    "reqHeadTimeStamp": lambda ib, c, o: ib.reqHeadTimeStampAsync(c, "TRADES", True, 1),
    "reqHistogramData": lambda ib, c, o: ib.reqHistogramDataAsync(c, True, "1 day"),
    "reqHistoricalTicks": lambda ib, c, o: ib.reqHistoricalTicksAsync(
        c, "", "20261016 12:00:00", 100, "TRADES", True
    ),
    "reqContractDetails": lambda ib, c, o: ib.reqContractDetailsAsync(c),
    "qualifyContracts": lambda ib, c, o: ib.qualifyContractsAsync(c),
    "calculateImpliedVolatility": lambda ib, c, o: ib.calculateImpliedVolatilityAsync(
        c, 1.0, 100.0
    ),
    "placeOrder": lambda ib, c, o: ib.placeOrder(c, o),
    "whatIfOrder": lambda ib, c, o: ib.whatIfOrderAsync(c, o),
}

REFUSALS = (ValueError, TypeError)


def attempt(
    session: Session, request: Request, contract, order
) -> tuple[BaseException | None, int]:
    """Make the request and return the refusal and the number of frames
    sent. The refusal is the exception the request raised, or None if the
    request was sent. An awaitable result is started as a task. Its frames
    are counted and then the task is cancelled. The cancel may send its own
    frame, which is not counted."""
    before = len(session.conn.sent)
    try:
        result = request(session.ib, contract, order)
    except REFUSALS as exc:
        return exc, len(session.conn.sent) - before
    refusal = None
    if asyncio.iscoroutine(result) or asyncio.isfuture(result):
        task = asyncio.ensure_future(result, loop=session.loop)
        session.run()
        if task.done() and not task.cancelled() and task.exception() is not None:
            refusal = task.exception()
            assert isinstance(refusal, REFUSALS), refusal
        sent = len(session.conn.sent) - before
        task.cancel()
        session.run()
        return refusal, sent
    return None, len(session.conn.sent) - before


@given(
    name=st.sampled_from(sorted(REQUESTS)),
    contract=userContracts,
    order=st.one_of(orders(), st.builds(ibi.MarketOrder, st.just("BUY"), st.just(100))),
)
@examples()
def test_request_sends_one_frame_or_refuses_before_sending(name, contract, order):
    session = Session()
    ready(session)
    refusal, sent = attempt(session, REQUESTS[name], contract, order)
    if refusal is None:
        assert sent == 1, (name, sent)
    else:
        assert sent == 0, (name, refusal)
