"""Property tests for util.df: every row and value is kept."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ib_async import util
from tests._property import examples

pytest.importorskip("polars")


@dataclass
class Row:
    count: int | None
    price: Decimal | None
    name: str
    when: datetime | None
    ratio: float | None


rows = st.lists(
    st.builds(
        Row,
        count=st.one_of(st.none(), st.integers(-(2**62), 2**62)),
        price=st.one_of(
            st.none(), st.decimals(Decimal("-1e9"), Decimal("1e9"), places=4)
        ),
        name=st.text(max_size=6),
        when=st.one_of(
            st.none(),
            st.datetimes(
                datetime(1980, 1, 1), datetime(2100, 1, 1), timezones=st.just(UTC)
            ),
        ),
        ratio=st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False)),
    ),
    max_size=20,
)


@given(rows=rows)
@examples()
def test_all_rows_and_values_kept(rows):
    frame = util.df(rows)
    assert frame.height == len(rows)
    if not rows:
        return  # no rows, so no column names
    assert frame.columns == ["count", "price", "name", "when", "ratio"]
    for column in frame.columns:
        got = frame[column].to_list()
        want = [getattr(row, column) for row in rows]
        assert got == want, column


@given(rows=rows, labels=st.permutations(["ratio", "name", "count"]))
@examples()
def test_labels_select_columns_in_order(rows, labels):
    frame = util.df(rows, labels)
    assert frame.columns == labels
    assert frame.height == len(rows)
