"""``reqHistoricalSchedule`` duration and pass-through parameters.

The schedule request used to hard-code ``f"{numDays} D"``, which made the
day unit the only span expressible through the adapter. IBKR caps a
historical request at one year and rejects a day count past it, so a
caller who wanted ``'1 Y'`` -- or any of ``'W'`` / ``'M'`` -- had no way
to ask for it short of dropping down to ``IB.client``.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey
from tests._clock import installClock

# Positional layout of the outbound ``client.reqHistoricalData`` call.
REQ_ID, CONTRACT, END, DURATION, BAR_SIZE = 0, 1, 2, 3, 4
WHAT_TO_SHOW, USE_RTH, FORMAT_DATE, KEEP_UP_TO_DATE, CHART_OPTIONS = 5, 6, 7, 8, 9


def _wiredIB() -> ibi.IB:
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.side_effect = iter(range(300, 1000))
    ib.client.isConnected.return_value = True
    return ib


def _stock() -> ibi.Stock:
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 1
    return contract


def _runSchedule(ib: ibi.IB, *args, **kwargs) -> ibi.HistoricalSchedule:
    """Drive the request to the wire, answer it, and return the result."""
    loop = ibi.util.getLoop()
    task = loop.create_task(ib.reqHistoricalScheduleAsync(*args, **kwargs))
    loop.run_until_complete(asyncio.sleep(0))

    reqId = ib.client.reqHistoricalData.call_args[0][REQ_ID]
    ib.wrapper.historicalSchedule(reqId, "20250714", "20250715", "US/Eastern", [])
    return loop.run_until_complete(task)


def _sentArgs(ib: ibi.IB) -> tuple:
    return ib.client.reqHistoricalData.call_args[0]


# -- duration -----------------------------------------------------------------


def test_int_numDays_keeps_the_day_shorthand():
    ib = _wiredIB()

    _runSchedule(ib, _stock(), 30)

    assert _sentArgs(ib)[DURATION] == "30 D"


def test_str_numDays_reaches_the_wire_verbatim():
    """The whole point: a unit other than days is only reachable through
    the str form, and it must not be rewritten on the way out."""
    ib = _wiredIB()

    _runSchedule(ib, _stock(), "1 Y")

    assert _sentArgs(ib)[DURATION] == "1 Y"


def test_str_numDays_passes_every_ibkr_unit():
    for duration in ("60 S", "5 D", "2 W", "6 M", "1 Y"):
        ib = _wiredIB()
        _runSchedule(ib, _stock(), duration)
        assert _sentArgs(ib)[DURATION] == duration


def test_str_numDays_is_not_reformatted_when_it_looks_like_days():
    """``'400 D'`` is out of IBKR's range, but the caller asked for it
    explicitly -- the adapter forwards rather than second-guesses."""
    ib = _wiredIB()

    _runSchedule(ib, _stock(), "400 D")

    assert _sentArgs(ib)[DURATION] == "400 D"


# -- unchanged defaults -------------------------------------------------------


def test_defaults_are_unchanged():
    ib = _wiredIB()
    contract = _stock()

    schedule = _runSchedule(ib, contract, 7)

    sent = _sentArgs(ib)
    assert sent[CONTRACT] is contract
    assert sent[END] == ""
    assert sent[DURATION] == "7 D"
    assert sent[BAR_SIZE] == "1 day"
    assert sent[WHAT_TO_SHOW] == "SCHEDULE"
    assert sent[USE_RTH] is True
    assert sent[FORMAT_DATE] == 1
    assert sent[KEEP_UP_TO_DATE] is False
    assert sent[CHART_OPTIONS] is None
    assert schedule.timeZone == "US/Eastern"


def test_legacy_positional_call_still_works():
    """``(contract, numDays, endDateTime, useRTH)`` predates the added
    parameters and must keep landing in the same slots."""
    ib = _wiredIB()

    _runSchedule(ib, _stock(), 3, "20250714 08:00:00", False)

    sent = _sentArgs(ib)
    assert sent[DURATION] == "3 D"
    assert sent[END] == "20250714 08:00:00"
    assert sent[USE_RTH] is False


# -- newly exposed pass-throughs ----------------------------------------------


def test_barSizeSetting_formatDate_and_chartOptions_reach_the_wire():
    ib = _wiredIB()
    options = [ibi.TagValue("k", "v")]

    _runSchedule(
        ib,
        _stock(),
        "1 M",
        barSizeSetting="1 hour",
        formatDate=2,
        chartOptions=options,
    )

    sent = _sentArgs(ib)
    assert sent[BAR_SIZE] == "1 hour"
    assert sent[FORMAT_DATE] == 2
    assert sent[CHART_OPTIONS] is options
    assert sent[WHAT_TO_SHOW] == "SCHEDULE"


# -- timeout ------------------------------------------------------------------


def test_unanswered_request_times_out_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch,
):
    """A duration IBKR drops rather than answers left the await unbounded
    with no reqId in the caller's hands to cancel by."""
    ib = _wiredIB()
    loop = ibi.util.getLoop()
    clock = installClock(loop, monkeypatch)

    task = loop.create_task(ib.reqHistoricalScheduleAsync(_stock(), "400 D", timeout=6))
    loop.run_until_complete(asyncio.sleep(0))
    clock.advance(6.1)
    schedule = loop.run_until_complete(task)

    assert schedule == ibi.HistoricalSchedule()
    ib.client.cancelHistoricalData.assert_called_once_with(300)
    assert ib.wrapper.requests.get(ReqIdKey(300)) is None


async def test_a_cancelled_historical_request_is_cancelled_with_ibkr():
    """A caller's own cancellation (or a sync call's RequestTimeout) ends
    the request with IBKR and closes its keepUpToDate subscription."""
    ib = _wiredIB()
    for reqId, start in (
        (
            300,
            lambda: ib.reqHistoricalDataAsync(
                _stock(), "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
            ),
        ),
        (301, lambda: ib.reqHistoricalScheduleAsync(_stock(), 5)),
    ):
        task = asyncio.ensure_future(start())
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        ib.client.cancelHistoricalData.assert_called_with(reqId)
        assert ib.wrapper.subscriptions.get_sub(reqId) is None
    assert len(ib.wrapper.requests) == 0
