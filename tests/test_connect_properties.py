"""Property test of the connect startup sequence against a simulated TWS.

For any combination of fetchFields, readonly, managed accounts and chosen
account, the test checks that connectAsync sends exactly the startup
requests those settings require, requests executions only after the first batch is
answered, and completes once every request is answered. The test does not
wait for any timeout, because the simulated server answers every request it
receives.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async import StartupFetch
from ib_async.util import getLoop
from tests._property import examples
from tests._sim import Ask, SimulatedTws

FLAGS = list(StartupFetch)


def expectedRequests(
    fields: StartupFetch, readonly: bool, accounts: list[str], account: str
) -> dict[str, int]:
    """Return the requests connect sends before executions, as a count per
    client method."""
    chosen = account or (accounts[0] if len(accounts) == 1 else "")
    expected: dict[str, int] = {}
    if fields & StartupFetch.POSITIONS:
        expected["reqPositions"] = 1
    if not readonly and fields & StartupFetch.ORDERS_OPEN:
        expected["reqOpenOrders"] = 1
    if not readonly and fields & StartupFetch.ORDERS_COMPLETE:
        expected["reqCompletedOrders"] = 1
    if chosen and fields & StartupFetch.ACCOUNT_UPDATES:
        expected["reqAccountUpdates"] = 1
    if fields & StartupFetch.SUB_ACCOUNT_UPDATES:
        expected["reqAccountUpdatesMulti"] = len(accounts)
    return expected


def counts(asks: list[Ask]) -> dict[str, int]:
    found: dict[str, int] = {}
    for ask in asks:
        found[ask.kind] = found.get(ask.kind, 0) + 1
    return found


@given(
    flags=st.lists(st.sampled_from(FLAGS), unique=True),
    readonly=st.booleans(),
    accounts=st.lists(st.sampled_from(["DU1", "DU2", "DU3"]), min_size=1, unique=True),
    chooseAccount=st.booleans(),
)
@examples()
def test_connect_sends_startup_requests_for_settings(
    flags, readonly, accounts, chooseAccount
):
    fields = StartupFetch(0)
    for flag in flags:
        fields |= flag
    account = accounts[0] if chooseAccount else ""
    loop = getLoop()
    tws = SimulatedTws(loop)
    tws.client.connectAsync = AsyncMock()
    tws.client.getAccounts.return_value = list(accounts)
    tws.client.serverVersion.return_value = 226
    tws.client.isReady.return_value = True

    task = tws.start(
        tws.ib.connectAsync(
            clientId=7,
            timeout=0,
            readonly=readonly,
            account=account,
            fetchFields=fields,
        )
    )
    expected = expectedRequests(fields, readonly, accounts, account)
    executions = bool(fields & StartupFetch.EXECUTIONS)
    firstBatch = {k: v for k, v in counts(tws.asks).items() if k != "reqExecutions"}
    assert firstBatch == expected
    # Connect requests executions after the first batch is answered, or
    # immediately if there is no first batch.
    assert ("reqExecutions" in counts(tws.asks)) == (executions and not expected)

    for ask in list(tws.asks):
        if ask.open and ask.kind != "reqExecutions":
            tws.answer(ask)
    if executions:
        assert counts(tws.asks).get("reqExecutions") == 1
        for ask in tws.openAsks("reqExecutions"):
            tws.answer(ask)
    else:
        assert "reqExecutions" not in counts(tws.asks)

    assert task.done() and task.result() is tws.ib
    assert not tws.openAsks()
    tws.client.disconnect.assert_not_called()
    assert ibi.StartupFetch.EXECUTIONS in fields or "reqExecutions" not in counts(
        tws.asks
    )
