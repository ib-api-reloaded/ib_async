"""util.df builds polars DataFrames from ib_async objects."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import NamedTuple

import pytest

pl = pytest.importorskip("polars")

from ib_async import BarData, Position, RealTimeBar, Stock, util
from ib_async.flexreport import FlexReport

T0 = dt.datetime(2026, 10, 15, 9, 30, tzinfo=dt.UTC)


def bars() -> list[BarData]:
    return [
        BarData(
            date=T0,
            open=Decimal("100.5"),
            high=Decimal("101.25"),
            low=Decimal(99),
            close=Decimal("100.75"),
            volume=Decimal(1200),
            average=None,
            barCount=7,
        ),
        BarData(
            date=T0 + dt.timedelta(minutes=1),
            open=Decimal("100.75"),
            high=Decimal(102),
            low=Decimal("100.5"),
            close=Decimal("101.5"),
            volume=Decimal(800),
            average=Decimal("101.125"),
            barCount=3,
        ),
    ]


def test_dataclasses_one_row_each_with_field_columns():
    frame = util.df(bars())
    assert isinstance(frame, pl.DataFrame)
    assert frame.columns == [
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "average",
        "barCount",
    ]
    assert frame.height == 2


def test_values_keep_their_types():
    frame = util.df(bars())
    assert frame.schema["date"] == pl.Datetime(time_zone="UTC")
    assert frame["date"].to_list() == [T0, T0 + dt.timedelta(minutes=1)]
    assert isinstance(frame.schema["open"], pl.Decimal)
    # decimals with different scales keep their exact values
    assert frame["high"].to_list() == [Decimal("101.25"), Decimal(102)]
    assert frame["average"].to_list() == [None, Decimal("101.125")]
    assert frame.schema["barCount"] == pl.Int64


def test_ib_async_objects_stay_objects():
    contract = Stock("SPY", "SMART", "USD")
    frame = util.df([Position("DU1", contract, Decimal(10), Decimal("450.5"))])
    assert frame.schema["contract"] == pl.Object
    assert frame["contract"][0] is contract
    assert frame["position"].to_list() == [Decimal(10)]


def test_labels_keep_those_columns_in_that_order():
    frame = util.df(bars(), labels=["close", "date"])
    assert frame.columns == ["close", "date"]


def test_unknown_label_raises():
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        util.df(bars(), labels=["closing"])


def test_no_objects_gives_an_empty_frame():
    assert util.df([]).shape == (0, 0)
    assert util.df(iter(()), labels=["open", "close"]).columns == ["open", "close"]


def test_generator_input():
    assert util.df(b for b in bars()).height == 2


def test_namedtuples():
    class Quote(NamedTuple):
        bid: float
        ask: float

    frame = util.df([Quote(1.0, 1.5), Quote(2.0, 2.5)])
    assert frame.columns == ["bid", "ask"]
    assert frame["ask"].to_list() == [1.5, 2.5]


def test_plain_tuples_get_numbered_columns():
    frame = util.df([(1, "a"), (2, "b")])
    assert frame.columns == ["column_0", "column_1"]
    assert frame.rows() == [(1, "a"), (2, "b")]


def test_dicts_with_missing_keys_give_nulls():
    frame = util.df([{"a": 1}, {"a": 2, "b": "x"}])
    assert frame.columns == ["a", "b"]
    assert frame["b"].to_list() == [None, "x"]


def test_mixed_decimal_and_float_gives_a_float_column():
    frame = util.df([{"v": Decimal("1.25")}, {"v": 2.5}, {"v": None}])
    assert frame.schema["v"] == pl.Float64
    assert frame["v"].to_list() == [1.25, 2.5, None]


def test_flexreport_rows(tmp_path):
    path = tmp_path / "report.xml"
    path.write_text(
        "<FlexQueryResponse><FlexStatements><FlexStatement>"
        '<Trade symbol="SPY" quantity="10" tradePrice="450.5"/>'
        '<Trade symbol="QQQ" quantity="5" tradePrice="380"/>'
        "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )
    frame = FlexReport(path=path).df("Trade")
    assert frame.columns == ["symbol", "quantity", "tradePrice"]
    assert frame["symbol"].to_list() == ["SPY", "QQQ"]
    assert frame["quantity"].to_list() == [10, 5]
    # one float and one int in a column: a float column
    assert frame["tradePrice"].to_list() == [450.5, 380.0]


def test_ohlc_rows_from_frame_and_from_bars():
    expected = [
        (Decimal("100.5"), Decimal("101.25"), Decimal(99), Decimal("100.75")),
        (Decimal("100.75"), Decimal(102), Decimal("100.5"), Decimal("101.5")),
    ]
    assert util._ohlcRows(util.df(bars())) == expected
    assert util._ohlcRows(bars()) == expected


def test_ohlc_rows_from_realtime_bars():
    bar = RealTimeBar(
        time=T0,
        open=Decimal(1),
        high=Decimal(3),
        low=Decimal(0),
        close=Decimal(2),
    )
    assert util._ohlcRows([bar]) == [(Decimal(1), Decimal(3), Decimal(0), Decimal(2))]


def test_a_missing_optional_dependency_says_how_to_install_it():
    with pytest.raises(ImportError, match="pip install the-thing"):
        util._optional("ib_async_no_such_module", "pip install the-thing")
