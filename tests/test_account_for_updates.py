"""Which account connect subscribes to for portfolio and account updates."""

from __future__ import annotations

import logging

import ib_async as ibi
from ib_async import StartupFetch

ALL = StartupFetch.POSITIONS | StartupFetch.ACCOUNT_UPDATES


def test_the_given_account_or_the_only_one():
    ib = ibi.IB()
    assert ib._accountForUpdates("DU2", ["DU1", "DU2"], ALL) == "DU2"
    assert ib._accountForUpdates("", ["DU1"], ALL) == "DU1"


def test_several_accounts_and_none_chosen_is_said(caplog):
    """IBKR streams portfolio updates for one account at a time: with
    several accounts and none chosen, portfolio() stays empty, which the
    log says instead of leaving it silent."""
    ib = ibi.IB()
    with caplog.at_level(logging.INFO, logger="ib_async.ib"):
        assert ib._accountForUpdates("", ["DU1", "DU2"], ALL) == ""
    assert "portfolio() stays empty" in caplog.text
    assert "connect(account=...)" in caplog.text


def test_nothing_is_said_when_account_updates_are_not_fetched(caplog):
    ib = ibi.IB()
    with caplog.at_level(logging.INFO, logger="ib_async.ib"):
        ib._accountForUpdates("", ["DU1", "DU2"], StartupFetch.POSITIONS)
    assert "portfolio() stays empty" not in caplog.text
