"""Internal request correlation registry.

Each in-flight request is tracked as a :class:`Request` under a typed
:class:`RequestKey`. The registry holds:

* the :class:`asyncio.Future` the caller awaits;
* the container that response handlers append rows to;
* metadata: the originating contract and, for a request shared by
  concurrent callers, each caller's own future;
* a count of answers still expected for requests whose callers stopped
  waiting, so those messages are not mistaken for live updates.

Key types are distinct so lookups cannot cross namespaces. IBKR uses one
counter for both request IDs and order IDs; typed keys keep the internal
mapping unambiguous.

A request can end in three ways:

* **Answered.** Rows arrive (:meth:`RequestRegistry.append`), then the end
  message (:meth:`~RequestRegistry.set_result`) or an error. This settles
  the future and every follower's future.
* **Withdrawn.** The request is cancelled here because IBKR will not answer
  it: IBKR was told to cancel it, or it was never sent
  (:meth:`~RequestRegistry.cancel`, :meth:`~RequestRegistry.withdraw`).
  Awaiters get CancelledError and no answer is expected.
* **Abandoned.** The caller stops waiting first (a timeout or a cancelled
  task), so the future is done before the answer arrives. IBKR still
  answers, in the order the requests were sent. The registry counts the
  expected answers per key and discards the next rows and end message for
  that key. After that, messages for the key go to a newer request or are
  treated as live updates (:meth:`~RequestRegistry.answering`). An expected
  answer that has not arrived after ``OWED_FOR`` seconds is forgotten.

:mod:`ib_async.ib` opens, shares and cancels requests. :mod:`ib_async.wrapper`
answers them, moves a request that IBKR asks to have resent, and opens one
to refill bars. The per-tick dispatch path does not use this module; it uses
a separate flat ``reqId -> Ticker`` mapping.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from ib_async.runtime import RequestState, Tally
from ib_async.util import getLoop

_logger = logging.getLogger("ib_async.requests")

# Sentinel that lets `set_result` distinguish "use the accumulator"
# from "explicit None result". Module-private; never returned to callers.
_USE_CONTAINER: Any = object()


# --------------------------------------------------------------------------
# Discriminated key types
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RequestKey:
    """Tagged-union base class for request keys.

    Use one of the four concrete subclasses so the registry's namespace
    stays disjoint by type. Two keys are equal iff their concrete type
    and field values match.
    """


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
    ``scannerParams``, ``accountValues``.
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

    When ``settled`` is True the entry has been removed from the registry
    because the request was answered, withdrawn (``withdrawn`` is set) or
    abandoned; see the module docstring. A request whose future is done is
    finished even if its entry has not been removed yet.
    """

    key: RequestKey
    future: asyncio.Future
    container: Any = None
    contract: Any = None
    # Builds the result from the error code and message when IBKR refuses
    # the request, unless refusals raise (IB.RaiseRequestErrors). If None,
    # the result is the container.
    refusal: Callable[[int, str], Any] | None = None
    # Arguments of a shared request that are not visible in its answer.
    # A caller with different arguments cannot share the request.
    args: tuple = ()
    # One future per caller still waiting on a shared request
    # (see RequestRegistry.share).
    followers: list[asyncio.Future] = field(default_factory=list)
    settled: bool = False
    # Set by cancel(): IBKR was already told to cancel, or was never asked.
    withdrawn: bool = False

    @property
    def live(self) -> bool:
        return not self.settled and not self.future.done()

    @property
    def reqId(self) -> int:
        """The current reqId of a request on a :class:`ReqIdKey`.

        A bust event (10225) resends the request under a new reqId and
        moves its key (:meth:`RequestRegistry.move`), so read the reqId
        from the key when cancelling instead of storing it."""
        if not isinstance(self.key, ReqIdKey):
            raise TypeError(f"{self.key!r} is no reqId's")
        return self.key.reqId

    def settle(self, result: Any = None, exc: BaseException | None = None) -> None:
        """Settle the future and all follower futures with ``result``, or
        with ``exc`` if given."""
        self.settled = True
        for future in (self.future, *self.followers):
            if future.done():
                continue
            if exc is None:
                future.set_result(result)
            else:
                future.set_exception(exc)
        if exc is not None and self.followers and not self.future.cancelled():
            # The followers pass the error to their awaiters. Nothing awaits
            # the shared future, so retrieve its exception here.
            self.future.exception()


# Seconds to keep expecting an answer for an abandoned request. IBKR may
# never send it (for example, a refusal that does not name the request).
# Without a limit, the stale expectation would swallow the answer to the
# key's next request.
OWED_FOR = 60.0


