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

from ..util import checkUnique


@dataclass(frozen=True, slots=True)
class Member:
    """One value of a family, and the name of its enum member."""

    name: str
    value: str


@dataclass(frozen=True, slots=True)
class Family:
    """The values of one kind, generated as a ``StrEnum``."""

    name: str
    doc: str
    # In the order to document them.
    members: tuple[Member, ...]

    def __post_init__(self) -> None:
        # A second member of the same value would be a silent enum alias.
        checkUnique(f"{self.name} member names", (m.name for m in self.members))
        checkUnique(f"{self.name} member values", (m.value for m in self.members))

    @property
    def values(self) -> tuple[str, ...]:
        return tuple(member.value for member in self.members)


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

    def __post_init__(self) -> None:
        unknown = [v for v in self.values if v not in self.family.values]
        if unknown:
            raise ValueError(f"{self.name}: not in {self.family.name}: {unknown}")


def _named(*values: str) -> tuple[Member, ...]:
    """Members named as their values."""
    return tuple(Member(value, value) for value in values)


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
        Member("SEC_1", "1 secs"),
        Member("SEC_5", "5 secs"),
        Member("SEC_10", "10 secs"),
        Member("SEC_15", "15 secs"),
        Member("SEC_30", "30 secs"),
        Member("MIN_1", "1 min"),
        Member("MIN_2", "2 mins"),
        Member("MIN_3", "3 mins"),
        Member("MIN_4", "4 mins"),
        Member("MIN_5", "5 mins"),
        Member("MIN_10", "10 mins"),
        Member("MIN_15", "15 mins"),
        Member("MIN_20", "20 mins"),
        Member("MIN_30", "30 mins"),
        Member("HOUR_1", "1 hour"),
        Member("HOUR_2", "2 hours"),
        Member("HOUR_3", "3 hours"),
        Member("HOUR_4", "4 hours"),
        Member("HOUR_8", "8 hours"),
        Member("DAY_1", "1 day"),
        Member("WEEK_1", "1 week"),
        Member("MONTH_1", "1 month"),
    ),
)

DURATION_UNIT = Family(
    name="DurationUnit",
    doc="The unit of a historical data request's durationStr, such as the D of '30 D'.",
    members=(
        Member("SECONDS", "S"),
        Member("DAYS", "D"),
        Member("WEEKS", "W"),
        Member("MONTHS", "M"),
        Member("YEARS", "Y"),
    ),
)

FAMILIES: tuple[Family, ...] = (WHAT_TO_SHOW, BAR_SIZE, DURATION_UNIT)

PARAMETERS: tuple[Parameter, ...] = (
    Parameter(
        name="HistoricalData",
        doc="The whatToShow of reqHistoricalData and reqHeadTimeStamp. "
        "AGGTRADES is for crypto; the ``YIELD_*`` values are for bonds. "
        "SCHEDULE, answered with a schedule rather than bars, is "
        "reqHistoricalSchedule's.",
        family=WHAT_TO_SHOW,
        values=tuple(v for v in WHAT_TO_SHOW.values if v != "SCHEDULE"),
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

# Every family and parameter is one name of the generated module.
checkUnique(
    "family and parameter names",
    [*(f.name for f in FAMILIES), *(p.name for p in PARAMETERS)],
)
