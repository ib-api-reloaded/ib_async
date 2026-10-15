"""connect syncs only what StartupFetch asks for."""

from __future__ import annotations

from unittest.mock import MagicMock

import ib_async as ibi
from ib_async import StartupFetch


def _ib() -> ibi.IB:
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.isConnected.return_value = False
    ib.client.serverVersion.return_value = 200
    ib.client.getReqId.side_effect = iter(range(100, 200))
    return ib


def test_positions_only_when_asked_for():
    ib = _ib()
    fetch = StartupFetch.ORDERS_OPEN | StartupFetch.ACCOUNT_UPDATES
    names = ib._startupRequests(fetch, False, "DU1", ["DU1"])
    assert set(names) == {"open orders", "account updates"}
    ib.client.reqPositions.assert_not_called()


def test_everything_when_asked_for():
    ib = _ib()
    names = ib._startupRequests(ibi.StartupFetchALL, False, "DU1", ["DU1"])
    assert set(names) == {
        "positions",
        "open orders",
        "completed orders",
        "account updates",
        "account updates for DU1",
    }
