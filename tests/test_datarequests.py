"""The data request value types: generated from one catalog, accepting each
value as a string or an enum member, and the durationStr check."""

import asyncio
from typing import get_args

import pytest

import ib_async as ibi
from ib_async import datarequests
from ib_async.datarequests import (
    BarSize,
    BarSizeSetting,
    DurationUnit,
    HistoricalData,
    HistoricalTicksData,
    RealTimeBarsData,
    WhatToShow,
    checkDuration,
)
from ib_async.datarequests.catalog import FAMILIES, PARAMETERS


def test_each_family_has_unique_names_and_values() -> None:
    for family in FAMILIES:
        names = [name for name, _ in family.members]
        assert len(set(names)) == len(names), family.name
        assert len(set(family.values)) == len(family.values), family.name


def test_each_parameter_takes_values_of_its_family() -> None:
    for parameter in PARAMETERS:
        assert set(parameter.values) <= set(parameter.family.values), parameter.name


def test_a_parameter_type_accepts_its_strings_and_its_enum_members() -> None:
    assert set(get_args(RealTimeBarsData)) == {
        "TRADES",
        "MIDPOINT",
        "BID",
        "ASK",
        WhatToShow.TRADES,
        WhatToShow.MIDPOINT,
        WhatToShow.BID,
        WhatToShow.ASK,
    }
    # the other spellings IBKR documents are accepted as strings only
    ticks = set(get_args(HistoricalTicksData))
    assert {"Trades", "Midpoint", "Bid_Ask", WhatToShow.BID_ASK} <= ticks
    assert WhatToShow.BID not in ticks


def test_every_value_is_both_a_string_and_a_member() -> None:
    for alias, enum in (
        (HistoricalData, WhatToShow),
        (BarSizeSetting, BarSize),
    ):
        args = get_args(alias)
        for member in enum:
            assert member in args and member.value in args


def test_an_enum_member_is_its_value_on_the_wire() -> None:
    assert BarSize.HOUR_1 == "1 hour"
    assert f"{WhatToShow.ADJUSTED_LAST}" == "ADJUSTED_LAST"


def test_the_package_exports_the_types() -> None:
    for name in datarequests.__all__:
        assert getattr(ibi, name) is getattr(datarequests, name)


@pytest.mark.parametrize("duration", ["60 S", "30 D", "13 W", "6 M", "10 Y", "1 Y"])
def test_check_duration_accepts(duration: str) -> None:
    assert checkDuration(duration) == duration


@pytest.mark.parametrize(
    "duration",
    ["", "30", "D", "30D", "30  D", "30 d", "0 D", "-1 D", "1.5 D", "30 days", " 30 D"],
)
def test_check_duration_refuses(duration: str) -> None:
    with pytest.raises(ValueError, match="such as '30 D'"):
        checkDuration(duration)


def test_the_duration_message_names_every_unit() -> None:
    with pytest.raises(ValueError) as refused:
        checkDuration("30 days")
    for unit in DurationUnit:
        assert f"{unit.value} {unit.name.lower()}" in str(refused.value)


def test_requests_refuse_a_bad_duration_before_sending() -> None:
    """Nothing is sent (the IB is not even connected) and no request is
    left open."""
    ib = ibi.IB()
    contract = ibi.Stock("AAPL", "SMART", "USD")
    with pytest.raises(ValueError, match="durationStr"):
        asyncio.run(
            ib.reqHistoricalDataAsync(contract, "", "30 days", "1 hour", "TRADES", True)
        )
    with pytest.raises(ValueError, match="durationStr"):
        asyncio.run(ib.reqHistoricalScheduleAsync(contract, "2 weeks"))
    assert len(ib.wrapper.requests) == 0
