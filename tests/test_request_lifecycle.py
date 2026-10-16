"""How requests end, and what their late answers are."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey, RequestRegistry, SingletonKey
from ib_async._subscriptions import HistoricalBarsSub

EXECUTED = dt.datetime(2026, 10, 14, 15, 30, tzinfo=dt.UTC)


def connected() -> ibi.IB:
    """An IB whose client records requests instead of sending them."""
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.isConnected.return_value = True
    ib.client.getReqId.side_effect = iter(range(500, 1000))
    return ib


def execution(execId: str) -> ibi.Execution:
    return ibi.Execution(
        execId=execId, permId=1, shares=Decimal(1), price=Decimal(1), time=EXECUTED
    )


async def test_late_rows_of_an_abandoned_executions_request_are_history():
    """A reqExecutions its caller gave up on still gets its answer: those
    rows are past executions, not live fills; after its end, executions
    for that reqId would be live again."""
    ib = connected()
    task = asyncio.ensure_future(ib.reqExecutionsAsync())
    await asyncio.sleep(0)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(task, 0.01)
    assert len(ib.wrapper.requests) == 0

    stock = ibi.Stock("X", "SMART", "USD")
    ib.wrapper.execDetails(500, stock, execution("late"))
    assert ib.wrapper.fills["late"].time == EXECUTED
    ib.wrapper.execDetailsEnd(500)
    assert not ib.wrapper.requests.answering(ReqIdKey(500))


async def test_cancel_cancels_every_awaiter_without_noise():
    reg = RequestRegistry()
    mine = reg.share(SingletonKey("positions")).future
    req = reg.get(SingletonKey("positions"))
    reg.cancel(SingletonKey("positions"))
    assert req is not None and req.future.cancelled() and mine.cancelled()


async def test_a_request_never_sent_leaves_live_updates_live():
    """reqOpenOrders while disconnected sends nothing, so no answer is
    owed: a later live order update is still an openOrderEvent."""
    ib = connected()
    ib.client.reqOpenOrders.side_effect = ConnectionError("Not connected")
    with pytest.raises(ConnectionError):
        ib.reqOpenOrdersAsync()
    events: list = []
    ib.openOrderEvent += events.append
    contract = ibi.Stock("X", "SMART", "USD")
    order = ibi.Order(orderId=1, clientId=0, permId=5)
    ib.wrapper.openOrder(1, contract, order, ibi.OrderState(status="Submitted"))
    assert len(events) == 1


async def test_a_refused_request_for_one_object_answers_its_kind():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    schedule = asyncio.ensure_future(ib.reqHistoricalScheduleAsync(contract, 5))
    await asyncio.sleep(0)
    ib.wrapper.error(500, 162, "Historical Market Data Service error", "")
    assert await schedule == ibi.HistoricalSchedule()
    article = ib.reqNewsArticleAsync("BZ", "1")
    ib.wrapper.error(501, 10172, "Failed to request news article", "")
    assert article.result() is None


async def test_a_bust_event_starts_the_answer_over_under_a_fresh_reqid():
    """A bust event during the first answer sends the request again,
    under a fresh reqId: the caller gets the new answer, its bars and
    subscription carry the new reqId, and IBKR's reply to cancelling the
    old one refuses nothing."""
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    ib.wrapper.historicalData(
        500, ibi.BarData(date="20261015 15:00:00 UTC", close=Decimal(1))
    )
    ib.wrapper.error(500, 10225, "Bust event occurred", "")
    ib.wrapper.error(500, 162, "API historical data query cancelled: 500", "")
    assert not task.done()
    ib.wrapper.historicalData(
        501, ibi.BarData(date="20261015 15:00:00 UTC", close=Decimal(2))
    )
    ib.wrapper.historicalDataEnd(501, "", "")
    bars = await task
    assert [bar.close for bar in bars] == [Decimal(2)]
    assert bars.reqId == 501
    assert ib.wrapper.subscriptions.get_sub(500) is None
    assert isinstance(ib.wrapper.subscriptions.get_sub(501), HistoricalBarsSub)
    ib.client.cancelHistoricalData.assert_called_once_with(500)
    assert ib.client.reqHistoricalData.call_args.args[0] == 501


async def test_a_bust_event_after_the_answer_refills_the_bars():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    ib.wrapper.historicalData(
        500, ibi.BarData(date="20261015 15:00:00 UTC", close=Decimal(1))
    )
    ib.wrapper.historicalDataEnd(500, "", "")
    bars = await task
    ib.wrapper.error(500, 10225, "Bust event occurred", "")
    ib.wrapper.historicalData(
        501, ibi.BarData(date="20261015 15:00:00 UTC", close=Decimal(3))
    )
    ib.wrapper.historicalDataEnd(501, "", "")
    assert [bar.close for bar in bars] == [Decimal(3)]


async def test_answers_that_never_settled_now_do():
    ib = connected()
    tiers = ib.reqSoftDollarTiersAsync()
    ib.wrapper.softDollarTiers(500, [ibi.SoftDollarTier("a", "b", "c")])
    assert tiers.result() == [ibi.SoftDollarTier("a", "b", "c")]
    info = ib.reqUserInfoAsync()
    ib.wrapper.userInfo(501, "brand")
    assert info.result() == "brand"
    codes = ib.reqFamilyCodesAsync()
    ib.wrapper.familyCodes([ibi.FamilyCode("acct", "fam")])
    assert codes.result() == [ibi.FamilyCode("acct", "fam")]


async def test_a_shared_request_with_other_arguments_is_refused():
    """reqOpenOrders and reqAllOpenOrders share one answer that does not
    say which was asked, as completed orders' does not say apiOnly."""
    ib = connected()
    ib.reqOpenOrdersAsync()
    with pytest.raises(ValueError, match="must wait for its answer"):
        ib.reqAllOpenOrdersAsync()
    ib.reqCompletedOrdersAsync(True)
    with pytest.raises(ValueError, match="must wait for its answer"):
        ib.reqCompletedOrdersAsync(False)
    ib.reqCompletedOrdersAsync(True)  # the same request is shared
    ib.client.reqCompletedOrders.assert_called_once_with(True)


