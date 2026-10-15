"""The values historical and real-time data requests take: the single
source of truth.

``generated.py`` (one ``StrEnum`` per family, one ``Literal`` per
parameter) is generated from this catalog by
``scripts/generate_datarequests.py``; ``make ruff`` fails when it is out
of date.

A family lists every value of a kind, such as every bar size. A parameter
lists the values one request parameter accepts, a subset of its family:
real-time bars take four of the historical data sources. Each parameter
accepts its values as plain strings and as members of the family's enum.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Family:
    """The values of one kind, generated as a ``StrEnum``."""

    name: str
    doc: str
    # (member name, value) pairs, in the order to document them.
    members: tuple[tuple[str, str], ...]

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(value for _, value in self.members)


@dataclass(frozen=True, slots=True)
class Parameter:
    """The values one request parameter accepts, generated as a
    ``Literal`` of the plain strings and the family's enum members."""

    name: str
    doc: str
    family: Family
    values: tuple[str, ...]
    # Other spellings IBKR documents for the same values, accepted as
    # strings only.
    spellings: tuple[str, ...] = ()


def _named(*values: str) -> tuple[tuple[str, str], ...]:
    """Members named as their values."""
    return tuple((value, value) for value in values)


WHAT_TO_SHOW = Family(
    name="WhatToShow",
    doc="The data a historical or real-time data request is built from.",
    members=_named(
        "TRADES",
        "MIDPOINT",
        "BID",
        "ASK",
        "BID_ASK",
        "ADJUSTED_LAST",
        "HISTORICAL_VOLATILITY",
        "OPTION_IMPLIED_VOLATILITY",
        "REBATE_RATE",
        "FEE_RATE",
        "YIELD_BID",
        "YIELD_ASK",
        "YIELD_BID_ASK",
        "YIELD_LAST",
        "SCHEDULE",
        "AGGTRADES",
    ),
)

BAR_SIZE = Family(
    name="BarSize",
    doc="The time period of one historical bar.",
    members=(
        ("SEC_1", "1 secs"),
        ("SEC_5", "5 secs"),
        ("SEC_10", "10 secs"),
        ("SEC_15", "15 secs"),
        ("SEC_30", "30 secs"),
        ("MIN_1", "1 min"),
        ("MIN_2", "2 mins"),
        ("MIN_3", "3 mins"),
        ("MIN_4", "4 mins"),
        ("MIN_5", "5 mins"),
        ("MIN_10", "10 mins"),
        ("MIN_15", "15 mins"),
        ("MIN_20", "20 mins"),
        ("MIN_30", "30 mins"),
        ("HOUR_1", "1 hour"),
        ("HOUR_2", "2 hours"),
        ("HOUR_3", "3 hours"),
        ("HOUR_4", "4 hours"),
        ("HOUR_8", "8 hours"),
        ("DAY_1", "1 day"),
        ("WEEK_1", "1 week"),
        ("MONTH_1", "1 month"),
    ),
)

DURATION_UNIT = Family(
    name="DurationUnit",
    doc="The unit of a historical data request's durationStr, such as the D of '30 D'.",
    members=(
        ("SECONDS", "S"),
        ("DAYS", "D"),
        ("WEEKS", "W"),
        ("MONTHS", "M"),
        ("YEARS", "Y"),
    ),
)

FAMILIES: tuple[Family, ...] = (WHAT_TO_SHOW, BAR_SIZE, DURATION_UNIT)

PARAMETERS: tuple[Parameter, ...] = (
    Parameter(
        name="HistoricalData",
        doc="The whatToShow of reqHistoricalData and reqHeadTimeStamp. "
        "SCHEDULE is for reqHistoricalSchedule; AGGTRADES is for crypto; "
        "the ``YIELD_*`` values are for bonds.",
        family=WHAT_TO_SHOW,
        values=WHAT_TO_SHOW.values,
    ),
    Parameter(
        name="RealTimeBarsData",
        doc="The whatToShow of reqRealTimeBars.",
        family=WHAT_TO_SHOW,
        values=("TRADES", "MIDPOINT", "BID", "ASK"),
    ),
    Parameter(
        name="HistoricalTicksData",
        doc="The whatToShow of reqHistoricalTicks.",
        family=WHAT_TO_SHOW,
        values=("TRADES", "MIDPOINT", "BID_ASK"),
        spellings=("Trades", "Midpoint", "Bid_Ask"),
    ),
    Parameter(
        name="BarSizeSetting",
        doc="The barSizeSetting of reqHistoricalData and reqHistoricalSchedule.",
        family=BAR_SIZE,
        values=BAR_SIZE.values,
    ),
)
