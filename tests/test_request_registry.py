"""Unit tests for ib_async._requests.RequestRegistry.

The registry is the source of truth for in-flight request correlation.
These tests exercise it in isolation: no Wrapper, no IB client, no
network. They cover the documented invariants:

  * discriminated keys do not collide
  * single_flight dedupes; non-single_flight raises on duplicate
  * append/set_result/set_error/cancel are idempotent
  * fail_all wakes every awaiter and empties the registry
  * each caller of a single-flight request has a future of its own;
    the last caller to leave ends the request
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from ib_async._requests import (
    OWED_FOR,
    CompositeKey,
    ReqIdKey,
    Request,
    RequestRegistry,
    SingletonKey,
    WhatIfKey,
)

# (asyncio_mode="auto" in pyproject.toml takes care of marking async tests)


# --- key types --------------------------------------------------------------


def test_keys_are_disjoint_by_type():
    """Same numeric / string identity does not collide across key types."""
    assert ReqIdKey(5) != WhatIfKey(5)
    assert ReqIdKey(5) != SingletonKey("5")
    assert SingletonKey("openOrders") != CompositeKey("openOrders")
    assert hash(ReqIdKey(5)) != hash(WhatIfKey(5)) or ReqIdKey(5) != WhatIfKey(5)


def test_keys_are_hashable_and_equal_by_value():
    assert ReqIdKey(7) == ReqIdKey(7)
    assert SingletonKey("x") == SingletonKey("x")
    assert CompositeKey("marketRule", (10,)) == CompositeKey("marketRule", (10,))
    s = {ReqIdKey(7), ReqIdKey(7), ReqIdKey(8)}
    assert len(s) == 2


# --- open / single_flight ---------------------------------------------------


async def test_open_creates_fresh_request():
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(1))
    assert isinstance(req, Request)
    assert isinstance(req.future, asyncio.Future)
    assert req.container == []
    assert req.followers == []
    assert ReqIdKey(1) in reg


async def test_open_duplicate_without_single_flight_raises():
    reg = RequestRegistry()
    reg.open(ReqIdKey(2))
    with pytest.raises(RuntimeError):
        reg.open(ReqIdKey(2))


async def test_sharing_attaches_to_the_request_in_flight():
    reg = RequestRegistry()
    first = reg.share(SingletonKey("openOrders"))
    second = reg.share(SingletonKey("openOrders"))
    assert (first.isNew, second.isNew) == (True, False)
    assert first.future is not second.future
    req = reg.get(SingletonKey("openOrders"))
    assert req is not None and req.followers == [first.future, second.future]


async def test_sharing_refuses_a_request_with_other_arguments():
    reg = RequestRegistry()
    reg.share(SingletonKey("completedOrders"), args=(True,))
    with pytest.raises(ValueError, match="must wait for its answer"):
        reg.share(SingletonKey("completedOrders"), args=(False,))


async def test_open_after_settle_creates_fresh_request():
    reg = RequestRegistry()
    first = reg.open(SingletonKey("positions"))
    reg.set_result(SingletonKey("positions"), [])
    second = reg.open(SingletonKey("positions"))
    assert second is not first and not second.future.done()


# --- append -----------------------------------------------------------------


async def test_append_accumulates():
    reg = RequestRegistry()
    reg.open(ReqIdKey(3))
    reg.append(ReqIdKey(3), "a")
    reg.append(ReqIdKey(3), "b")
    req = reg.get(ReqIdKey(3))
    assert req is not None
    assert req.container == ["a", "b"]


async def test_append_after_settle_is_noop():
    """The original 'completedOrder after end' KeyError class of bug."""
    reg = RequestRegistry()
    reg.open(SingletonKey("completedOrders"))
    reg.set_result(SingletonKey("completedOrders"))  # uses container
    # second wave of events arrives after end-of-stream callback:
    reg.append(SingletonKey("completedOrders"), "stray")
    # silent no-op, no exception


async def test_append_on_missing_key_is_noop():
    reg = RequestRegistry()
    reg.append(ReqIdKey(99), "x")  # never opened — must not raise


# --- set_result / set_error / cancel ---------------------------------------


async def test_set_result_with_accumulator():
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(4))
    reg.append(ReqIdKey(4), 1)
    reg.append(ReqIdKey(4), 2)
    reg.set_result(ReqIdKey(4))
    assert req.future.result() == [1, 2]
    assert req.settled is True
    assert ReqIdKey(4) not in reg


async def test_set_result_with_explicit_value():
    reg = RequestRegistry()
    req = reg.open(SingletonKey("currentTime"))
    reg.set_result(SingletonKey("currentTime"), 42)
    assert req.future.result() == 42


async def test_set_result_idempotent():
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(5))
    reg.set_result(ReqIdKey(5), "ok")
    reg.set_result(ReqIdKey(5), "stomp")  # must not raise, must not re-settle
    assert req.future.result() == "ok"


async def test_set_error_settles_with_exception():
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(6))
    err = ValueError("nope")
    reg.set_error(ReqIdKey(6), err)
    with pytest.raises(ValueError, match="nope"):
        req.future.result()
    assert req.settled is True


async def test_cancel_settles_with_cancellederror():
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(7))
    reg.cancel(ReqIdKey(7))
    with pytest.raises(asyncio.CancelledError):
        req.future.result()


# --- fail_all (disconnect) --------------------------------------------------


async def test_fail_all_wakes_everyone():
    reg = RequestRegistry()
    a = reg.open(ReqIdKey(10))
    b = reg.open(SingletonKey("positions"))
    c = reg.open(CompositeKey("marketRule", (3,)))

    err = ConnectionError("disconnect")
    reg.fail_all(err)

    for req in (a, b, c):
        with pytest.raises(ConnectionError, match="disconnect"):
            req.future.result()
    assert len(reg) == 0


async def test_fail_all_skips_already_done_futures():
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(11))
    req.future.set_result("preset")
    # fail_all must not crash trying to set_exception on a done future
    reg.fail_all(ConnectionError("late"))
    assert req.future.result() == "preset"


# --- iteration / len / contains --------------------------------------------


async def test_contains_treats_settled_as_absent():
    reg = RequestRegistry()
    reg.open(ReqIdKey(20))
    assert ReqIdKey(20) in reg
    reg.set_result(ReqIdKey(20))
    assert ReqIdKey(20) not in reg


async def test_len_and_iter_reflect_live_state():
    reg = RequestRegistry()
    reg.open(ReqIdKey(30))
    reg.open(SingletonKey("x"))
    assert len(reg) == 2
    keys = {r.key for r in reg}
    assert keys == {ReqIdKey(30), SingletonKey("x")}


async def test_a_request_its_awaiter_abandons_is_forgotten():
    """A timeout or a cancelled task ends the request as an answer does:
    it does not stay registered, and late data for it is dropped."""
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(1))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(req.future, 0.001)
    assert len(reg) == 0
    reg.append(ReqIdKey(1), "late")  # no-op: nothing to append to
    assert req.container == []
    # the id can be opened again
    again = reg.open(ReqIdKey(1))
    assert again is not req


async def test_forgetting_leaves_a_newer_request_for_the_same_key():
    reg = RequestRegistry()
    reg.open(ReqIdKey(1))
    reg.set_result(ReqIdKey(1), "done")
    second = reg.open(ReqIdKey(1))
    await asyncio.sleep(0)  # the first future's done callbacks run
    assert reg.get(ReqIdKey(1)) is second


# --- shared requests ---------------------------------------------------------


async def test_one_callers_timeout_leaves_the_others_waiting():
    reg = RequestRegistry()
    key = CompositeKey("marketRule", (26,))
    impatient = reg.share(key).future
    patientShare = reg.share(key)
    assert not patientShare.isNew
    patient = patientShare.future

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(impatient, 0.01)
    req = reg.get(key)
    assert req is not None and req.followers == [patient]

    reg.set_result(key, ["rule"])
    assert await asyncio.wait_for(patient, 1) == ["rule"]


async def test_followers_settle_with_the_request_at_once():
    reg = RequestRegistry()
    a = reg.share(SingletonKey("positions")).future
    b = reg.share(SingletonKey("positions")).future
    reg.set_error(SingletonKey("positions"), ConnectionError("gone"))
    for future in (a, b):
        assert isinstance(future.exception(), ConnectionError)


async def test_the_last_caller_to_leave_ends_the_request():
    reg = RequestRegistry()
    key = SingletonKey("openOrders")
    first = reg.share(key).future
    second = reg.share(key).future
    req = reg.get(key)
    first.cancel()
    await asyncio.sleep(0)
    assert key in reg
    second.cancel()
    await asyncio.sleep(0)
    assert req is not None and req.future.cancelled()
    assert key not in reg and len(reg) == 0


# --- answers owed to ended requests -----------------------------------------


async def test_an_ended_request_is_answering_at_once():
    """Rows that arrive right after a caller gives up, before its entry
    is dropped, are its answer's, not live updates."""
    reg = RequestRegistry()
    key = ReqIdKey(7)
    req = reg.open(key)
    req.future.cancel()
    assert key not in reg and reg.answering(key)
    await asyncio.sleep(0)
    assert reg.answering(key)
    reg.set_result(key)
    assert not reg.answering(key)