async def test_fa_requests_of_different_types_are_each_answered():
    ib = connected()
    groups = asyncio.ensure_future(ib.requestFAAsync(1))
    aliases = asyncio.ensure_future(ib.requestFAAsync(3))
    await asyncio.sleep(0)
    assert ib.client.requestFA.call_count == 2
    ib.wrapper.receiveFA(3, "<aliases/>")
    ib.wrapper.receiveFA(1, "<groups/>")
    assert (await groups, await aliases) == ("<groups/>", "<aliases/>")


async def test_a_market_rule_not_sent_is_not_left_open():
    ib = connected()
    ib.client.reqMarketRule.side_effect = ConnectionError("Not connected")
    with pytest.raises(ConnectionError):
        await ib.reqMarketRuleAsync(26)
    assert len(ib.wrapper.requests) == 0


async def test_a_timeout_of_zero_waits_for_the_answer():
    ib = connected()
    task = asyncio.ensure_future(
        ib.reqHistoricalNewsAsync(1, "BZ", "", "", 10, timeout=0)
    )
    await asyncio.sleep(0.01)
    assert not task.done()
    ib.wrapper.historicalNewsEnd(500, False)
    assert await task == []


async def test_a_refused_keep_up_to_date_request_closes_its_subscription():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    assert isinstance(ib.wrapper.subscriptions.get_sub(500), HistoricalBarsSub)
    ib.wrapper.error(500, 162, "Historical Market Data Service error", "")
    await task
    assert ib.wrapper.subscriptions.get_sub(500) is None


async def test_a_request_cancelled_with_ibkr_is_owed_nothing():
    """reqHeadTimeStamp cancels its request with IBKR however it ends, so
    a timeout leaves no answer owed to it."""
    ib = connected()
    task = asyncio.ensure_future(
        ib.reqHeadTimeStampAsync(ibi.Stock("X", "SMART", "USD"), "TRADES", True, 1)
    )
    await asyncio.sleep(0)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(task, 0.01)
    assert not ib.wrapper.requests.answering(ReqIdKey(500))


async def test_an_error_ends_an_owed_answer():
    ib = connected()
    task = asyncio.ensure_future(ib.reqExecutionsAsync())
    await asyncio.sleep(0)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(task, 0.01)
    assert ib.wrapper.requests.answering(ReqIdKey(500))
    ib.wrapper.error(500, 162, "Historical Market Data Service error", "")
    assert not ib.wrapper.requests.answering(ReqIdKey(500))


