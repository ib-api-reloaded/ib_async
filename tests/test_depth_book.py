"""Market-depth order book: row semantics, views, and wrapper integration."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

import ib_async as ibi
from ib_async._subscriptions import MktDepthSub
from ib_async.depth import DepthBook, DepthOperation
from ib_async.objects import DOMLevel

INSERT, UPDATE, DELETE = (
    DepthOperation.INSERT,
    DepthOperation.UPDATE,
    DepthOperation.DELETE,
)
BID, ASK = 1, 0


def _book(*prices: float) -> DepthBook:
    book = DepthBook()
    book.setRows(BID, [DOMLevel(price, 1.0, "") for price in prices])
    return book


def _prices(rows: Sequence[DOMLevel]) -> list[float]:
    return [row.price for row in rows]


def _depthTicker(reqId: int = 1) -> tuple[ibi.IB, ibi.Ticker]:
    ib = ibi.IB()
    contract = ibi.Stock("QQQ", "ISLAND", "USD")
    contract.conId = 1000 + reqId
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    ib.wrapper.subscriptions.add(
        MktDepthSub(reqId=reqId, contract=contract, ticker=ticker)
    )
    return ib, ticker


# ---------------------------------------------------------------------------
# DepthBook row semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "operation, position, expected",
    [
        # insert shifts the rows at and below ``position`` down
        (INSERT, 0, [9, 3, 2, 1]),
        (INSERT, 1, [3, 9, 2, 1]),
        (INSERT, 3, [3, 2, 1, 9]),
        (INSERT, 4, [3, 2, 1]),  # below the rows held is dropped
        (INSERT, -1, [3, 2, 1]),  # negative is ignored
        # update replaces the row in place
        (UPDATE, 0, [9, 2, 1]),
        (UPDATE, 2, [3, 2, 9]),
        (UPDATE, 3, [3, 2, 1, 9]),  # the next row down extends the book
        (UPDATE, 4, [3, 2, 1]),  # further down is dropped
        (UPDATE, -1, [3, 2, 1]),
        # delete pulls the rows below up
        (DELETE, 0, [2, 1]),
        (DELETE, 1, [3, 1]),
        (DELETE, 2, [3, 2]),
        (DELETE, 3, [3, 2, 1]),  # below the rows held is dropped
        (DELETE, -1, [3, 2, 1]),
        # unknown operations change nothing
        (7, 0, [3, 2, 1]),
    ],
)
def test_apply_row_operation(operation, position, expected):
    book = _book(3, 2, 1)
    book.apply(BID, operation, position, 9.0, 1.0)
    assert _prices(book.bids) == expected
    assert book.asks == ()


def test_apply_delete_returns_removed_row_and_others_return_none():
    book = _book(3, 2, 1)
    assert book.apply(BID, DELETE, 1, 0.0, 0.0) == DOMLevel(2, 1.0, "")
    assert book.apply(BID, DELETE, 5, 0.0, 0.0) is None
    assert book.apply(BID, UPDATE, 0, 9.0, 1.0) is None
    assert book.apply(BID, INSERT, 0, 8.0, 1.0) is None


def test_apply_routes_by_side_and_keeps_market_maker():
    book = DepthBook()
    book.apply(ASK, INSERT, 0, 101.0, 5.0, "ARCA")
    book.apply(BID, INSERT, 0, 100.0, 7.0, "NSDQ")
    assert book.asks == (DOMLevel(101.0, 5.0, "ARCA"),)
    assert book.bids == (DOMLevel(100.0, 7.0, "NSDQ"),)


def test_out_of_range_rows_are_logged_at_debug(caplog):
    book = _book(3)
    with caplog.at_level("DEBUG", logger="ib_async.depth"):
        book.apply(BID, DELETE, 4, 0.0, 0.0)
        book.apply(BID, UPDATE, 0, 9.0, 1.0)  # in range: silent
    assert len(caplog.records) == 1
    assert "row 4 of a 1-row bid side" in caplog.records[0].getMessage()


def test_set_rows_replaces_one_side_from_any_iterable():
    book = _book(3, 2)
    book.setRows(BID, (DOMLevel(price, 1.0, "") for price in (5, 4, 1)))
    book.setRows(ASK, [DOMLevel(6, 1.0, "")])
    assert _prices(book.bids) == [5, 4, 1]
    assert _prices(book.asks) == [6]


def test_clear_empties_both_sides_and_returns_removed_rows():
    book = DepthBook()
    book.apply(BID, INSERT, 0, 1.0, 1.0)
    book.apply(ASK, INSERT, 0, 2.0, 1.0)
    assert book.clear() == ((DOMLevel(1.0, 1.0, ""),), (DOMLevel(2.0, 1.0, ""),))
    assert not book
    assert book.bids == () and book.asks == ()
    assert book.clear() == ((), ())


def test_repr_shows_both_sides():
    book = _book(3)
    assert repr(book) == (
        "DepthBook(bids=(DOMLevel(price=3, size=1.0, marketMaker=''),), asks=())"
    )


# ---------------------------------------------------------------------------
# Every view is a read-only snapshot
# ---------------------------------------------------------------------------


def test_book_sides_are_immutable_snapshots():
    book = _book(3, 2)
    bids = book.bids
    with pytest.raises((TypeError, AttributeError)):
        bids.append(DOMLevel(1, 1.0, ""))  # type: ignore[attr-defined]
    book.apply(BID, DELETE, 0, 0.0, 0.0)
    assert _prices(bids) == [3, 2]  # taken before the delete
    assert _prices(book.bids) == [2]


def test_book_row_mappings_are_detached():
    book = _book(3, 2)
    view = book.bidsByRow()
    assert view == {0: DOMLevel(3, 1.0, ""), 1: DOMLevel(2, 1.0, "")}
    book.apply(BID, DELETE, 0, 0.0, 0.0)
    assert len(view) == 2  # taken before the delete
    assert book.asksByRow() == {}


def test_ticker_sides_are_immutable_snapshots():
    ticker = ibi.Ticker()
    ticker.dom.apply(BID, INSERT, 0, 100.0, 1.0)
    ticker.dom.apply(BID, INSERT, 1, 99.0, 1.0)

    bids = ticker.domBids
    with pytest.raises((TypeError, AttributeError)):
        bids.append(DOMLevel(1, 1.0, ""))  # type: ignore[attr-defined]
    ticker.dom.apply(BID, DELETE, 0, 0.0, 0.0)
    assert _prices(bids) == [100.0, 99.0]  # taken before the delete
    assert _prices(ticker.domBids) == [99.0]
    assert ticker.domAsks == ()
    assert sorted(ticker.domBids, key=lambda row: row.price)  # usable as-is


def test_ticker_row_mappings_are_detached():
    ticker = ibi.Ticker()
    ticker.dom.apply(BID, INSERT, 0, 100.0, 1.0)
    view = ticker.domBidsDict
    assert view == {0: DOMLevel(100.0, 1.0, "")}
    assert ticker.domAsksDict == {}
    ticker.dom.apply(BID, DELETE, 0, 0.0, 0.0)
    assert view == {0: DOMLevel(100.0, 1.0, "")}  # taken before the delete
    assert ticker.domBidsDict == {}


def test_ticker_assignment_replaces_rows_without_sharing_the_input():
    ticker = ibi.Ticker()
    rows = [DOMLevel(5.0, 1.0, "")]
    ticker.domBids = rows
    ticker.domAsks = (DOMLevel(6.0, 1.0, ""),)
    rows.append(DOMLevel(4.0, 1.0, ""))  # the caller's list stays theirs
    assert _prices(ticker.domBids) == [5.0]
    assert _prices(ticker.domAsks) == [6.0]


def test_ticker_repr_hides_an_empty_book_and_shows_a_populated_one():
    ticker = ibi.Ticker()
    assert "dom=" not in repr(ticker)
    ticker.dom.apply(BID, INSERT, 0, 100.0, 1.0)
    assert "dom=DepthBook(bids=(DOMLevel(price=100.0" in repr(ticker)


# ---------------------------------------------------------------------------
# Wrapper integration
# ---------------------------------------------------------------------------


def test_mid_book_insert_and_delete_shift_rows():
    """Single-exchange depth sends inserts and deletes in the middle of the
    book; rows below must move rather than be overwritten or left as gaps."""
    ib, ticker = _depthTicker()
    update = ib.wrapper.updateMktDepthL2
    for row, price in enumerate([100.0, 99.0, 98.0]):
        update(1, row, "", INSERT, BID, price, 10)

    update(1, 1, "", INSERT, BID, 99.5, 4)  # new level between 100 and 99
    assert _prices(ticker.domBids) == [100.0, 99.5, 99.0, 98.0]

    update(1, 0, "", DELETE, BID, 0.0, 0)  # best bid leaves
    assert _prices(ticker.domBids) == [99.5, 99.0, 98.0]
    assert ticker.domBids[0] == DOMLevel(99.5, 4, "")


def test_delete_tick_reports_removed_price_and_zero_size():
    ib, ticker = _depthTicker()
    update = ib.wrapper.updateMktDepthL2
    update(1, 0, "", INSERT, ASK, 101.0, 10)
    update(1, 0, "", DELETE, ASK, 0.0, 0)
    tick = ticker.domTicks[-1]
    assert (tick.operation, tick.side, tick.price, tick.size) == (
        DELETE,
        ASK,
        101.0,
        0,
    )


def test_out_of_range_positions_never_raise():
    ib, ticker = _depthTicker()
    update = ib.wrapper.updateMktDepthL2
    update(1, 5, "", UPDATE, BID, 98.0, 1)  # below the rows held: dropped
    update(1, 0, "", UPDATE, BID, 100.0, 1)  # the next row down: kept
    update(1, 9, "", INSERT, BID, 99.0, 1)  # below the rows held: dropped
    update(1, 9, "", DELETE, BID, 0.0, 0)  # below the rows held: dropped
    assert _prices(ticker.domBids) == [100.0]
    assert len(ticker.domTicks) == 4  # every message is still reported


def test_market_depth_reset_emits_deletes_and_clears_book():
    ib, ticker = _depthTicker()
    update = ib.wrapper.updateMktDepthL2
    update(1, 0, "", INSERT, ASK, 101.0, 10)
    update(1, 0, "", INSERT, BID, 100.0, 10)
    ib.wrapper.tcpDataArrived()

    ib.wrapper.error(1, 317, "Market depth data has been RESET", "")

    assert not ticker.dom
    resets = [(t.side, t.price) for t in ticker.domTicks if t.operation == DELETE]
    assert resets == [(ASK, 101.0), (BID, 100.0)]
