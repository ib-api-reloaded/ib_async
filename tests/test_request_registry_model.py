"""Model-based test of :class:`RequestRegistry`.

Hypothesis runs random sequences of the operations IB and Wrapper perform
on the registry:

- open a reqId request
- share a singleton request among several callers
- append a row
- end a request with a result or an error
- cancel or withdraw a request
- cancel one caller's future, as a timeout does
- advance the clock
- move a request to a new reqId, as after a bust event
- disconnect

After each step, the registry's ``answering``, ``get``, ``__contains__``
and ``__len__`` are compared with a simple model of the same history. Each
caller's future must be done exactly when the model says its request
ended, with the outcome the model expects.

At the end, the test answers every request still outstanding. The registry
must then be empty with no answers still expected, so no caller is left
waiting.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from ib_async._requests import (
    OWED_FOR,
    ReqIdKey,
    RequestKey,
    RequestRegistry,
    SingletonKey,
)
from ib_async.util import getLoop
from tests._property import machine

# As in IB, singleton requests are shared among callers, and each reqId
# request has a single caller.
SHARED_KEYS = [SingletonKey("positions"), SingletonKey("openOrders")]
OPENED_KEYS = [ReqIdKey(1), ReqIdKey(2), ReqIdKey(3)]
KEYS: list[RequestKey] = [*SHARED_KEYS, *OPENED_KEYS]

PENDING, RESULT, ERROR, CANCELLED = "pending", "result", "error", "cancelled"


@dataclass
class _Caller:
    """A caller's future and the outcome the model expects for it."""

    future: asyncio.Future
    expect: str = PENDING
    result: Any = None


@dataclass
class _Live:
    """The model's record of an outstanding request."""

    shared: bool
    args: tuple
    callers: list[_Caller]
    rows: list[Any] = field(default_factory=list)


