"""The dividend tick (59), as IBKR sends it.

Its value is 'past12,next12,yyyymmdd,amount'. IBKR uses commas both
between the fields and within a number of 1,000 or more, so the fields
are read by their shape. tests/test_ticker_tick_model.py sends generated
ticks of every shape; these are the shapes seen from IBKR.
"""

from __future__ import annotations

import logging
from datetime import date

import pytest

from ib_async import Dividends, Ticker
from ib_async.util import getLoop
from tests._sim import CONTRACT, SimulatedTws, TestEmpty


def tickerWithDividends(value: str) -> Ticker[None] | Ticker[TestEmpty]:
    tws = SimulatedTws(getLoop())
    ticker = tws.ib.reqMktData(CONTRACT, "456")
    tws.run()
    [ask] = tws.openAsks("reqMktData")
    assert ask.reqId is not None
    tws.wrapper.tickString(ask.reqId, 59, value)
    return ticker


@pytest.mark.parametrize(
    ("value", "dividends"),
    [
        # IBKR's documented example
        ("0.83,0.92,20130219,0.23", Dividends(0.83, 0.92, date(2013, 2, 19), 0.23)),
        # sent by IBKR: no past total, 1,089.45 over the next 12 months
        (
            ",1,089.45,20261116,2.199",
            Dividends(None, 1089.45, date(2026, 11, 16), 2.199),
        ),
        (
            "1,089.45,12,234,567.5,20261116,1,089.45",
            Dividends(1089.45, 12234567.5, date(2026, 11, 16), 1089.45),
        ),
        (",,20261218,", Dividends(None, None, date(2026, 12, 18), None)),
        (",,,", Dividends(None, None, None, None)),
    ],
)
def test_dividends_are_read_by_the_shape_of_each_field(
    value: str, dividends: Dividends
) -> None:
    assert tickerWithDividends(value).dividends == dividends


@pytest.mark.parametrize(
    "value", ["0.83,0.92,2013021,0.23", "0.83,0.92,20130219", "1,2", "a,b,20130219,c"]
)
def test_another_shape_is_logged_and_leaves_the_dividends(
    value: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        ticker = tickerWithDividends(value)
    assert ticker.dividends is None
    assert f"tickType 59: malformed value: {value!r}" in caplog.text
