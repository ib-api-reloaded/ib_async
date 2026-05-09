"""Unit tests for ib_async._requests.RequestRegistry.

The registry is the source of truth for in-flight request correlation.
These tests exercise it in isolation: no Wrapper, no IB client, no
network. They cover the documented invariants:

  * discriminated keys do not collide
  * single_flight dedupes; non-single_flight raises on duplicate
  * append/set_result/set_error/cancel are idempotent
  * fail_all wakes every awaiter and empties the registry
"""

import asyncio

import pytest

from ib_async._requests import (
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
    req, isNew = reg.open(ReqIdKey(1))
    assert isNew is True
    assert isinstance(req, Request)
    assert isinstance(req.future, asyncio.Future)
    assert req.container == []
    assert req.refcount == 1
    assert ReqIdKey(1) in reg


async def test_open_duplicate_without_single_flight_raises():
    reg = RequestRegistry()
    reg.open(ReqIdKey(2))
    with pytest.raises(RuntimeError):
        reg.open(ReqIdKey(2))


async def test_open_duplicate_with_single_flight_attaches():
    reg = RequestRegistry()
    first, isNew1 = reg.open(SingletonKey("openOrders"), single_flight=True)
    second, isNew2 = reg.open(SingletonKey("openOrders"), single_flight=True)
    assert isNew1 is True
    assert isNew2 is False
    assert first is second
    assert first.refcount == 2


async def test_open_after_settle_creates_fresh_request():
    reg = RequestRegistry()
    first, _ = reg.open(SingletonKey("positions"))
    reg.set_result(SingletonKey("positions"), [])
    second, isNew = reg.open(SingletonKey("positions"))
    assert isNew is True
    assert second is not first


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
    req, _ = reg.open(ReqIdKey(4))
    reg.append(ReqIdKey(4), 1)
    reg.append(ReqIdKey(4), 2)
    reg.set_result(ReqIdKey(4))
    assert req.future.result() == [1, 2]
    assert req.settled is True
    assert ReqIdKey(4) not in reg


async def test_set_result_with_explicit_value():
    reg = RequestRegistry()
    req, _ = reg.open(SingletonKey("currentTime"))
    reg.set_result(SingletonKey("currentTime"), 42)
    assert req.future.result() == 42


async def test_set_result_idempotent():
    reg = RequestRegistry()
    req, _ = reg.open(ReqIdKey(5))
    reg.set_result(ReqIdKey(5), "ok")
    reg.set_result(ReqIdKey(5), "stomp")  # must not raise, must not re-settle
    assert req.future.result() == "ok"


async def test_set_error_settles_with_exception():
    reg = RequestRegistry()
    req, _ = reg.open(ReqIdKey(6))
    err = ValueError("nope")
    reg.set_error(ReqIdKey(6), err)
    with pytest.raises(ValueError, match="nope"):
        req.future.result()
    assert req.settled is True


async def test_cancel_settles_with_cancellederror():
    reg = RequestRegistry()
    req, _ = reg.open(ReqIdKey(7))
    reg.cancel(ReqIdKey(7))
    with pytest.raises(asyncio.CancelledError):
        req.future.result()


# --- fail_all (disconnect) --------------------------------------------------


async def test_fail_all_wakes_everyone():
    reg = RequestRegistry()
    a, _ = reg.open(ReqIdKey(10))
    b, _ = reg.open(SingletonKey("positions"))
    c, _ = reg.open(CompositeKey("marketRule", (3,)))

    err = ConnectionError("disconnect")
    reg.fail_all(err)

    for req in (a, b, c):
        with pytest.raises(ConnectionError, match="disconnect"):
            req.future.result()
    assert len(reg) == 0


async def test_fail_all_skips_already_done_futures():
    reg = RequestRegistry()
    req, _ = reg.open(ReqIdKey(11))
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