class RegistryModel(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.loop = getLoop()
        self.now = 0.0
        self.reg = RequestRegistry(clock=lambda: self.now)
        self.live: dict[RequestKey, _Live] = {}
        # Per key: how many answers are still expected for abandoned
        # requests, and the time until which they are expected.
        self.owed: dict[RequestKey, tuple[int, float]] = {}
        self.callers: list[_Caller] = []

    # -- model -----------------------------------------------------------

    def flush(self) -> None:
        """Run the futures' done callbacks."""
        self.loop.run_until_complete(asyncio.sleep(0))

    def owing(self, key: RequestKey) -> int:
        count, until = self.owed.get(key, (0, 0.0))
        return count if self.now <= until else 0

    def settle(self, live: _Live, expect: str, result: Any = None) -> None:
        for caller in live.callers:
            caller.expect, caller.result = expect, result

    def abandoned(self, key: RequestKey) -> None:
        """Record that the last caller of ``key`` stopped waiting.

        The request's answer is still expected."""
        del self.live[key]
        self.owed[key] = (self.owing(key) + 1, self.now + OWED_FOR)

    def ended(self, key: RequestKey, expect: str) -> None:
        """Record an end message for ``key``.

        An end first counts against answers expected for abandoned
        requests. Only then does it end the outstanding request."""
        owing = self.owing(key)
        if owing:
            self.owed[key] = (owing - 1, self.owed[key][1])
        elif key in self.live:
            live = self.live.pop(key)
            self.settle(live, expect, list(live.rows))

    # -- client operations -----------------------------------------------

    @rule(key=st.sampled_from(OPENED_KEYS))
    def open(self, key: RequestKey) -> None:
        if key in self.live:
            with pytest.raises(RuntimeError):
                self.reg.open(key)
            return
        req = self.reg.open(key)
        caller = _Caller(req.future)
        self.callers.append(caller)
        self.live[key] = _Live(False, (), [caller])

    @rule(key=st.sampled_from(SHARED_KEYS), args=st.sampled_from([(), ("all",)]))
    def share(self, key: RequestKey, args: tuple) -> None:
        live = self.live.get(key)
        if live is not None and live.args != args:
            with pytest.raises(ValueError):
                self.reg.share(key, args=args)
            return
        shared = self.reg.share(key, args=args)
        assert shared.isNew == (live is None)
        caller = _Caller(shared.future)
        self.callers.append(caller)
        if live is None:
            self.live[key] = _Live(True, args, [caller])
        else:
            live.callers.append(caller)

    @rule(key=st.sampled_from(KEYS), data=st.data())
    def cancel_caller_future(self, key: RequestKey, data: st.DataObject) -> None:
        """Cancel one caller's future, as a timeout or task cancel does.

        The request stays open for its other callers. When the last caller
        is gone, the request is abandoned and its answer is still expected."""
        live = self.live.get(key)
        if live is None:
            return
        caller = live.callers.pop(data.draw(st.integers(0, len(live.callers) - 1)))
        caller.future.cancel()
        caller.expect = CANCELLED
        self.flush()
        if not live.callers:
            self.abandoned(key)

    @rule(key=st.sampled_from(KEYS))
    def cancel(self, key: RequestKey) -> None:
        self.reg.cancel(key, "not sent")
        if key in self.live:
            self.settle(self.live.pop(key), CANCELLED)
        self.flush()

    @rule(key=st.sampled_from(KEYS))
    def withdraw(self, key: RequestKey) -> None:
        self.reg.withdraw(key)
        self.owed.pop(key, None)
        if key in self.live:
            self.settle(self.live.pop(key), CANCELLED)
        self.flush()

    @rule(key=st.sampled_from(OPENED_KEYS), newKey=st.sampled_from(OPENED_KEYS))
    def move_to_new_reqid(self, key: RequestKey, newKey: RequestKey) -> None:
        """Move a request to an unused reqId, as after a bust event.

        The request is then found under the new key. An answer still
        expected under the old key stays expected under the old key."""
        if newKey == key or newKey in self.live:
            return
        moved = self.reg.move(key, newKey)
        assert (moved is not None) == (key in self.live)
        if key in self.live:
            self.live[newKey] = self.live.pop(key)

    @rule(seconds=st.floats(0, 2 * OWED_FOR))
    def advance_clock(self, seconds: float) -> None:
        self.now += seconds

    # -- server messages -------------------------------------------------

    @rule(key=st.sampled_from(KEYS), item=st.integers())
    def append_row(self, key: RequestKey, item: int) -> None:
        self.reg.append(key, item)
        if not self.owing(key) and key in self.live:
            self.live[key].rows.append(item)

    @rule(key=st.sampled_from(KEYS))
    def end_with_result(self, key: RequestKey) -> None:
        self.reg.set_result(key)
        self.ended(key, RESULT)
        self.flush()

    @rule(key=st.sampled_from(KEYS))
    def end_with_error(self, key: RequestKey) -> None:
        self.reg.set_error(key, RuntimeError("refused"))
        self.ended(key, ERROR)
        self.flush()

    @rule()
    def disconnect(self) -> None:
        self.reg.fail_all(ConnectionError("gone"))
        for live in self.live.values():
            self.settle(live, ERROR)
        self.live.clear()
        self.owed.clear()
        self.flush()

    # -- invariants ------------------------------------------------------

    @invariant()
    def registry_matches_model(self) -> None:
        for key in KEYS:
            assert (key in self.reg) == (key in self.live), key
            assert (self.reg.get(key) is not None) == (key in self.live), key
            assert self.reg.answering(key) == (
                key in self.live or self.owing(key) > 0
            ), key
        assert len(self.reg) == len(self.live)

    @invariant()
    def callers_match_model(self) -> None:
        for caller in self.callers:
            future = caller.future
            if caller.expect == PENDING:
                assert not future.done()
            elif caller.expect == CANCELLED:
                assert future.cancelled()
            elif caller.expect == RESULT:
                assert future.done() and not future.cancelled()
                assert future.result() == caller.result
            else:
                assert future.done() and not future.cancelled()
                assert future.exception() is not None

    def teardown(self) -> None:
        """Answer every outstanding request and check nothing is left."""
        for key in KEYS:
            while self.reg.answering(key):
                self.end_with_result(key)
        self.registry_matches_model()
        self.callers_match_model()
        assert len(self.reg) == 0 and not self.reg._owed
        assert all(caller.future.done() for caller in self.callers)


TestRegistryModel = RegistryModel.TestCase
TestRegistryModel.settings = machine()