@dataclass(frozen=True, slots=True)
class _Owed:
    """Number of answers expected for abandoned requests of one key, and
    the deadline after which they are forgotten."""

    count: int
    until: float


@dataclass(frozen=True, slots=True)
class Shared:
    """A caller's share of a request (see :meth:`RequestRegistry.share`)."""

    future: asyncio.Future  # this caller's future
    isNew: bool  # True if the request is new and this caller must send it


def refusedAsNone(_code: int, _text: str) -> None:
    """``refusal`` for a single-object request: return None when IBKR
    refuses it."""
    return None


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


@dataclass(slots=True, eq=False)
class RequestRegistry:
    """Owns the lifecycle of in-flight :class:`Request` entries.

    Lookups by key are O(1); counting and iterating walk the entries. The
    per-tick dispatch path does not use this object. Methods are
    idempotent where needed, so late or duplicate callbacks are no-ops
    instead of raising KeyError. The module docstring describes how a
    request ends and how answers for abandoned requests are kept apart
    from live updates.
    """

    # Clock used for the OWED_FOR deadlines, in seconds.
    clock: Callable[[], float] = time.monotonic
    # The session's counters (ib_async.runtime), shared with the registry
    # that replaces this one after a disconnect. Each request's end is
    # counted once, where it ends.
    tally: Tally = field(default_factory=Tally)
    _reqs: dict[RequestKey, Request] = field(default_factory=dict, init=False)
    # Per key, the answers still expected for abandoned requests. Ordered
    # by deadline, oldest first: an entry is always (re)inserted with the
    # latest deadline.
    _owed: dict[RequestKey, _Owed] = field(default_factory=dict, init=False)

    # -- queries ---------------------------------------------------------

    def __contains__(self, key: RequestKey) -> bool:
        req = self._reqs.get(key)
        return req is not None and req.live

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def __iter__(self) -> Iterator[Request]:
        """The live requests."""
        return (req for req in list(self._reqs.values()) if req.live)

    def answering(self, key: RequestKey) -> bool:
        """Return True if messages for ``key`` belong to a request.

        That is a live request, or an abandoned one whose answer is still
        expected. Messages that belong to no request are live updates."""
        return key in self._reqs or self._owing(key) > 0

    def _owing(self, key: RequestKey) -> int:
        """Number of answers still expected for ``key``; drops the count
        once its deadline has passed."""
        owed = self._owed.get(key)
        if owed is None:
            return 0
        if self.clock() > owed.until:
            del self._owed[key]
            self.tally.answersForgotten += owed.count
            _logger.debug("%r: no longer waiting for %d owed answers", key, owed.count)
            return 0
        return owed.count

    def find_by_reqid(self, reqId: int) -> Request | None:
        """Return the :class:`Request` whose key is ``ReqIdKey(reqId)`` or
        ``WhatIfKey(reqId)``, or ``None``.

        Used by the error handler, which only has the integer ``reqId``
        and does not know which key type the request was opened with.
        """

        for key in (ReqIdKey(reqId), WhatIfKey(reqId)):
            req = self._reqs.get(key)
            if req is not None and req.live:
                return req
        return None

    def get(self, key: RequestKey) -> Request | None:
        """Return the live :class:`Request` for ``key``, or ``None``.

        A finished request is treated as absent.
        """

        req = self._reqs.get(key)
        if req is None or not req.live:
            return None
        return req

    # -- lifecycle -------------------------------------------------------

    def open(
        self,
        key: RequestKey,
        *,
        container: Any = None,
        contract: Any = None,
        refusal: Callable[[int, str], Any] | None = None,
        args: tuple = (),
    ) -> Request:
        """Open a request for ``key``, awaited on ``request.future``.

        Raises :class:`RuntimeError` if a live request for the key exists,
        instead of silently replacing it. Use :meth:`share` for a request
        shared among callers.

        ``container`` defaults to a fresh empty list. Pass an explicit
        object (string, dataclass instance, list of expected size) for
        callbacks that need a specific accumulator type.
        """

        existing = self._reqs.get(key)
        if existing is not None:
            if existing.live:
                raise RuntimeError(f"request already in flight: {key!r}")
            # Abandoned but not yet removed: its answer is still expected.
            self._abandoned(existing)

        future = getLoop().create_future()
        req = Request(
            key=key,
            future=future,
            container=[] if container is None else container,
            contract=contract,
            refusal=refusal,
            args=args,
        )
        self._reqs[key] = req
        self.tally.requestsOpened += 1
        # If the awaiter finishes the future (a timeout or a cancelled
        # task), remove the request. Otherwise it would stay registered
        # and keep collecting late data.
        future.add_done_callback(lambda _: self._abandoned(req))
        return req

    @contextlib.contextmanager
    def sending(
        self,
        key: RequestKey,
        *,
        container: Any = None,
        contract: Any = None,
        refusal: Callable[[int, str], Any] | None = None,
        args: tuple = (),
    ) -> Iterator[Request]:
        """Open a request for ``key`` (see :meth:`open`) for the block that
        sends it.

        The block holds the wire ``client.req*`` call. If it raises (the
        encoder refused an argument), nothing was sent and no answer
        comes, so the request is cancelled and the exception propagates.
        The caller never gets the future; left open, the request would
        wait until the next disconnect. ``open`` runs before the block, so
        a request already in flight is refused before anything is sent.
        """
        req = self.open(
            key, container=container, contract=contract, refusal=refusal, args=args
        )
        try:
            yield req
        except BaseException:
            self.cancel(key, "not sent", sent=False)
            raise

    def share(self, key: RequestKey, *, args: tuple = ()) -> Shared:
        """Join the request for ``key`` that concurrent callers share.

        Returns this caller's own future and whether the request is new
        (the caller must send it) or already in flight.

        The future settles when the request does. Cancelling it (a timeout
        or a cancelled task) leaves the request running for the other
        callers. When the last caller leaves, the request is cancelled.
        ``args`` are request arguments that are not visible in the answer.
        If they differ from the live request's ``args``, :class:`ValueError`
        is raised, because that answer would not match this request.
        """

        req = self.get(key)
        isNew = req is None
        if req is None:
            req = self.open(key, args=args)
        elif req.args != args:
            raise ValueError(
                f"{key!r} is in flight with {req.args!r}; one with {args!r} "
                "must wait for its answer"
            )
        else:
            self.tally.requestsJoined += 1
        shared = req
        mine: asyncio.Future = shared.future.get_loop().create_future()

        def leave(_: asyncio.Future) -> None:
            if not mine.cancelled():
                return
            shared.followers.remove(mine)
            if not shared.followers:
                shared.future.cancel()

        shared.followers.append(mine)
        mine.add_done_callback(leave)
        return Shared(mine, isNew)

    def move(self, key: RequestKey, newKey: RequestKey) -> Request | None:
        """Move the request for ``key`` to ``newKey`` after it is resent
        under that key. Returns the request, or None if there is none."""
        req = self._reqs.pop(key, None)
        if req is not None:
            req.key = newKey
            self._reqs[newKey] = req
        return req

    def _abandoned(self, req: Request) -> None:
        """Remove ``req`` after its caller stopped waiting, and expect its
        answer for the next ``OWED_FOR`` seconds."""
        key = req.key
        if self._reqs.get(key) is not req:
            return
        del self._reqs[key]
        req.settled = True
        self.tally.requestsAbandoned += 1
        now = self.clock()
        count = self._owing(key) + 1
        # Reinsert at the end with the latest deadline. This keeps entries
        # in deadline order, with expired ones at the front.
        self._owed.pop(key, None)
        self._owed[key] = _Owed(count, now + OWED_FOR)
        _logger.debug("%r: ended before its answer, which is owed", key)
        for expired in [k for k, o in self._owed.items() if o.until < now]:
            self.tally.answersForgotten += self._owed.pop(expired).count
            _logger.debug("%r: no longer waiting for its owed answers", expired)

    def _ended(self, key: RequestKey) -> Request | None:
        """Handle an end message for ``key``.

        Removes and returns the request it ends, or returns None if the
        message belongs to an abandoned request."""
        owed = self._owing(key)
        if owed:
            if owed > 1:
                self._owed[key] = _Owed(owed - 1, self._owed[key].until)
            else:
                del self._owed[key]
            self.tally.answersDiscarded += 1
            _logger.debug("%r: an owed answer ended, settling nothing", key)
            return None
        return self._reqs.pop(key, None)

    def withdraw(self, key: RequestKey) -> None:
        """The request for ``key`` was cancelled with IBKR. Stop expecting
        any answer for it, live or abandoned."""
        self._owed.pop(key, None)
        self.cancel(key, "cancelled")

    def owedReqIdKey(self, reqId: int) -> RequestKey | None:
        """Return ``ReqIdKey(reqId)`` or ``WhatIfKey(reqId)`` if it belongs
        to an abandoned request whose answer is still expected, else None."""
        for key in (ReqIdKey(reqId), WhatIfKey(reqId)):
            if self._owing(key):
                return key
        return None

    def append(self, key: RequestKey, item: Any) -> None:
        """Append ``item`` to the request's container. No-op if the
        request is missing or finished, or the row belongs to an
        abandoned request."""

        req = self._reqs.get(key)
        if self._owing(key) or req is None or not req.live:
            return
        req.container.append(item)

    def extend(self, key: RequestKey, items: Any) -> None:
        """Extend the request's container with ``items``.

        Same as :meth:`append`, for callbacks that deliver several items
        at once (e.g. historical ticks).
        """

        req = self._reqs.get(key)
        if self._owing(key) or req is None or not req.live:
            return
        req.container.extend(items)

    def set_result(self, key: RequestKey, value: Any = _USE_CONTAINER) -> None:
        """Finish the request for ``key`` with ``value``, or with its
        container if no value is given. Idempotent. An end message for an
        abandoned request settles nothing."""

        self._finish(key, value, refused=False)

    def _finish(self, key: RequestKey, value: Any, *, refused: bool) -> None:
        """Settle the request for ``key`` with ``value`` (or its container),
        and count it as answered or refused."""
        req = self._ended(key)
        if req is not None:
            if refused:
                self.tally.requestsRefused += 1
            else:
                self.tally.requestsAnswered += 1
            req.settle(req.container if value is _USE_CONTAINER else value)

    def set_error(self, key: RequestKey, exc: BaseException) -> None:
        """Fail the request for ``key`` with ``exc``. Idempotent."""

        req = self._ended(key)
        if req is not None:
            self.tally.requestsFailed += 1
            req.settle(exc=exc)

    def refuse(self, key: RequestKey, errorCode: int, errorString: str) -> None:
        """Settle a request that IBKR refused, with the result of its
        ``refusal`` callback, or with its container if it has none."""

        req = self._reqs.get(key)
        if req is None or self._owing(key) or req.refusal is None:
            self._finish(key, _USE_CONTAINER, refused=True)
        else:
            self._finish(key, req.refusal(errorCode, errorString), refused=True)

    def cancel(self, key: RequestKey, reason: str = "", *, sent: bool = True) -> None:
        """Cancel a request that IBKR will not answer, because it was
        cancelled with IBKR or, with ``sent=False``, never sent.

        The awaiter and all followers get :class:`asyncio.CancelledError`.
        Answers expected for earlier abandoned requests of the key are
        still expected; :meth:`withdraw` clears those too. Idempotent."""

        req = self._reqs.pop(key, None)
        if req is None:
            return
        req.settled = True
        req.withdrawn = True
        if sent:
            self.tally.requestsWithdrawn += 1
        else:
            self.tally.requestsNotSent += 1
        for future in (req.future, *req.followers):
            future.cancel(reason or repr(key))

    def fail_all(self, exc: BaseException) -> None:
        """Settle every live request with ``exc``.

        Used on disconnect so no awaiter hangs on a future that will never
        resolve. Afterwards the registry is empty and no answers are
        expected.

        The client reports the disconnect itself (``apiEnd``,
        ``IB.disconnectedEvent``). A caller that dropped its future before
        the disconnect gets no second report: each failure set here is
        marked as read, so the loop does not report "Future exception was
        never retrieved". An awaiter still gets ``exc`` raised.
        """

        for req in list(self._reqs.values()):
            # A request whose caller already stopped waiting (its removal
            # still pending on the loop) ended as abandoned.
            if req.future.done():
                self.tally.requestsAbandoned += 1
            else:
                self.tally.requestsDisconnected += 1
            failing = [f for f in (req.future, *req.followers) if not f.done()]
            req.settle(exc=exc)
            for future in failing:
                future.exception()
        self._reqs.clear()
        self._owed.clear()

    def state(self) -> RequestState:
        """The requests waiting for an answer, by kind of key. Reading it
        changes nothing: expired owed answers are left out, not dropped."""
        reqIds = singletons = composites = whatIfs = callers = 0
        for req in self._reqs.values():
            if not req.live:
                continue
            key = req.key
            if isinstance(key, ReqIdKey):
                reqIds += 1
            elif isinstance(key, SingletonKey):
                singletons += 1
            elif isinstance(key, CompositeKey):
                composites += 1
            elif isinstance(key, WhatIfKey):
                whatIfs += 1
            callers += len(req.followers)
        now = self.clock()
        owed = 0
        for entry in self._owed.values():
            if entry.until >= now:
                owed += entry.count
        return RequestState(
            reqIdRequests=reqIds,
            singletonRequests=singletons,
            compositeRequests=composites,
            whatIfRequests=whatIfs,
            waitingCallers=callers,
            owedAnswers=owed,
        )
