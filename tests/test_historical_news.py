from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey
from tests._clock import installClock


def test_historical_news_request_accumulates_list_results():
    ib = ibi.IB()
    req_id = 7
    req = ib.wrapper.requests.open(ReqIdKey(req_id))
    future = req.future

    ib.wrapper.historicalNews(
        req_id,
        "20251020 15:00:00 UTC",
        "BZ",
        "article-1",
        "headline one",
    )
    ib.wrapper.historicalNews(
        req_id,
        "20251020 15:05:00 UTC",
        "FLY",
        "article-2",
        "headline two",
    )
    ib.wrapper.historicalNewsEnd(req_id, False)

    result = future.result()

    assert len(result) == 2
    assert [item.providerCode for item in result] == ["BZ", "FLY"]
    assert result[0].time == datetime(2025, 10, 20, 15, 0, tzinfo=UTC)


async def test_historical_news_timeout_is_the_callers(
    monkeypatch: pytest.MonkeyPatch,
):
    """The wait is a parameter (it was fixed at 4 seconds, short for 300
    headlines): with no answer, the request gives up after ``timeout``."""

    clock = installClock(asyncio.get_running_loop(), monkeypatch)
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.return_value = 7
    ib.client.isConnected.return_value = False
    news = asyncio.ensure_future(
        ib.reqHistoricalNewsAsync(8314, "BZ", "", "", 300, timeout=300)
    )
    await asyncio.sleep(0)
    clock.advance(5)
    await asyncio.sleep(0)
    assert not news.done()
    clock.advance(296)
    assert await news is None