async def test_an_abandoned_scan_ends_its_subscription():
    ib = connected()
    task = asyncio.ensure_future(ib.reqScannerDataAsync(ibi.ScannerSubscription()))
    await asyncio.sleep(0)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(task, 0.01)
    assert ib.wrapper.subscriptions.get_sub(500) is None
    ib.client.cancelScannerSubscription.assert_called_once_with(500)


async def test_an_fa_request_is_keyed_as_its_answer_is():
    """The answer carries the FA data type as an int, however it was
    asked for."""
    ib = connected()
    groups = asyncio.ensure_future(ib.requestFAAsync("1"))  # type: ignore[arg-type]
    await asyncio.sleep(0)
    ib.wrapper.receiveFA(1, "<groups/>")
    assert await groups == "<groups/>"


async def test_cancelling_wsh_metadata_cancels_its_awaiter():
    """A second getWshMetaData cancels the first one's request: the
    first caller is woken, not left waiting for good."""
    ib = connected()
    ib.client.serverVersion.return_value = 200
    first = asyncio.ensure_future(ib.getWshMetaDataAsync())
    await asyncio.sleep(0)
    second = asyncio.ensure_future(ib.getWshMetaDataAsync())
    await asyncio.sleep(0)
    with pytest.raises(asyncio.CancelledError):
        await first
    ib.wrapper.wshMetaData(501, "{}")
    assert await second == "{}"


async def test_a_request_abandoned_after_a_bust_ends_its_resent_subscription():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract,
            "",
            "1 D",
            "1 hour",
            "TRADES",
            True,
            keepUpToDate=True,
            timeout=0.05,
        )
    )
    await asyncio.sleep(0)
    ib.wrapper.error(500, 10225, "Bust event occurred", "")
    await task
    assert [c.args[0] for c in ib.client.cancelHistoricalData.call_args_list] == [
        500,
        501,
    ]
    assert ib.wrapper.subscriptions.get_sub(501) is None
    assert not ib.wrapper.requests.answering(ReqIdKey(501))


async def test_cancelling_bars_being_refilled_ends_the_refill():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    ib.wrapper.historicalDataEnd(500, "", "")
    bars = await task
    ib.wrapper.error(500, 10225, "Bust event occurred", "")
    ib.cancelHistoricalData(bars)
    assert len(ib.wrapper.requests) == 0
    ib.wrapper.historicalData(
        501, ibi.BarData(date="20261015 15:00:00 UTC", close=Decimal(9))
    )
    assert list(bars) == []


async def test_refilled_bars_are_announced():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    ib.wrapper.historicalDataEnd(500, "", "")
    bars = await task
    updates: list = []
    bars.updateEvent += lambda b, hasNewBar: updates.append((len(b), hasNewBar))
    ib.wrapper.error(500, 10225, "Bust event occurred", "")
    ib.wrapper.historicalData(
        501, ibi.BarData(date="20261015 15:00:00 UTC", close=Decimal(3))
    )
    ib.wrapper.historicalDataEnd(501, "", "")
    await asyncio.sleep(0)
    assert updates == [(1, True)]


async def test_a_refused_refill_is_not_announced():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    ib.wrapper.historicalDataEnd(500, "", "")
    bars = await task
    updates: list = []
    bars.updateEvent += lambda b, hasNewBar: updates.append(hasNewBar)
    ib.wrapper.error(500, 10225, "Bust event occurred", "")
    ib.wrapper.error(501, 162, "Historical Market Data Service error", "")
    await asyncio.sleep(0)
    assert updates == []
    assert ib.wrapper.subscriptions.get_sub(501) is None


async def test_bars_cancelled_by_hand_are_cancelled_with_ibkr_once():
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    task = asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    (bars,) = ib.realtimeBars()
    ib.cancelHistoricalData(bars)
    with pytest.raises(asyncio.CancelledError):
        await task
    ib.client.cancelHistoricalData.assert_called_once_with(500)


async def test_a_bust_resend_is_logged_with_both_reqids(caplog):
    ib = connected()
    contract = ibi.Stock("X", "SMART", "USD")
    asyncio.ensure_future(
        ib.reqHistoricalDataAsync(
            contract, "", "1 D", "1 hour", "TRADES", True, keepUpToDate=True
        )
    )
    await asyncio.sleep(0)
    with caplog.at_level(logging.INFO, logger="ib_async.wrapper"):
        ib.wrapper.error(500, 10225, "Bust event occurred", "")
    assert "reqId 500 sent again as 501" in caplog.text
