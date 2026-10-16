"""A single-flight request whose send fails is withdrawn, never left open."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import ib_async as ibi
from ib_async._requests import SingletonKey


def _connectedIB(serverVersion: int) -> ibi.IB:
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.connState = ib.client.CONNECTED
    ib.client.conn = MagicMock()
    return ib


def test_current_time_in_millis_below_213_raises_and_leaves_nothing_open():
    ib = _connectedIB(212)

    with pytest.raises(ValueError, match="213"):
        ib.reqCurrentTimeInMillisAsync()
    assert SingletonKey("currentTimeInMillis") not in ib.wrapper.requests

    # A retry raises again instead of attaching to a future that can
    # never settle.
    with pytest.raises(ValueError, match="213"):
        ib.reqCurrentTimeInMillisAsync()
    assert SingletonKey("currentTimeInMillis") not in ib.wrapper.requests


def test_failed_send_is_withdrawn_and_a_later_call_sends_again():
    ib = _connectedIB(226)
    ib.client.reqPositions = MagicMock(side_effect=[ConnectionError("down"), None])

    with pytest.raises(ConnectionError):
        ib.reqPositionsAsync()
    assert SingletonKey("positions") not in ib.wrapper.requests

    future = ib.reqPositionsAsync()
    assert not future.done()
    assert ib.client.reqPositions.call_count == 2
    assert SingletonKey("positions") in ib.wrapper.requests


def test_concurrent_callers_share_one_send():
    ib = _connectedIB(226)
    ib.client.reqPositions = MagicMock()

    first = ib.reqPositionsAsync()
    second = ib.reqPositionsAsync()

    ib.client.reqPositions.assert_called_once()
    # Each caller has a future of its own; one answer settles both.
    assert first is not second
    ib.wrapper.requests.set_result(SingletonKey("positions"), ["p"])
    assert first.result() == second.result() == ["p"]
