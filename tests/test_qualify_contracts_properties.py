"""Property test for qualifyContracts and qualifyContractDetails.

For any list of contract details IBKR returns:

- If there is exactly one match, the caller's contract is updated in
  place from it. When the query has a secType and several details are
  returned, only details with that secType count as matches.
- A query for SMART keeps SMART as its exchange.
- If there is no match or more than one, the contract is unchanged.
- qualifyContracts returns the contract itself, or None (with returnAll,
  the possible contracts of an ambiguous answer).
- qualifyContractDetails returns the matching details, whose contract is
  the caller's contract, or None.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async.util import dataclassAsDict, getLoop
from tests._property import examples
from tests._sim import SimulatedTws

details = st.lists(
    st.builds(
        ibi.ContractDetails,
        contract=st.builds(
            ibi.Contract,
            secType=st.sampled_from(["STK", "OPT", "FUT"]),
            conId=st.integers(1, 10**6),
            symbol=st.just("X"),
            exchange=st.sampled_from(["ISLAND", "ARCA", "CME"]),
            currency=st.just("USD"),
        ),
        longName=st.sampled_from(["", "X Corp"]),
    ),
    max_size=4,
)

Qualified = ibi.Contract | list[ibi.Contract | None] | ibi.ContractDetails | None
Qualify = Callable[[ibi.IB, ibi.Contract], Awaitable[list[Qualified]]]


def qualified(
    query: ibi.Contract, answered: list[ibi.ContractDetails], qualify: Qualify
) -> Qualified:
    loop = getLoop()
    tws = SimulatedTws(loop)
    task = tws.start(qualify(tws.ib, query))
    tws.answerContractDetails(tws.openAsks("reqContractDetails")[0], answered)
    loop.run_until_complete(asyncio.sleep(0))
    [result] = task.result()
    return result


def matching(
    secType: str, answered: list[ibi.ContractDetails]
) -> list[ibi.ContractDetails]:
    if secType and len(answered) > 1:
        return [d for d in answered if d.contract and d.contract.secType == secType]
    return answered


def contractOf(d: ibi.ContractDetails) -> ibi.Contract:
    assert d.contract is not None
    return d.contract


@given(
    secType=st.sampled_from(["", "STK", "OPT"]),
    exchange=st.sampled_from(["SMART", "ISLAND"]),
    answered=details,
    returnAll=st.booleans(),
)
@examples()
def test_unique_match_qualifies_contract_in_place(
    secType: str, exchange: str, answered: list[ibi.ContractDetails], returnAll: bool
) -> None:
    query = ibi.Contract(secType=secType, symbol="X", exchange=exchange, currency="USD")
    before = dataclassAsDict(query)
    matches = matching(secType, answered)
    possibles = [dataclassAsDict(contractOf(d)) for d in matches]

    result = qualified(
        query, answered, lambda ib, c: ib.qualifyContractsAsync(c, returnAll=returnAll)
    )

    if len(matches) == 1:
        [match] = possibles
        assert result is query
        assert query.conId == match["conId"]
        assert query.secType == match["secType"]
        # SMART stays SMART. Otherwise the exchange comes from the details.
        assert query.exchange == ("SMART" if exchange == "SMART" else match["exchange"])
    else:
        assert dataclassAsDict(query) == before
        if not answered or not returnAll:
            assert result is None
        else:
            assert isinstance(result, list)
            assert [c and dataclassAsDict(c) for c in result] == possibles


@given(
    secType=st.sampled_from(["", "STK", "OPT"]),
    exchange=st.sampled_from(["SMART", "ISLAND"]),
    answered=details,
)
@examples()
def test_details_are_the_unique_match_holding_the_contract(
    secType: str, exchange: str, answered: list[ibi.ContractDetails]
) -> None:
    query = ibi.Contract(secType=secType, symbol="X", exchange=exchange, currency="USD")
    before = dataclassAsDict(query)
    matches = matching(secType, answered)
    possibles = [dataclassAsDict(contractOf(d)) for d in matches]

    result = qualified(query, answered, lambda ib, c: ib.qualifyContractDetailsAsync(c))

    if len(matches) == 1:
        [match] = possibles
        assert isinstance(result, ibi.ContractDetails) and result is matches[0]
        assert result.contract is query
        assert query.conId == match["conId"]
        assert query.exchange == ("SMART" if exchange == "SMART" else match["exchange"])
    else:
        assert result is None
        assert dataclassAsDict(query) == before
