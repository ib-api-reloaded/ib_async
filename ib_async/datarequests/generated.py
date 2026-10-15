"""The values historical and real-time data requests take, generated from
``catalog.py`` by ``scripts/generate_datarequests.py``. Do not edit: change
the catalog and regenerate."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

__all__ = [
    "BarSize",
    "BarSizeSetting",
    "DurationUnit",
    "HistoricalData",
    "HistoricalTicksData",
    "RealTimeBarsData",
    "WhatToShow",
]


class WhatToShow(StrEnum):
    """The data a historical or real-time data request is built from."""

    TRADES = "TRADES"
    MIDPOINT = "MIDPOINT"
    BID = "BID"
    ASK = "ASK"
    BID_ASK = "BID_ASK"
    ADJUSTED_LAST = "ADJUSTED_LAST"
    HISTORICAL_VOLATILITY = "HISTORICAL_VOLATILITY"
    OPTION_IMPLIED_VOLATILITY = "OPTION_IMPLIED_VOLATILITY"
    REBATE_RATE = "REBATE_RATE"
    FEE_RATE = "FEE_RATE"
    YIELD_BID = "YIELD_BID"
    YIELD_ASK = "YIELD_ASK"
    YIELD_BID_ASK = "YIELD_BID_ASK"
    YIELD_LAST = "YIELD_LAST"
    SCHEDULE = "SCHEDULE"
    AGGTRADES = "AGGTRADES"


class BarSize(StrEnum):
    """The time period of one historical bar."""

    SEC_1 = "1 secs"
    SEC_5 = "5 secs"
    SEC_10 = "10 secs"
    SEC_15 = "15 secs"
    SEC_30 = "30 secs"
    MIN_1 = "1 min"
    MIN_2 = "2 mins"
    MIN_3 = "3 mins"
    MIN_4 = "4 mins"
    MIN_5 = "5 mins"
    MIN_10 = "10 mins"
    MIN_15 = "15 mins"
    MIN_20 = "20 mins"
    MIN_30 = "30 mins"
    HOUR_1 = "1 hour"
    HOUR_2 = "2 hours"
    HOUR_3 = "3 hours"
    HOUR_4 = "4 hours"
    HOUR_8 = "8 hours"
    DAY_1 = "1 day"
    WEEK_1 = "1 week"
    MONTH_1 = "1 month"


class DurationUnit(StrEnum):
    """The unit of a historical data request's durationStr, such as the D of '30 D'."""

    SECONDS = "S"
    DAYS = "D"
    WEEKS = "W"
    MONTHS = "M"
    YEARS = "Y"


#: The whatToShow of reqHistoricalData and reqHeadTimeStamp. SCHEDULE is for reqHistoricalSchedule; AGGTRADES is for crypto; the ``YIELD_*`` values are for bonds.
HistoricalData = Literal[
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
    WhatToShow.TRADES,
    WhatToShow.MIDPOINT,
    WhatToShow.BID,
    WhatToShow.ASK,
    WhatToShow.BID_ASK,
    WhatToShow.ADJUSTED_LAST,
    WhatToShow.HISTORICAL_VOLATILITY,
    WhatToShow.OPTION_IMPLIED_VOLATILITY,
    WhatToShow.REBATE_RATE,
    WhatToShow.FEE_RATE,
    WhatToShow.YIELD_BID,
    WhatToShow.YIELD_ASK,
    WhatToShow.YIELD_BID_ASK,
    WhatToShow.YIELD_LAST,
    WhatToShow.SCHEDULE,
    WhatToShow.AGGTRADES,
]


#: The whatToShow of reqRealTimeBars.
RealTimeBarsData = Literal[
    "TRADES",
    "MIDPOINT",
    "BID",
    "ASK",
    WhatToShow.TRADES,
    WhatToShow.MIDPOINT,
    WhatToShow.BID,
    WhatToShow.ASK,
]


#: The whatToShow of reqHistoricalTicks.
HistoricalTicksData = Literal[
    "TRADES",
    "MIDPOINT",
    "BID_ASK",
    "Trades",
    "Midpoint",
    "Bid_Ask",
    WhatToShow.TRADES,
    WhatToShow.MIDPOINT,
    WhatToShow.BID_ASK,
]


#: The barSizeSetting of reqHistoricalData and reqHistoricalSchedule.
BarSizeSetting = Literal[
    "1 secs",
    "5 secs",
    "10 secs",
    "15 secs",
    "30 secs",
    "1 min",
    "2 mins",
    "3 mins",
    "4 mins",
    "5 mins",
    "10 mins",
    "15 mins",
    "20 mins",
    "30 mins",
    "1 hour",
    "2 hours",
    "3 hours",
    "4 hours",
    "8 hours",
    "1 day",
    "1 week",
    "1 month",
    BarSize.SEC_1,
    BarSize.SEC_5,
    BarSize.SEC_10,
    BarSize.SEC_15,
    BarSize.SEC_30,
    BarSize.MIN_1,
    BarSize.MIN_2,
    BarSize.MIN_3,
    BarSize.MIN_4,
    BarSize.MIN_5,
    BarSize.MIN_10,
    BarSize.MIN_15,
    BarSize.MIN_20,
    BarSize.MIN_30,
    BarSize.HOUR_1,
    BarSize.HOUR_2,
    BarSize.HOUR_3,
    BarSize.HOUR_4,
    BarSize.HOUR_8,
    BarSize.DAY_1,
    BarSize.WEEK_1,
    BarSize.MONTH_1,
]
