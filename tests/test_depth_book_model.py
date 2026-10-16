"""Model-based tests of :class:`DepthBook`.

A DepthBook can hold fewer rows than TWS has. It must always be an exact
copy of TWS's top rows, even when TWS changes rows below the ones the
book holds.

The first test applies random inserts, updates and deletes at random rows,
starting from random prefixes, and compares both sides with a plain list
after each step. The second test converts target books into IBKR row
operations, with deletes first or inserts first, sends them through the
wrapper, and checks that the result equals the target.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import ib_async as ibi
from ib_async._subscriptions import MktDepthSub
from ib_async.depth import DepthBook, DepthOperation
from ib_async.objects import DOMLevel
from tests._property import examples

INSERT, UPDATE, DELETE = (
    DepthOperation.INSERT,
    DepthOperation.UPDATE,
    DepthOperation.DELETE,
)
BID, ASK = 1, 0
SIDES = (BID, ASK)


@dataclass
class _Side:
    tws: list[DOMLevel] = field(default_factory=list)


class PartialBookModel(RuleBasedStateMachine):
    """Compare a DepthBook with a plain list model of TWS's book.

    Each side of TWS's book is a list. The DepthBook may be subscribed with
    fewer rows, so it holds a prefix of that list and must stay an exact
    prefix after every operation."""

    def __init__(self) -> None:
        super().__init__()
        self.book = DepthBook()
        self.sides = {BID: _Side(), ASK: _Side()}
        self.step = 0

    def level(self, size: int) -> DOMLevel:
        self.step += 1
        return DOMLevel(float(self.step), float(size), "")

    @rule(side=st.sampled_from(SIDES), rows=st.integers(0, 12), held=st.integers(0, 12))
    def start_book_with_prefix(self, side, rows, held):
        tws = [self.level(1) for _ in range(rows)]
        self.sides[side].tws = tws
        self.book.setRows(side, tws[:held])

    @rule(side=st.sampled_from(SIDES), data=st.data(), size=st.integers(1, 9))
    def change_row(self, side, data, size):
        tws = self.sides[side].tws
        if not tws or data.draw(st.booleans()):
            operation, position = INSERT, data.draw(st.integers(0, len(tws)))
        else:
            operation = data.draw(st.sampled_from([UPDATE, DELETE]))
            position = data.draw(st.integers(0, len(tws) - 1))
        level = self.level(size)
        if operation == INSERT:
            tws.insert(position, level)
        elif operation == UPDATE:
            tws[position] = level
        else:
            del tws[position]
        self.book.apply(side, operation, position, level.price, level.size)

    @invariant()
    def book_is_prefix_of_tws(self):
        for side, rows in ((BID, self.book.bids), (ASK, self.book.asks)):
            assert list(rows) == self.sides[side].tws[: len(rows)], side


TestPartialBookModel = PartialBookModel.TestCase
TestPartialBookModel.settings = examples(150, stateful_step_count=60)


# -- replaying target books as IBKR row operations ----------------------------

Op = tuple[int, int, float, float, str]  # position, operation, price, size, maker
MAKERS = ("", "ARCA", "NSDQ", "EDGX")


def _deletesFirst(current: Sequence[DOMLevel], target: list[DOMLevel]) -> list[Op]:
    kept = {row.price for row in target}
    work = list(current)
    ops: list[Op] = []
    for row in reversed(range(len(work))):
        if work[row].price not in kept:
            ops.append((row, DELETE, 0.0, 0.0, ""))
            del work[row]
    for row, level in enumerate(target):
        if row >= len(work) or work[row].price != level.price:
            ops.append((row, INSERT, level.price, level.size, level.marketMaker))
            work.insert(row, level)
        elif work[row] != level:
            ops.append((row, UPDATE, level.price, level.size, level.marketMaker))
    return ops


def _insertsFirst(
    current: Sequence[DOMLevel], target: list[DOMLevel], side: int
) -> list[Op]:
    """Insert new levels before deleting old ones.

    The book briefly holds more rows than the target. This happens when a
    better price arrives at a full book before its worst row is deleted."""
    old = {row.price for row in current}
    merged = sorted(
        list(current) + [row for row in target if row.price not in old],
        key=lambda row: row.price,
        reverse=side == BID,
    )
    ops: list[Op] = []
    for row, level in enumerate(merged):
        if level.price not in old:
            ops.append((row, INSERT, level.price, level.size, level.marketMaker))
    kept = {row.price for row in target}
    work = list(merged)
    for row in reversed(range(len(work))):
        if work[row].price not in kept:
            ops.append((row, DELETE, 0.0, 0.0, ""))
            del work[row]
    for row, level in enumerate(target):
        if work[row] != level:
            ops.append((row, UPDATE, level.price, level.size, level.marketMaker))
    return ops


def book(side: int, mid: int) -> st.SearchStrategy[list[DOMLevel]]:
    """A book of unique prices on one side of ``mid``, best price first."""
    ticks = range(mid - 30, mid) if side == BID else range(mid + 1, mid + 31)
    return st.lists(st.sampled_from(list(ticks)), max_size=10, unique=True).map(
        lambda prices: [
            DOMLevel(price / 100, float(1 + price % 7), MAKERS[price % 4])
            for price in sorted(prices, reverse=side == BID)
        ]
    )


@st.composite
def bookSequences(draw: st.DrawFn) -> list[tuple[list[DOMLevel], list[DOMLevel]]]:
    mid = 10_000
    books = []
    for _ in range(draw(st.integers(1, 12))):
        mid += draw(st.integers(-3, 3))
        books.append((draw(book(BID, mid)), draw(book(ASK, mid))))
    return books


@given(books=bookSequences(), insertsFirst=st.booleans())
@examples(150)
def test_row_operations_reproduce_target_books(books, insertsFirst):
    ib = ibi.IB()
    contract = ibi.Stock("QQQ", "ISLAND", "USD", conId=1001)
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    ib.wrapper.subscriptions.add(MktDepthSub(reqId=1, contract=contract, ticker=ticker))
    update = ib.wrapper.updateMktDepthL2
    for bids, asks in books:
        for side, target in ((BID, bids), (ASK, asks)):
            current = ticker.domBids if side == BID else ticker.domAsks
            ops = (
                _insertsFirst(current, target, side)
                if insertsFirst
                else _deletesFirst(current, target)
            )
            for position, operation, price, size, maker in ops:
                update(1, position, maker, operation, side, price, size)
            after = ticker.domBids if side == BID else ticker.domAsks
            assert list(after) == target
        bidPrices = [row.price for row in ticker.domBids]
        askPrices = [row.price for row in ticker.domAsks]
        assert bidPrices == sorted(set(bidPrices), reverse=True)
        assert askPrices == sorted(set(askPrices))
