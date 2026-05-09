"""Internal request correlation registry.

Each in-flight request from the IB API client side is tracked here as a
:class:`Request` keyed by a typed :class:`RequestKey`. The registry is
the single source of truth for:

* the awaitable :class:`asyncio.Future` the caller is blocked on,
* the streaming-accumulation container that response handlers append to,
* metadata: started time (monotonic), originating contract, refcount for
  single-flight deduplication.

Discriminated key types prevent accidental cross-namespace lookups.
The IBKR wire protocol shares one monotonic counter for request IDs and
order IDs; tagging keys keeps the internal mapping unambiguous even
while the wire space stays unified.

Designed to be used only by :mod:`ib_async.wrapper`. The hot per-tick
dispatch path does NOT go through this module — it touches a flat
``reqId -> Ticker`` view maintained separately for the per-packet inner
loop.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from ib_async.util import getLoop

# Sentinel that lets `set_result` distinguish "use the accumulator"
# from "explicit None result". Module-private; never returned to callers.
_USE_CONTAINER: Any = object()


# --------------------------------------------------------------------------
# Discriminated key types
# --------------------------------------------------------------------------


class RequestKey:
    """Tagged-union base class for request keys.

    Use one of the four concrete subclasses so the registry's namespace
    stays disjoint by type. Two keys are equal iff their concrete type
    and field values match.
    """

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class ReqIdKey(RequestKey):
    """Wraps an IBKR-allocated sequential request ID.

    Used for one-shot data requests whose reqId is assigned client-side
    via ``Client.getReqId()`` and echoed back on every response and the
    end-of-stream callback (e.g. ``reqContractDetails``,
    ``reqHistoricalData``, ``reqExecutions``).
    """

    reqId: int


@dataclass(frozen=True, slots=True)
class SingletonKey(RequestKey):
    """A globally-named request whose response stream has no reqId on the
    wire.

    Examples: ``openOrders``, ``completedOrders``, ``positions``,
    ``currentTime``, ``mktDepthExchanges``, ``newsProviders``,
    ``scannerParams``, ``requestFA``, ``accountValues``.
    """

    name: str


@dataclass(frozen=True, slots=True)
class CompositeKey(RequestKey):
    """Parameterised singleton: a name plus a tuple of arguments.

    Example: ``CompositeKey("marketRule", (marketRuleId,))`` keeps
    distinct in-flight requests for distinct rule IDs without colliding
    in the global namespace.
    """

    name: str
    args: tuple = ()


@dataclass(frozen=True, slots=True)
class WhatIfKey(RequestKey):
    """Wraps the orderId of a ``placeOrder(whatIf=True)`` request.

    Distinct from :class:`ReqIdKey` so a stray contract-details error
    using the same numeric id cannot collide with a margin-impact
    future.
    """

    orderId: int


# --------------------------------------------------------------------------
# Request record
# --------------------------------------------------------------------------


@dataclass(slots=True)
class Request:
    """One in-flight request and its accumulated state.

    Once ``settled`` is True the entry has been removed from the registry
    and the future has either been fulfilled or rejected; further
    callbacks for this key are safe no-ops.
    """

    key: RequestKey
    future: asyncio.Future
    container: Any = None
    contract: Any = None
    started_monotonic: float = field(default_factory=time.monotonic)
    refcount: int = 1
    settled: bool = False


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


class RequestRegistry:
    """Owns the lifecycle of in-flight :class:`Request` entries.

    All operations are O(1); the hot per-tick dispatch path does not
    touch this object. Methods are idempotent where it matters: late or
    duplicate callbacks become no-ops rather than KeyErrors.
    """

    __slots__ = ("_reqs",)

    def __init__(self) -> None:
        self._reqs: dict[RequestKey, Request] = {}

    # -- queries ---------------------------------------------------------

    def __contains__(self, key: RequestKey) -> bool:
        req = self._reqs.get(key)
        return req is not None and not req.settled

    def __len__(self) -> int:
        return len(self._reqs)

    def __iter__(self) -> Iterator[Request]:
        return iter(self._reqs.values())

    def find_by_reqid(self, reqId: int) -> Request | None:
        """Return the :class:`Request` whose key is ``ReqIdKey(reqId)`` or
        ``WhatIfKey(reqId)``, or ``None``.

        Used by the wire-level error handler, which sees only the raw
        integer ``reqId`` and must resolve to the right request without
        knowing which key flavour was used at open time.
        """

        for key in (ReqIdKey(reqId), WhatIfKey(reqId)):
            req = self._reqs.get(key)
            if req is not None and not req.settled:
                return req
        return None

    def get(self, key: RequestKey) -> Request | None:
        """Return the live :class:`Request` for ``key``, or ``None``.

        A settled request is treated as absent.
        """

        req = self._reqs.get(key)
        if req is None or req.settled:
            return None
        return req

    # -- lifecycle -------------------------------------------------------

    def open(
        self,
        key: RequestKey,
        *,
        future: asyncio.Future | None = None,
        container: Any = None,
        contract: Any = None,
        single_flight: bool = False,
    ) -> tuple[Request, bool]:
        """Open or attach to a request.

        Returns ``(request, isNew)``.

        With ``single_flight=True``: if a live request for ``key``
        already exists, return it with ``isNew=False`` so the caller
        skips re-issuing the underlying API request and attaches to the
        in-flight result. The existing request's ``refcount`` is
        incremented.

        Without ``single_flight`` an attempt to re-open a live key
        raises :class:`RuntimeError` — loud failure beats silent
        overwrite.

        ``future`` may be passed in to re-use an externally-created
        Future (used by the legacy :meth:`Wrapper.startReq` facade).
        Otherwise a fresh future is created on the active loop.

        ``container`` defaults to a fresh empty list. Pass an explicit
        object (string, dataclass instance, list of expected size) for
        callbacks that need a specific accumulator type.
        """

        existing = self._reqs.get(key)
        if existing is not None and not existing.settled:
            if single_flight:
                existing.refcount += 1
                return existing, False
            raise RuntimeError(f"request already in flight: {key!r}")

        if future is None:
            future = getLoop().create_future()
        if container is None:
            container = []

        req = Request(
            key=key,
            future=future,
            container=container,
            contract=contract,
        )
        self._reqs[key] = req
        return req, True

    def append(self, key: RequestKey, item: Any) -> None:
        """Append ``item`` to the request's accumulator.

        No-op if the request is missing or already settled. Replaces
        legacy ``_results[key].append(...)`` call sites that could
        ``KeyError`` on a late-callback race.
        """

        req = self._reqs.get(key)
        if req is None or req.settled:
            return
        req.container.append(item)

    def extend(self, key: RequestKey, items: Any) -> None:
        """Extend the request's accumulator with ``items``.

        Same semantics as :meth:`append` but for batch inserts where the
        callback delivers a chunk of items at once (e.g. historical
        tick streams).
        """

        req = self._reqs.get(key)
        if req is None or req.settled:
            return
        req.container.extend(items)

    def set_result(self, key: RequestKey, value: Any = _USE_CONTAINER) -> None:
        """Settle the request's future with ``value``.

        If no value is given, settles with the accumulator. Idempotent;
        a second call for the same key is a no-op.
        """

        req = self._reqs.pop(key, None)
        if req is None:
            return
        req.settled = True
        if req.future.done():
            return
        result = req.container if value is _USE_CONTAINER else value
        req.future.set_result(result)

    def set_error(self, key: RequestKey, exc: BaseException) -> None:
        """Settle the request's future with an exception. Idempotent."""

        req = self._reqs.pop(key, None)
        if req is None:
            return
        req.settled = True
        if req.future.done():
            return
        req.future.set_exception(exc)

    def cancel(self, key: RequestKey, reason: str = "") -> None:
        """Settle with :class:`asyncio.CancelledError`. Idempotent."""

        self.set_error(key, asyncio.CancelledError(reason or repr(key)))

    def fail_all(self, exc: BaseException) -> None:
        """Settle every live request with ``exc``.

        Used on disconnect so every awaiter is woken instead of
        silently hanging on a future that will never be resolved.
        After this returns the registry is empty.
        """

        for req in list(self._reqs.values()):
            req.settled = True
            if not req.future.done():
                req.future.set_exception(exc)
        self._reqs.clear()

    def clear(self) -> None:
        """Drop all entries without settling.

        Used by :meth:`Wrapper.reset` after :meth:`fail_all` has already
        run, and by tests. Does not touch futures.
        """

        self._reqs.clear()
