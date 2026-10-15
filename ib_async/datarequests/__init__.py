"""Typed values for historical and real-time data requests.

Each request parameter with a fixed set of values has a ``Literal`` type
that accepts them as plain strings and as members of an enum, so both
spellings are checked by a type checker::

    ib.reqHistoricalData(contract, "", "30 D", "1 hour", "TRADES", True)
    ib.reqHistoricalData(
        contract, "", "30 D", BarSize.HOUR_1, WhatToShow.TRADES, True
    )

A value outside a parameter's type still reaches IBKR, which has the final
word; a type checker reports it first. ``durationStr``, a number and a
unit, is checked when a request is made: :func:`checkDuration`.

The values are generated from ``catalog.py``; see there to add one.
"""

from __future__ import annotations

import re

from .generated import *  # noqa: F403  (the enums and the parameter types)
from .generated import DurationUnit
from .generated import __all__ as _generated

_DURATION = re.compile(
    rf"[1-9][0-9]* ({'|'.join(unit.value for unit in DurationUnit)})"
)


def checkDuration(durationStr: str) -> str:
    """``durationStr`` if it is a historical data duration: a positive whole
    number, a space, and a :class:`DurationUnit` (S, D, W, M or Y), such as
    ``'30 D'``. Raises ValueError otherwise, saying what IBKR expects,
    instead of IBKR refusing the request later."""
    if not _DURATION.fullmatch(durationStr):
        units = ", ".join(f"{unit.value} {unit.name.lower()}" for unit in DurationUnit)
        raise ValueError(
            f"durationStr is a positive whole number, a space and a unit "
            f"({units}), such as '30 D' or '1 Y'; not {durationStr!r}"
        )
    return durationStr


__all__ = [*_generated, "checkDuration"]