async def test_an_answer_owed_to_an_ended_request_comes_before_a_new_ones():
    """A caller gives up mid-answer and asks again: the rest of the first
    answer, and its end, are the ended request's; the second answer is
    the new request's, whole."""
    reg = RequestRegistry()
    key = SingletonKey("openOrders")
    first = reg.share(key).future
    reg.append(key, "first-1")
    first.cancel()
    await asyncio.sleep(0)
    secondShare = reg.share(key)
    assert secondShare.isNew
    second = secondShare.future
    reg.append(key, "first-2")
    reg.set_result(key)  # the first answer's end
    assert not second.done() and reg.answering(key)
    reg.append(key, "second-1")
    reg.append(key, "second-2")
    reg.set_result(key)
    assert second.result() == ["second-1", "second-2"]
    assert not reg.answering(key)


async def test_a_withdrawn_request_is_owed_nothing():
    """A request cancelled with IBKR, or never sent, gets no answer:
    later messages for its key are live updates."""
    reg = RequestRegistry()
    future = reg.share(SingletonKey("openOrders")).future
    reg.cancel(SingletonKey("openOrders"), "not sent")
    await asyncio.sleep(0)
    assert future.cancelled()
    assert not reg.answering(SingletonKey("openOrders"))


async def test_owed_answers_no_longer_waited_for_are_dropped():
    """A reqId is never asked again, so its owed answer is never looked up
    once IBKR stops owing it: the next abandoned request drops every entry
    past its time, and a disconnect drops them all."""
    now = [0.0]
    reg = RequestRegistry(clock=lambda: now[0])
    for reqId in range(3):
        reg.open(ReqIdKey(reqId)).future.cancel()
    await asyncio.sleep(0)
    assert all(reg.answering(ReqIdKey(reqId)) for reqId in range(3))
    now[0] = OWED_FOR + 1
    reg.open(ReqIdKey(3)).future.cancel()
    await asyncio.sleep(0)
    assert list(reg._owed) == [ReqIdKey(3)]
    assert not reg.answering(ReqIdKey(0)) and reg.answering(ReqIdKey(3))
    reg.fail_all(ConnectionError("gone"))
    assert not reg.answering(ReqIdKey(3))


