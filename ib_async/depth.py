"""Market-depth (DOM) order book maintained from IBKR row operations."""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Final

from ib_async.objects import DOMLevel

_logger = logging.getLogger(__name__)


class DepthOperation(IntEnum):
    """Row operation carried by ``updateMktDepth`` / ``updateMktDepthL2``."""

    INSERT = 0
    UPDATE = 1
    DELETE = 2


# Plain ints for the per-message comparisons (an enum attribute lookup
# costs more than the comparison itself).
_INSERT: Final = int(DepthOperation.INSERT)
_UPDATE: Final = int(DepthOperation.UPDATE)
_DELETE: Final = int(DepthOperation.DELETE)


@dataclass(slots=True)
class DepthBook:
    """Both sides of a market-depth order book, best price first.

    IBKR addresses depth by row: an insert pushes the rows at and below
    ``position`` down one, a delete pulls them up one, and an update
    replaces the row in place. Applying the stream in order keeps each
    side sorted and gap-free.

    The book always holds an exact copy of the top rows of TWS's book,
    even when it holds fewer rows than TWS (after a reset race, say). An
    operation below the rows held only moves rows that are not held, so
    it is dropped (and logged at DEBUG) rather than raised on or placed
    at the wrong row. An update to the row just below the last one held
    is TWS's next row, so it is kept and the copy grows back.

    The rows are held privately and only ever handed out as copies, so
    nothing a reader does to a returned value can change the book. Rows
    are immutable :class:`.DOMLevel` records, so every copy is a complete
    snapshot.
    """

    _bids: list[DOMLevel] = field(default_factory=list, init=False)
    _asks: list[DOMLevel] = field(default_factory=list, init=False)

    def __repr__(self) -> str:
        return f"DepthBook(bids={self.bids!r}, asks={self.asks!r})"

    def __bool__(self) -> bool:
        return bool(self._bids or self._asks)

    @property
    def bids(self) -> Sequence[DOMLevel]:
        """Snapshot of the bid side, best (highest) price first."""
        return tuple(self._bids)

    @property
    def asks(self) -> Sequence[DOMLevel]:
        """Snapshot of the ask side, best (lowest) price first."""
        return tuple(self._asks)

    def bidsByRow(self) -> Mapping[int, DOMLevel]:
        """Copy of the bid side keyed by row."""
        return dict(enumerate(self._bids))

    def asksByRow(self) -> Mapping[int, DOMLevel]:
        """Copy of the ask side keyed by row."""
        return dict(enumerate(self._asks))

    def apply(
        self,
        side: int,
        operation: int,
        position: int,
        price: float,
        size: float,
        marketMaker: str = "",
    ) -> DOMLevel | None:
        """Apply one row operation to the bid (``side=1``) or ask side.

        ``price``, ``size`` and ``marketMaker`` describe the new row for
        an insert or update; a delete ignores them.

        Returns:
            The row removed by a delete, otherwise None.
        """
        rows = self._bids if side else self._asks
        count = len(rows)
        if operation == _UPDATE:
            if 0 <= position < count:
                rows[position] = DOMLevel(price, size, marketMaker)
                return None
            if position == count:
                rows.append(DOMLevel(price, size, marketMaker))
                return None
        elif operation == _INSERT:
            if 0 <= position <= count:
                rows.insert(position, DOMLevel(price, size, marketMaker))
                return None
        elif operation == _DELETE:
            if 0 <= position < count:
                return rows.pop(position)
        _logger.debug(
            "dropped depth operation %s at row %s of a %s-row %s side",
            operation,
            position,
            count,
            "bid" if side else "ask",
        )
        return None

    def setRows(self, side: int, rows: Iterable[DOMLevel]) -> None:
        """Replace every row of the bid (``side=1``) or ask side."""
        (self._bids if side else self._asks)[:] = rows

    def clear(self) -> tuple[Sequence[DOMLevel], Sequence[DOMLevel]]:
        """Empty both sides.

        Returns:
            The removed ``(bids, asks)`` rows, best price first.
        """
        removed = (tuple(self._bids), tuple(self._asks))
        self._bids.clear()
        self._asks.clear()
        return removed
