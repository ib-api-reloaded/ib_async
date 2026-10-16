"""Property tests for input checks at the API boundary.

- A duration string is accepted only if it is a count and a unit.
- Option strike months are accepted only in YYYYMM or YYYYMMDD form.
- An IBC command lists each set option once with its switch, and building
  it never raises.
- A Flex report built from any XML extracts its rows, and a file that is
  not XML raises FlexError.
- Tag value options are copied, not shared.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as et

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async.datarequests import checkDuration
from ib_async.flexreport import FlexError, FlexReport
from ib_async.ib import _optionSearches, _tagValueList
from ib_async.ibcontroller import _SWITCHES, IBC
from tests._property import examples

DURATION = re.compile(r"[1-9][0-9]* [SDWMY]")


@given(text=st.text(alphabet="0123456789 SDWMYsdX-", max_size=8))
@examples()
def test_duration_accepted_only_as_count_and_unit(text):
    if DURATION.fullmatch(text):
        assert checkDuration(text) == text
    else:
        with pytest.raises(ValueError, match="durationStr"):
            checkDuration(text)


months = st.one_of(
    st.text(alphabet="0123456789", max_size=9),
    st.text(max_size=8),
    st.sampled_from(["202612", "20261218"]),
)


@given(
    secType=st.sampled_from(["STK", "FUT", "CONTFUT", "OPT", "IND"]),
    symbol=st.sampled_from(["", "ES"]),
    exchange=st.sampled_from(["", "CME"]),
    monthList=st.lists(months, max_size=4),
)
@examples()
def test_option_strike_searches_accept_documented_months(
    secType, symbol, exchange, monthList
):
    underlying = ibi.Contract(
        secType=secType, symbol=symbol, exchange=exchange, currency="USD"
    )
    wellFormed = all(m.isdigit() and len(m) in (6, 8) for m in monthList)
    expectedOk = (
        secType in ("STK", "FUT", "CONTFUT")
        and symbol
        and monthList
        and wellFormed
        and (secType == "STK" or exchange)
    )
    try:
        searches = _optionSearches(underlying, monthList)
    except ValueError:
        assert not expectedOk
        return
    assert expectedOk
    assert [s.lastTradeDateOrContractMonth for s in searches] == list(
        dict.fromkeys(monthList)
    )
    assert all(s.secType == ("OPT" if secType == "STK" else "FOP") for s in searches)
    assert all(
        s.exchange == ("SMART" if secType == "STK" else exchange) for s in searches
    )
    assert all(s.symbol == symbol and s.conId == 0 for s in searches)


OPTIONS = [name for name in _SWITCHES if name not in ("twsVersion", "gateway")]


@given(
    twsVersion=st.sampled_from([1019, "10.19", 1030]),
    gateway=st.booleans(),
    windows=st.booleans(),
    values=st.dictionaries(
        st.sampled_from(OPTIONS),
        st.text(alphabet="abcXYZ019/:_-.", min_size=1, max_size=6),
        max_size=5,
    ),
)
@examples()
def test_ibc_command_lists_each_set_option_once(twsVersion, gateway, windows, values):
    ibc = IBC(twsVersion, gateway=gateway, **values)
    ibc._isWindows = windows
    command = ibc._command()
    assert command[0].endswith("StartIBC.bat" if windows else "ibcstart.sh")
    assert command[1] == str(twsVersion)
    rest = command[2:]
    assert ("/Gateway" in rest or "--gateway" in rest) == gateway
    # ibcPath always has a value. IBC uses its default install path if unset.
    options = {"ibcPath": ibc.ibcPath, **values}
    for name, value in options.items():
        switch = _SWITCHES[name][windows]
        found = [arg for arg in rest if arg.startswith(switch)] if switch else []
        if not switch:
            assert value not in rest, name  # omitted, not passed without a switch
        else:
            assert found == [f"{switch}{value}"], name
    # The command holds only the options above and the gateway switch.
    assert len(rest) == len([n for n in options if _SWITCHES[n][windows]]) + int(
        gateway
    )


topicNames = st.sampled_from(["TradeConfirm", "Order", "OpenPosition", "CashReport"])
attributeNames = st.sampled_from(["symbol", "quantity", "price", "currency", "when"])
attributeValues = st.one_of(
    st.integers(-(10**9), 10**9).map(str),
    st.floats(-1e9, 1e9, allow_nan=False).map(lambda f: repr(round(f, 4))),
    st.text(alphabet="ABCxyz- ", max_size=6),
)


@st.composite
def flexXml(draw: st.DrawFn) -> tuple[bytes, dict[str, list[dict[str, str]]]]:
    root = et.Element("FlexQueryResponse")
    rows: dict[str, list[dict[str, str]]] = {}
    for _ in range(draw(st.integers(0, 6))):
        topic = draw(topicNames)
        attributes = draw(
            st.dictionaries(attributeNames, attributeValues, min_size=1, max_size=4)
        )
        et.SubElement(root, topic, attrib=attributes)
        rows.setdefault(topic, []).append(attributes)
    return et.tostring(root), rows


def parsed(value: str) -> object:
    """The value FlexReport.extract(parseNumbers=True) returns for ``value``."""
    try:
        number = float(value)
    except ValueError:
        return value
    try:
        return int(value)
    except ValueError:
        return number


@given(report=flexXml())
@examples()
def test_flex_report_extracts_all_rows(report, tmp_path_factory):
    data, rows = report
    path = tmp_path_factory.mktemp("flex") / "report.xml"
    path.write_bytes(data)
    flex = FlexReport(path=path)
    assert flex.topics() == set(rows)
    for topic, expected in rows.items():
        extracted = flex.extract(topic, parseNumbers=False)
        assert [vars(row) for row in extracted] == expected
        numbers = flex.extract(topic)
        assert [vars(row) for row in numbers] == [
            {k: parsed(v) for k, v in attributes.items()} for attributes in expected
        ]


@given(junk=st.binary(max_size=40).filter(lambda b: not b.startswith(b"<")))
@examples()
def test_non_xml_file_raises_flex_error(junk, tmp_path_factory):
    path = tmp_path_factory.mktemp("flex") / "junk.xml"
    path.write_bytes(junk)
    with pytest.raises(FlexError):
        FlexReport(path=path)


@given(
    options=st.one_of(
        st.lists(st.builds(ibi.TagValue, st.text(max_size=4), st.text(max_size=4))),
        st.tuples(st.builds(ibi.TagValue, st.text(max_size=4), st.text(max_size=4))),
    )
)
@examples()
def test_tag_value_options_are_copied_not_shared(options):
    copied = _tagValueList(options)
    assert copied == list(options)
    assert copied is not options