async def test_an_owed_answer_that_never_comes_is_not_waited_for_long():
    """IBKR may never answer a request it refused without saying which:
    after a while the key's messages are live again, and its next
    request gets its own answer."""
    now = [0.0]
    reg = RequestRegistry(clock=lambda: now[0])
    key = SingletonKey("openOrders")
    reg.open(key).future.cancel()
    await asyncio.sleep(0)
    assert reg.answering(key)
    now[0] = 61.0
    assert not reg.answering(key)
    fresh = reg.share(key).future
    reg.append(key, "row")
    reg.set_result(key)
    assert fresh.result() == ["row"]


async def test_a_withdrawn_request_owes_nothing_even_after_its_caller_left():
    reg = RequestRegistry()
    reg.open(ReqIdKey(9)).future.cancel()
    await asyncio.sleep(0)
    assert reg.answering(ReqIdKey(9))
    reg.withdraw(ReqIdKey(9))
    assert not reg.answering(ReqIdKey(9))


async def test_a_moved_request_is_forgotten_under_its_new_key():
    reg = RequestRegistry()
    req = reg.open(ReqIdKey(1))
    assert reg.move(ReqIdKey(1), ReqIdKey(2)) is req
    assert reg.get(ReqIdKey(2)) is req and ReqIdKey(1) not in reg
    req.future.cancel()
    await asyncio.sleep(0)
    assert reg.answering(ReqIdKey(2)) and not reg.answering(ReqIdKey(1))
    assert reg.move(ReqIdKey(3), ReqIdKey(4)) is None


async def test_owed_answers_are_logged(caplog):
    reg = RequestRegistry()
    with caplog.at_level(logging.DEBUG, logger="ib_async.requests"):
        reg.open(ReqIdKey(1)).future.cancel()
        await asyncio.sleep(0)
        reg.set_result(ReqIdKey(1))
    assert "ended before its answer" in caplog.text
    assert "an owed answer ended" in caplog.text
