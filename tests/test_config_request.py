"""reqConfigAsync and updateConfigAsync answer TWS's response, or None
when TWS refuses the request, as their docstrings and types say."""

from __future__ import annotations

from ib_async.util import getLoop
from tests._sim import SimulatedTws


def test_a_refused_config_request_answers_none() -> None:
    tws = SimulatedTws(getLoop())
    request = tws.start(tws.ib.reqConfigAsync())
    [ask] = tws.openAsks("reqConfig")

    tws.refuse(ask)

    assert request.result() is None
    tws.assertEachEndCountedOnce()


def test_a_refused_config_update_answers_none() -> None:
    tws = SimulatedTws(getLoop())
    request = tws.start(tws.ib.updateConfigAsync())
    [opened] = tws.wrapper.requests

    tws.wrapper.error(opened.reqId, 321, "Server error validating request", "")
    tws.run()

    assert request.result() is None
    assert len(tws.wrapper.requests) == 0
