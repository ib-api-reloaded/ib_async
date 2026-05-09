"""Stage G: real-time bars / historical-bars-keepUpToDate / scanner /
PnL / PnLSingle subscriptions go through the SubscriptionRegistry.

Properties verified:

  * Each ``IB.req*`` registers a typed ``Subscription``.
  * Each ``IB.cancel*`` finds it via the registry and closes it; the
    legacy maps are cleaned up alongside until Stage K removes them.
  * ``reqPnL`` / ``reqPnLSingle`` silently dedupe on duplicate calls
    (replacing the previous hard ``assert`` that crashed retries).
"""

from unittest.mock import MagicMock

import ib_async as ibi
from ib_async._subscriptions import (
    HistoricalBarsSub,
    PnLSingleSub,
    PnLSub,
    RealTimeBarsSub,
    ScannerSub,
)


def _wired_ib():
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.side_effect = iter(range(300, 1000))
    ib.client.isConnected.return_value = False
    return ib


def _stock(conId: int) -> ibi.Stock:
    s = ibi.Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


# ---- real-time bars -------------------------------------------------------


def test_reqRealTimeBars_registers_sub_and_cancel_closes_it():
    ib = _wired_ib()
    contract = _stock(1)

    bars = ib.reqRealTimeBars(contract, 5, "TRADES", False)

    sub = ib.wrapper.subscriptions.get_sub(bars.reqId)
    assert isinstance(sub, RealTimeBarsSub)
    assert sub.bars is bars

    ib.cancelRealTimeBars(bars)

    ib.client.cancelRealTimeBars.assert_called_once_with(bars.reqId)
    assert ib.wrapper.subscriptions.get_sub(bars.reqId) is None
    assert bars.updateEvent.done() is True


# ---- historical bars (keepUpToDate) ---------------------------------------


def test_keepUpToDate_historical_data_registers_sub():
    """The keepUpToDate=True path adds a HistoricalBarsSub. We exercise
    just the registration step here (the full reqHistoricalDataAsync is
    integration-shaped); the cancel side is covered by the next test."""
    import asyncio

    ib = _wired_ib()
    contract = _stock(2)

    # Start an awaitable but never await it — we just want the wire +
    # registration side effects.
    coro = ib.reqHistoricalDataAsync(
        contract,
        endDateTime="",
        durationStr="60 S",
        barSizeSetting="5 secs",
        whatToShow="TRADES",
        useRTH=False,
        keepUpToDate=True,
        timeout=0,
    )
    task = asyncio.get_event_loop().create_task(coro)
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0))

    # Find the registered subscription via reqId. getReqId.side_effect
    # produced 300 first.
    sub = ib.wrapper.subscriptions.get_sub(300)
    assert isinstance(sub, HistoricalBarsSub)

    # Closing via cancelHistoricalData unregisters and sets the bars
    # event done.
    ib.cancelHistoricalData(sub.bars)
    ib.client.cancelHistoricalData.assert_called_once_with(300)
    assert ib.wrapper.subscriptions.get_sub(300) is None
    assert sub.bars.updateEvent.done() is True

    task.cancel()


# ---- scanner --------------------------------------------------------------


def test_reqScannerSubscription_registers_and_cancel_closes():
    ib = _wired_ib()
    sub_filter = ibi.ScannerSubscription()
    dataList = ib.reqScannerSubscription(sub_filter)

    sub = ib.wrapper.subscriptions.get_sub(dataList.reqId)
    assert isinstance(sub, ScannerSub)
    assert sub.dataList is dataList

    ib.cancelScannerSubscription(dataList)

    ib.client.cancelScannerSubscription.assert_called_once_with(dataList.reqId)
    assert ib.wrapper.subscriptions.get_sub(dataList.reqId) is None
    assert dataList.updateEvent.done() is True


# ---- PnL ------------------------------------------------------------------


def test_reqPnL_silent_dedupe():
    ib = _wired_ib()
    a = ib.reqPnL("DU1", "")
    b = ib.reqPnL("DU1", "")
    assert a is b
    assert ib.client.reqPnL.call_count == 1
    sub = ib.wrapper.subscriptions.get_pnl("DU1", "")
    assert isinstance(sub, PnLSub)
    assert sub.pnl is a


def test_cancelPnL_closes_via_registry():
    ib = _wired_ib()
    ib.reqPnL("DU1", "")
    reqId = ib.wrapper.subscriptions.get_pnl("DU1", "").reqId  # type: ignore[union-attr]

    ib.cancelPnL("DU1", "")

    ib.client.cancelPnL.assert_called_once_with(reqId)
    assert ib.wrapper.subscriptions.get_pnl("DU1", "") is None
    assert ib.wrapper.subscriptions.get_sub(reqId) is None


def test_cancelPnL_unknown_returns_quietly():
    ib = _wired_ib()
    ib.cancelPnL("MISSING", "")
    ib.client.cancelPnL.assert_not_called()


# ---- PnLSingle ------------------------------------------------------------


def test_reqPnLSingle_silent_dedupe():
    ib = _wired_ib()
    a = ib.reqPnLSingle("DU1", "", 42)
    b = ib.reqPnLSingle("DU1", "", 42)
    assert a is b
    assert ib.client.reqPnLSingle.call_count == 1
    sub = ib.wrapper.subscriptions.get_pnl_single("DU1", "", 42)
    assert isinstance(sub, PnLSingleSub)


def test_cancelPnLSingle_closes_via_registry():
    ib = _wired_ib()
    ib.reqPnLSingle("DU1", "", 42)
    reqId = ib.wrapper.subscriptions.get_pnl_single("DU1", "", 42).reqId  # type: ignore[union-attr]

    ib.cancelPnLSingle("DU1", "", 42)

    ib.client.cancelPnLSingle.assert_called_once_with(reqId)
    assert ib.wrapper.subscriptions.get_pnl_single("DU1", "", 42) is None
    assert ib.wrapper.subscriptions.get_sub(reqId) is None
