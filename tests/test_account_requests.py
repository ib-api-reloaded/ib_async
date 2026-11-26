"""reqAccountSummaryAsync, reqAccountUpdatesAsync and
reqAccountUpdatesMultiAsync answer None, as typed: the values go to IB's
account state, not to the awaiter. A refusal of a request with a reqId
also answers None."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import pytest

import ib_async as ibi
from ib_async.util import getLoop
from tests._sim import SimulatedTws

REQUESTS: dict[str, Callable[[ibi.IB], Awaitable[None]]] = {
    "reqAccountSummary": lambda ib: ib.reqAccountSummaryAsync(),
    "reqAccountUpdatesMulti": lambda ib: ib.reqAccountUpdatesMultiAsync("DU1"),
}


ANSWERED: dict[str, Callable[[ibi.IB], Awaitable[None]]] = {
    **REQUESTS,
    "reqAccountUpdates": lambda ib: ib.reqAccountUpdatesAsync("DU1"),
}


@pytest.mark.parametrize("kind", sorted(ANSWERED))
def test_an_answered_account_request_answers_none(kind: str) -> None:
    tws = SimulatedTws(getLoop())
    request = tws.start(ANSWERED[kind](tws.ib))
    [ask] = tws.openAsks(kind)

    tws.answer(ask)

    assert request.result() is None
    tws.assertEachEndCountedOnce()


@pytest.mark.parametrize("kind", sorted(REQUESTS))
def test_a_refused_account_request_answers_none(kind: str) -> None:
    tws = SimulatedTws(getLoop())
    request = tws.start(REQUESTS[kind](tws.ib))
    [ask] = tws.openAsks(kind)

    tws.refuse(ask, 321)

    assert request.result() is None
    tws.assertEachEndCountedOnce()
