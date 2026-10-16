"""Property test of the connect startup sequence against a simulated TWS.

For any combination of fetchFields, readonly, managed accounts and chosen
account, connectAsync sends exactly the startup requests those settings
call for. When the server leaves some of them unanswered, connect either
raises ConnectionError and disconnects (raiseSyncErrors) or completes and
reports the timeouts in the log.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async import StartupFetch
from ib_async.util import getLoop
from tests._property import examples
from tests._sim import Ask, SimulatedTws

FLAGS = list(StartupFetch)
TIMEOUT = 0.05


def expectedRequests(
    fields: StartupFetch, readonly: bool, accounts: list[str], account: str
) -> dict[str, int]:
    """The requests connect sends before executions, by client method, with
    how many of each."""
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


def runUntil(tws: SimulatedTws, condition, limit: float) -> None:
    """Run the loop in short steps until ``condition()`` holds or ``limit``
    seconds have passed."""
    waited = 0.0
    step = TIMEOUT / 10
    while not condition() and waited < limit:
        tws.loop.run_until_complete(asyncio.sleep(step))
        waited += step


@given(
    flags=st.lists(st.sampled_from(FLAGS), unique=True),
    readonly=st.booleans(),
    accounts=st.lists(st.sampled_from(["DU1", "DU2", "DU3"]), min_size=1, unique=True),
    chooseAccount=st.booleans(),
    raiseSyncErrors=st.booleans(),
    unanswered=st.lists(
        st.sampled_from(
            [
                "reqPositions",
                "reqOpenOrders",
                "reqCompletedOrders",
                "reqAccountUpdates",
                "reqAccountUpdatesMulti",
                "reqExecutions",
            ]
        ),
        unique=True,
    ),
)
@examples(40)
def test_connect_sends_the_startup_requests_its_settings_call_for(
    flags, readonly, accounts, chooseAccount, raiseSyncErrors, unanswered
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
    tws.client.connectionStats.return_value = ibi.ConnectionStats(0.0, 0.0, 0, 0, 0, 0)
    tws.client.disconnect.side_effect = lambda: tws.wrapper.connectionClosed()

    task = tws.start(
        tws.ib.connectAsync(
            clientId=7,
            timeout=TIMEOUT,
            readonly=readonly,
            account=account,
            raiseSyncErrors=raiseSyncErrors,
            fetchFields=fields,
        )
    )
    expected = expectedRequests(fields, readonly, accounts, account)
    # With no first-batch requests, executions is sent at once.
    firstBatch = {k: v for k, v in counts(tws.asks).items() if k != "reqExecutions"}
    assert firstBatch == expected

    # The server answers what it answers; the rest time out.
    for ask in list(tws.asks):
        if ask.open and ask.kind not in unanswered and ask.kind != "reqExecutions":
            tws.answer(ask)
    executions = bool(fields & StartupFetch.EXECUTIONS)

    def firstBatchSettled() -> bool:
        pending = [a for a in tws.asks if a.kind != "reqExecutions" and a.open]
        sent = any(a.kind == "reqExecutions" for a in tws.asks)
        return not pending and (sent or not executions)

    # The first batch resolves at once when all answered, else after TIMEOUT;
    # executions is sent only after that.
    runUntil(tws, firstBatchSettled, TIMEOUT * 3)
    if executions:
        assert counts(tws.asks).get("reqExecutions") == 1
        if "reqExecutions" not in unanswered:
            for ask in tws.openAsks("reqExecutions"):
                tws.answer(ask)
    else:
        assert "reqExecutions" not in counts(tws.asks)

    timedOut = any(kind in unanswered for kind in expected) or (
        bool(executions) and "reqExecutions" in unanswered
    )
    loop.run_until_complete(asyncio.wait({task}, timeout=1))
    assert task.done()
    if timedOut and raiseSyncErrors:
        assert isinstance(task.exception(), ConnectionError)
        tws.client.disconnect.assert_called_once()
    else:
        assert task.result() is tws.ib
        tws.client.disconnect.assert_not_called()
