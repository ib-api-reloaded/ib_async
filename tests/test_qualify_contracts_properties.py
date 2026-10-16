"""Property test for qualifyContracts.

For any list of contract details IBKR returns:

- If there is exactly one match, the caller's contract is updated in
  place from it. When the query has a secType and several details are
  returned, only details with that secType count as matches.
- A query for SMART keeps SMART as its exchange.
- If there is no match or more than one, the contract is unchanged.
"""

from __future__ import annotations

import asyncio

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
    ),
    max_size=4,
)


@given(
    secType=st.sampled_from(["", "STK", "OPT"]),
    exchange=st.sampled_from(["SMART", "ISLAND"]),
    answered=details,
    returnAll=st.booleans(),
)
@examples(300)
def test_unique_match_qualifies_contract_in_place(
    secType, exchange, answered, returnAll
):
    loop = getLoop()
    tws = SimulatedTws(loop)
    query = ibi.Contract(secType=secType, symbol="X", exchange=exchange, currency="USD")
    before = dataclassAsDict(query)
    task = tws.start(tws.ib.qualifyContractsAsync(query, returnAll=returnAll))
    tws.answerContractDetails(tws.openAsks("reqContractDetails")[0], answered)
    loop.run_until_complete(asyncio.sleep(0))
    [result] = task.result()

    candidates = [d.contract for d in answered]
    if secType and len(candidates) > 1:
        matching = [c for c in candidates if c.secType == secType]
    else:
        matching = candidates
    if len(matching) == 1:
        match = matching[0]
        assert result is query
        assert query.conId == match.conId
        assert query.secType == match.secType
        # SMART stays SMART. Otherwise the exchange comes from the details.
        assert query.exchange == ("SMART" if exchange == "SMART" else match.exchange)
    else:
        assert dataclassAsDict(query) == before
        if not candidates or not returnAll:
            assert result is None
        else:
            assert result == (matching if secType else candidates)
