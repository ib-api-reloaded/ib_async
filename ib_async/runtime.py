"""The client's runtime state, for metrics and debugging.

:meth:`IB.runtimeState` returns a :class:`RuntimeState`: the connection,
the transport, the requests waiting for an answer, the live subscriptions,
and :class:`Counters` totalled since the IB was created. Every record is
frozen. The state is read in one step on the event loop's thread, so its
parts agree with each other.

The counters only grow; a disconnect does not reset them. Each is counted
where the event happens, once per frame, request or subscription, never
per market data tick. Every request ends one way, so
``requestsOpened == requestsEnded + (requests still open)``, where
``requestsEnded`` sums the seven ways, and
``subscriptionsAdded == subscriptionsEnded + (live subscriptions)``.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Literal

ConnectionPhase = Literal["disconnected", "connecting", "connected"]


@dataclass(slots=True)
class Tally:
    """The counters as the client updates them. Internal: read a frozen
    copy through :meth:`counters` (or :meth:`IB.runtimeState`). The fields
    are those of :class:`Counters`, which describes them."""

    connectAttempts: int = 0
    connects: int = 0
    connectFailures: int = 0
    disconnects: int = 0
    framesSent: int = 0
    bytesSent: int = 0
    framesReceived: int = 0
    bytesReceived: int = 0
    throttleStarts: int = 0
    mostQueued: int = 0
    decodeFailures: int = 0
    unknownMessages: int = 0
    requestsOpened: int = 0
    requestsJoined: int = 0
    requestsAnswered: int = 0
    requestsRefused: int = 0
    requestsFailed: int = 0
    requestsAbandoned: int = 0
    requestsWithdrawn: int = 0
    requestsNotSent: int = 0
    requestsDisconnected: int = 0
    requestsTimedOut: int = 0
    answersDiscarded: int = 0
    answersForgotten: int = 0
    subscriptionsAdded: int = 0
    subscriptionsEnded: int = 0
    subscriptionsNotSent: int = 0
    subscriptionsRefused: int = 0
    subscriptionsDisconnected: int = 0
    errors: dict[int, int] = field(default_factory=dict)
    warnings: dict[int, int] = field(default_factory=dict)

    def counted(self, code: int, warning: bool) -> None:
        """Count one error or warning message with ``code``."""
        counts = self.warnings if warning else self.errors
        counts[code] = counts.get(code, 0) + 1

    def counters(self) -> Counters:
        """A frozen copy."""
        return Counters(
            **{name: getattr(self, name) for name in _COUNTS},
            errors=_codeCounts(self.errors),
            warnings=_codeCounts(self.warnings),
        )


# The Tally fields that are plain counts, copied as they are.
_COUNTS = tuple(
    f.name for f in dataclasses.fields(Tally) if f.name not in ("errors", "warnings")
)


def _codeCounts(counts: dict[int, int]) -> tuple[CodeCount, ...]:
    return tuple(CodeCount(code, counts[code]) for code in sorted(counts))


@dataclass(frozen=True, slots=True)
class CodeCount:
    """How many messages with an IBKR error or warning code arrived."""

    code: int
    count: int


@dataclass(frozen=True, slots=True)
class Counters:
    """Totals since the IB was created. A disconnect does not reset them."""

    #: Calls to connect.
    connectAttempts: int
    #: Connections whose API started.
    connects: int
    #: Calls to connect that raised.
    connectFailures: int
    #: API sessions that ended, by either side.
    disconnects: int
    framesSent: int
    bytesSent: int
    framesReceived: int
    bytesReceived: int
    #: Times requests were held back to stay within MaxRequests.
    throttleStarts: int
    #: The most frames held back at once.
    mostQueued: int
    #: Messages whose decoding or handling raised.
    decodeFailures: int
    #: Messages of a type the client does not handle.
    unknownMessages: int
    requestsOpened: int
    #: Callers that joined a shared request already in flight.
    requestsJoined: int
    # How requests ended. Each request is counted once, in one of these.
    #: Requests answered.
    requestsAnswered: int
    #: Requests IBKR refused with an error.
    requestsRefused: int
    #: Requests that raised: a refusal with RaiseRequestErrors, or an
    #: answer that could not be decoded.
    requestsFailed: int
    #: Requests whose caller stopped waiting: a timeout or a cancel.
    requestsAbandoned: int
    #: Requests cancelled with IBKR.
    requestsWithdrawn: int
    #: Requests whose send raised, so IBKR never got them.
    requestsNotSent: int
    #: Requests a disconnect ended.
    requestsDisconnected: int
    #: Requests whose time limit passed (IB.requestTimeoutEvent). Not a
    #: way to end: each also ended as abandoned or withdrawn.
    requestsTimedOut: int
    #: Answers that arrived for abandoned requests.
    answersDiscarded: int
    #: Answers expected for abandoned requests that never came.
    answersForgotten: int
    subscriptionsAdded: int
    #: Subscriptions that ended for any reason, including the three below.
    subscriptionsEnded: int
    #: Subscriptions whose send raised.
    subscriptionsNotSent: int
    #: Subscriptions IBKR ended with an error.
    subscriptionsRefused: int
    #: Subscriptions a disconnect ended.
    subscriptionsDisconnected: int
    #: Error messages by code.
    errors: tuple[CodeCount, ...]
    #: Warning and notice messages by code.
    warnings: tuple[CodeCount, ...]

    @property
    def requestsEnded(self) -> int:
        """Requests that ended, each counted once by how it ended."""
        return (
            self.requestsAnswered
            + self.requestsRefused
            + self.requestsFailed
            + self.requestsAbandoned
            + self.requestsWithdrawn
            + self.requestsNotSent
            + self.requestsDisconnected
        )


@dataclass(frozen=True, slots=True)
class ConnectionState:
    phase: ConnectionPhase
    #: True once the API started: requests can be made.
    apiReady: bool
    host: str
    port: int
    clientId: int
    #: The version the server negotiated; None before the handshake.
    serverVersion: int | None
    accounts: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TransportState:
    """The current connection's traffic and request pacing."""

    framesSent: int
    bytesSent: int
    framesReceived: int
    bytesReceived: int
    #: True while requests are held back to stay within MaxRequests.
    throttling: bool
    queuedFrames: int
    maxRequests: int
    requestsInterval: float


@dataclass(frozen=True, slots=True)
class RequestState:
    """Requests waiting for an answer, by kind of key."""

    reqIdRequests: int
    singletonRequests: int
    compositeRequests: int
    whatIfRequests: int
    #: Callers waiting on shared requests.
    waitingCallers: int
    #: Answers still expected for requests whose callers stopped waiting.
    owedAnswers: int


@dataclass(frozen=True, slots=True)
class SubscriptionState:
    """Live subscriptions, by kind."""

    marketData: int
    snapshots: int
    tickByTick: int
    marketDepth: int
    realTimeBars: int
    #: Historical bars kept up to date.
    historicalBars: int
    scanners: int
    pnl: int
    pnlSingle: int
    #: Tickers in the per-contract pool (IB.tickers()).
    pooledTickers: int


@dataclass(frozen=True, slots=True)
class RuntimeState:
    #: When the state was read (UTC).
    time: dt.datetime
    connection: ConnectionState
    transport: TransportState
    requests: RequestState
    subscriptions: SubscriptionState
    counters: Counters
