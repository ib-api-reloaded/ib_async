"""Stateful test of account values, account summary, positions and the
portfolio against a plain model.

The test requests account updates, model-level account updates, the
account summary and positions, in any order, while the simulated TWS
sends rows for live and finished requests, closes positions with a zero
or empty size, refuses summary requests and drops the socket. The model
is a set of dicts that use the same keys as IBKR. Account values are keyed
by account, tag, currency and model code. The summary is keyed by account,
tag and currency. Positions and portfolio rows are keyed by account and
conId.

After each step the test checks that accountValues(), positions(),
portfolio() and the account summary, with and without an account filter,
equal the model. It also checks that each row sent fires its event once.
A finished positions request returns the rows sent while it was open. A
finished summary request returns the summary filtered by account. After a
disconnect every store is empty and every open request has failed with
ConnectionError.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from decimal import Decimal

from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

import ib_async as ibi
from ib_async.objects import AccountValue
from ib_async.util import getLoop
from tests._property import machine
from tests._sim import Ask, SimulatedTws

ACCOUNTS = ["DU1", "DU2"]
MODELS = ["", "M1"]
TAGS = ["NetLiquidation", "BuyingPower", "CashBalance"]
CURRENCIES = ["USD", "EUR", "BASE"]
CONTRACTS = [
    ibi.Stock("A", "SMART", "USD", conId=10),
    ibi.Stock("B", "SMART", "USD", conId=11),
    ibi.Future("ES", "202612", "CME", conId=20),
]

accounts = st.sampled_from(ACCOUNTS)
tags = st.sampled_from(TAGS)
currencies = st.sampled_from(CURRENCIES)
contracts = st.sampled_from(CONTRACTS)
values = st.decimals(Decimal(-100000), Decimal(100000), places=2).map(str)
money = st.decimals(Decimal("0.01"), Decimal(10000), places=2)
# A position of None or zero means the position is closed.
sizes = st.one_of(
    st.none(),
    st.just(Decimal(0)),
    st.decimals(Decimal(-5000), Decimal(5000), places=4),
)


@dataclass
class Pending:
    """A request the test started and the server has not finished."""

    task: asyncio.Task
    ask: Ask
    account: str = ""
    rows: list[tuple] = field(default_factory=list)  # positions sent while open


def positionRows(positions: list[ibi.Position]) -> list[tuple]:
    return [(p.account, p.contract.conId, p.position, p.avgCost) for p in positions]


class AccountState(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.tws = SimulatedTws(getLoop())
        self.values: dict[tuple, str] = {}
        self.summary: dict[tuple, str] = {}
        self.positions: dict[tuple, tuple] = {}  # (account, conId) -> (size, cost)
        self.portfolio: dict[tuple, tuple] = {}  # (account, conId) -> (size, px, cost)
        self.accountUpdates: Pending | None = None
        self.positionsRequest: Pending | None = None
        self.summaryRequest: Pending | None = None
        self.multiAsks: list[Ask] = []  # finished model-level subscriptions
        self.summaryAsks: list[Ask] = []  # finished summary requests
        self.failed: list[asyncio.Task] = []  # requests open at a disconnect
        self.events = dict.fromkeys(("value", "summary", "position", "portfolio"), 0)
        self.expected = dict(self.events)
        ib = self.tws.ib
        ib.accountValueEvent += lambda v: self._count("value")
        ib.accountSummaryEvent += lambda v: self._count("summary")
        ib.positionEvent += lambda p: self._count("position")
        ib.updatePortfolioEvent += lambda p: self._count("portfolio")

    @property
    def ib(self) -> ibi.IB:
        return self.tws.ib

    def _count(self, name: str) -> None:
        self.events[name] += 1

    # -- account values ---------------------------------------------------

    @rule(account=accounts)
    def request_account_updates(self, account: str) -> None:
        if self.accountUpdates is not None or not self.tws.connected:
            return
        before = len(self.tws.asks)
        task = self.tws.start(self.ib.reqAccountUpdatesAsync(account))
        assert len(self.tws.asks) == before + 1
        ask = self.tws.asks[-1]
        assert ask.kind == "reqAccountUpdates" and ask.args == (True, account)
        self.accountUpdates = Pending(task, ask, account)

    @rule()
    def end_account_updates(self) -> None:
        if self.accountUpdates is None:
            return
        self.tws.accountUpdatesEnd(self.accountUpdates.ask)
        task = self.accountUpdates.task
        assert task.done() and task.exception() is None
        self.accountUpdates = None

    @rule(account=accounts, tag=tags, currency=currencies, value=values)
    def send_account_value(self, account, tag, currency, value) -> None:
        self.tws.accountValue(account, tag, value, currency)
        self.values[(account, tag, currency, "")] = value
        self.expected["value"] += 1

    @rule(account=accounts, model=st.sampled_from(MODELS), rows=st.integers(0, 2))
    def request_account_updates_multi(self, account, model, rows) -> None:
        if not self.tws.connected:
            return
        before = len(self.tws.asks)
        task = self.tws.start(self.ib.reqAccountUpdatesMultiAsync(account, model))
        assert len(self.tws.asks) == before + 1
        ask = self.tws.asks[-1]
        assert ask.kind == "reqAccountUpdatesMulti"
        assert ask.args[1:3] == (account, model)
        for i in range(rows):
            self.tws.accountValueMulti(ask, TAGS[i], str(i), "USD")
            self.values[(account, TAGS[i], "USD", model)] = str(i)
            self.expected["value"] += 1
        self.tws.wrapper.accountUpdateMultiEnd(ask.reqId)
        ask.answered = True
        self.tws.run()
        assert task.done() and task.exception() is None
        self.multiAsks.append(ask)

    @rule(data=st.data(), tag=tags, currency=currencies, value=values)
    def send_account_value_multi(self, data, tag, currency, value) -> None:
        """A model-level subscription keeps sending values after its first
        download ends."""
        if not self.multiAsks:
            return
        ask = data.draw(st.sampled_from(self.multiAsks))
        self.tws.accountValueMulti(ask, tag, value, currency)
        self.values[(ask.args[1], tag, currency, ask.args[2])] = value
        self.expected["value"] += 1

    # -- account summary --------------------------------------------------

    @rule(account=st.sampled_from(["", *ACCOUNTS]))
    def request_summary(self, account: str) -> None:
        """accountSummaryAsync requests the summary once, then answers from
        the store."""
        if self.summaryRequest is not None or not self.tws.connected:
            return
        before = len(self.tws.asks)
        task = self.tws.start(self.ib.accountSummaryAsync(account))
        if self.summary:
            assert len(self.tws.asks) == before
            assert task.done()
            assert set(task.result()) == self._summaryRows(account)
            return
        assert len(self.tws.asks) == before + 1
        ask = self.tws.asks[-1]
        assert ask.kind == "reqAccountSummary"
        assert not task.done()
        self.summaryRequest = Pending(task, ask, account)

    @rule(rows=st.lists(st.tuples(accounts, tags, currencies, values), max_size=3))
    def answer_summary(self, rows) -> None:
        if self.summaryRequest is None:
            return
        pending = self.summaryRequest
        for account, tag, currency, value in rows:
            self.tws.summaryValue(pending.ask, account, tag, value, currency)
            self.summary[(account, tag, currency)] = value
            self.expected["summary"] += 1
        self.tws.summaryEnd(pending.ask)
        assert pending.task.done()
        assert set(pending.task.result()) == self._summaryRows(pending.account)
        self.summaryAsks.append(pending.ask)
        self.summaryRequest = None

    @rule()
    def refuse_summary(self) -> None:
        if self.summaryRequest is None:
            return
        pending = self.summaryRequest
        self.tws.refuse(pending.ask)
        # A refused request settles with an empty answer and logs the error.
        assert pending.task.done()
        assert set(pending.task.result()) == self._summaryRows(pending.account)
        self.summaryRequest = None

    @rule(data=st.data(), account=accounts, tag=tags, currency=currencies, value=values)
    def send_summary_value(self, data, account, tag, currency, value) -> None:
        """A summary request is a subscription. Values keep arriving after
        its end message."""
        if not self.summaryAsks:
            return
        ask = data.draw(st.sampled_from(self.summaryAsks))
        self.tws.summaryValue(ask, account, tag, value, currency)
        self.summary[(account, tag, currency)] = value
        self.expected["summary"] += 1

    def _summaryRows(self, account: str) -> set[AccountValue]:
        return {
            AccountValue(a, t, v, c, "")
            for (a, t, c), v in self.summary.items()
            if not account or a == account
        }

    # -- positions and portfolio ------------------------------------------

    @rule(account=accounts, contract=contracts, size=sizes, cost=money)
    def send_position(self, account, contract, size, cost) -> None:
        self.tws.positionUpdate(account, contract, size, cost)
        key = (account, contract.conId)
        if size:
            self.positions[key] = (size, cost)
        else:
            self.positions.pop(key, None)
        if self.positionsRequest is not None:
            self.positionsRequest.rows.append((account, contract.conId, size, cost))
        self.expected["position"] += 1

    @rule()
    def request_positions(self) -> None:
        if self.positionsRequest is not None or not self.tws.connected:
            return
        before = len(self.tws.asks)
        task = self.tws.start(self.ib.reqPositionsAsync())
        assert len(self.tws.asks) == before + 1
        ask = self.tws.asks[-1]
        assert ask.kind == "reqPositions"
        self.positionsRequest = Pending(task, ask)

    @rule()
    def end_positions(self) -> None:
        """The positions request returns every row sent while it was open,
        closed positions included."""
        if self.positionsRequest is None:
            return
        pending = self.positionsRequest
        self.tws.positionsEnd(pending.ask)
        assert pending.task.done()
        assert positionRows(pending.task.result()) == pending.rows
        self.positionsRequest = None

    @rule(account=accounts, contract=contracts, size=sizes, px=money, cost=money)
    def send_portfolio(self, account, contract, size, px, cost) -> None:
        self.tws.portfolioUpdate(account, contract, size, px, cost)
        key = (account, contract.conId)
        if size:
            self.portfolio[key] = (size, px, cost)
        else:
            self.portfolio.pop(key, None)
        self.expected["portfolio"] += 1

    # -- connection -------------------------------------------------------

    @rule()
    def disconnect(self) -> None:
        if not self.tws.connected:
            return
        self.tws.disconnect()
        for pending in (
            self.accountUpdates,
            self.positionsRequest,
            self.summaryRequest,
        ):
            if pending is not None:
                self.failed.append(pending.task)
        self.accountUpdates = self.positionsRequest = self.summaryRequest = None
        self.multiAsks.clear()
        self.summaryAsks.clear()
        self.values.clear()
        self.summary.clear()
        self.positions.clear()
        self.portfolio.clear()

    @rule()
    def reconnect(self) -> None:
        self.tws.reconnect()

    # -- invariants -------------------------------------------------------

    @invariant()
    def account_values_match_model(self) -> None:
        expected = {
            AccountValue(a, t, v, c, m) for (a, t, c, m), v in self.values.items()
        }
        assert set(self.ib.accountValues()) == expected
        for account in ACCOUNTS:
            assert set(self.ib.accountValues(account)) == {
                v for v in expected if v.account == account
            }

    @invariant()
    def summary_matches_model(self) -> None:
        assert set(self.ib.wrapper.acctSummary.values()) == self._summaryRows("")

    @invariant()
    def positions_match_model(self) -> None:
        rows = {(a, c, s, k) for (a, c), (s, k) in self.positions.items()}
        assert set(positionRows(self.ib.positions())) == rows
        for account in ACCOUNTS:
            assert set(positionRows(self.ib.positions(account))) == {
                r for r in rows if r[0] == account
            }

    @invariant()
    def portfolio_matches_model(self) -> None:
        def rows(items: list[ibi.PortfolioItem]) -> set[tuple]:
            return {
                (i.account, i.contract.conId, i.position, i.marketPrice, i.averageCost)
                for i in items
            }

        expected = {(a, c, s, px, k) for (a, c), (s, px, k) in self.portfolio.items()}
        assert rows(self.ib.portfolio()) == expected
        for account in ACCOUNTS:
            assert rows(self.ib.portfolio(account)) == {
                r for r in expected if r[0] == account
            }

    @invariant()
    def each_row_fires_its_event_once(self) -> None:
        assert self.events == self.expected

    @invariant()
    def requests_open_at_disconnect_failed(self) -> None:
        for task in self.failed:
            assert task.done() and isinstance(task.exception(), ConnectionError)

    def teardown(self) -> None:
        for pending in (
            self.accountUpdates,
            self.positionsRequest,
            self.summaryRequest,
        ):
            if pending is not None:
                pending.task.cancel()
        self.tws.run()


TestAccountState = AccountState.TestCase
TestAccountState.settings = machine()
