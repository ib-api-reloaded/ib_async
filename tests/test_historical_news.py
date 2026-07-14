from datetime import UTC, datetime

import ib_async as ibi
from ib_async._requests import ReqIdKey


def test_historical_news_request_accumulates_list_results():
    ib = ibi.IB()
    req_id = 7
    req, _ = ib.wrapper.requests.open(ReqIdKey(req_id))
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
