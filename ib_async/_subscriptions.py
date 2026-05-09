"""Internal subscription registry.

A :class:`Subscription` is a long-lived live data flow from IB whose
lifecycle is independent of any single one-shot request: market data,
tick-by-tick, market depth, real-time bars, historical bars with
``keepUpToDate``, scanner subscriptions, and PnL streams.

Each concrete type is self-managing — it knows its own ``reqId``,
contract, accumulator object, and how to send its cancel — and the
:class:`SubscriptionRegistry` owns the per-shape indexes used for
hot-path tick dispatch and idempotent close.

Designed to be used only by :mod:`ib_async.wrapper`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, ClassVar, TypeVar

if TYPE_CHECKING:
    from ib_async.client import Client
    from ib_async.contract import Contract
    from ib_async.objects import (
        BarDataList,
        PnL,
        PnLSingle,
        RealTimeBarList,
        ScanDataList,
    )
    from ib_async.ticker import Ticker
    from ib_async.wrapper import Wrapper


_S = TypeVar("_S", bound="Subscription")


# --------------------------------------------------------------------------
# Subscription base + concrete types
# --------------------------------------------------------------------------


@dataclass
class Subscription:
    """Lifecycle-aware base class for live IB data flows.

    Subclasses fill in ``KIND`` (used by the registry to index by
    ``(conId, kind)`` for market-data-style subscriptions), ``ticker``
    or another accumulator field, and the two protocol hooks
    ``_send_cancel`` and ``_set_done``.

    A subscription is registered with a :class:`SubscriptionRegistry`
    via :meth:`SubscriptionRegistry.add`, which stamps ``_registry`` on
    the instance so :meth:`close` can find its way home. After
    :meth:`close` returns, the subscription is detached: its registry
    reference is cleared and the registry no longer indexes it.
    """

    # The (string) market-data kind used to index market-data-style
    # subscriptions (``"mktData"``, ``"Last"``, ``"AllLast"``,
    # ``"BidAsk"``, ``"MidPoint"``, ``"mktDepth"``). ``None`` means the
    # subscription is not market-data-shaped and is not stored in the
    # ``by_market_data_key`` index. Subclasses override.
    KIND: ClassVar[str | None] = None

    reqId: int
    contract: Contract
    closed: bool = False

    # Set by :meth:`SubscriptionRegistry.add`. Cleared on close. Not part
    # of the public API.
    _registry: SubscriptionRegistry | None = field(default=None, repr=False)

    # ---- public API ------------------------------------------------------

    def close(self, *, send_cancel: bool = True) -> None:
        """Idempotent. Tear down the subscription.

        With ``send_cancel=True`` (default) the subclass-defined
        :meth:`_send_cancel` is invoked so the IB client sends the
        appropriate ``cancel*`` message. The disconnect path uses
        ``send_cancel=False`` because the socket is already gone.

        Always: removes the subscription from every registry index, sets
        ``closed=True``, fires :meth:`_set_done` so any per-subscriber
        ``updateEvent`` wakes its awaiters, and clears the registry
        back-reference.
        """

        if self.closed:
            return
        self.closed = True
        registry = self._registry
        try:
            if send_cancel and registry is not None and registry._wrapper is not None:
                client = registry._wrapper.ib.client
                if client is not None:
                    self._send_cancel(client)
        finally:
            if registry is not None:
                registry._unregister(self)
            self._set_done()
            self._registry = None

    # ---- subclass protocol ----------------------------------------------

    def _send_cancel(self, client: Client) -> None:
        """Send the type-specific cancel message. Override per subclass."""

    def _set_done(self) -> None:
        """Mark any per-subscriber ``updateEvent`` as done so awaiters
        woken by :meth:`close` do not block forever past disconnect.

        Default: no-op. Subclasses that own a unique subscriber object
        (bars list, scanner data list) override.
        """


# ---- market-data family -----------------------------------------------------


@dataclass
class MktDataSub(Subscription):
    """``IB.reqMktData`` — streaming top-of-book + generic ticks.

    The :class:`Ticker` is pooled per-contract across mktData /
    tickByTick / mktDepth and is therefore *not* set-done on close;
    other subscriptions on the same contract may still be active.
    """

    KIND: ClassVar[str | None] = "mktData"

    ticker: Ticker = None  # type: ignore[assignment]
    snapshot: bool = False
    genericTickList: str = ""

    def _send_cancel(self, client: Client) -> None:
        # Snapshots auto-complete on the IB side; cancelling them is a
        # protocol error.
        if not self.snapshot:
            client.cancelMktData(self.reqId)


@dataclass
class TickByTickSub(Subscription):
    """``IB.reqTickByTickData`` — per-trade or per-quote stream.

    The four IB tick types (``"Last"``, ``"AllLast"``, ``"BidAsk"``,
    ``"MidPoint"``) share this single class. The market-data index in
    :class:`SubscriptionRegistry` reads :attr:`tickType` directly rather
    than the class-level ``KIND`` (which stays ``None``), so each
    instance can have its own kind without mutating shared state.
    """

    ticker: Ticker = None  # type: ignore[assignment]
    tickType: str = ""

    def _send_cancel(self, client: Client) -> None:
        client.cancelTickByTickData(self.reqId)


@dataclass
class MktDepthSub(Subscription):
    """``IB.reqMktDepth`` — DOM (level-2) book updates."""

    KIND: ClassVar[str | None] = "mktDepth"

    ticker: Ticker = None  # type: ignore[assignment]
    isSmartDepth: bool = False

    def _send_cancel(self, client: Client) -> None:
        client.cancelMktDepth(self.reqId, self.isSmartDepth)


# ---- bar / scanner family ---------------------------------------------------


@dataclass
class RealTimeBarsSub(Subscription):
    """``IB.reqRealTimeBars``."""

    bars: RealTimeBarList = None  # type: ignore[assignment]

    def _send_cancel(self, client: Client) -> None:
        client.cancelRealTimeBars(self.reqId)

    def _set_done(self) -> None:
        if self.bars is not None:
            self.bars.updateEvent.set_done()


@dataclass
class HistoricalBarsSub(Subscription):
    """``IB.reqHistoricalData(keepUpToDate=True)`` live extension."""

    bars: BarDataList = None  # type: ignore[assignment]

    def _send_cancel(self, client: Client) -> None:
        client.cancelHistoricalData(self.reqId)

    def _set_done(self) -> None:
        if self.bars is not None:
            self.bars.updateEvent.set_done()


@dataclass
class ScannerSub(Subscription):
    """``IB.reqScannerSubscription``."""

    dataList: ScanDataList = None  # type: ignore[assignment]

    def _send_cancel(self, client: Client) -> None:
        client.cancelScannerSubscription(self.reqId)

    def _set_done(self) -> None:
        if self.dataList is not None:
            self.dataList.updateEvent.set_done()


# ---- PnL family -------------------------------------------------------------


@dataclass
class PnLSub(Subscription):
    """``IB.reqPnL``."""

    pnl: PnL = None  # type: ignore[assignment]
    account: str = ""
    modelCode: str = ""

    def _send_cancel(self, client: Client) -> None:
        client.cancelPnL(self.reqId)


@dataclass
class PnLSingleSub(Subscription):
    """``IB.reqPnLSingle``."""

    pnlSingle: PnLSingle = None  # type: ignore[assignment]
    account: str = ""
    modelCode: str = ""
    conId: int = 0

    def _send_cancel(self, client: Client) -> None:
        client.cancelPnLSingle(self.reqId)


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


class SubscriptionRegistry:
    """Owns lifecycle and lookup for every live :class:`Subscription`.

    The registry is the single source of truth: every index it holds is
    maintained atomically on :meth:`add` and :meth:`_unregister`. The
    per-tick hot path uses :meth:`get_ticker` (one ``dict.get`` over the
    flat ``reqId -> Ticker`` view); subscription metadata lookups use
    :meth:`get_sub` and :meth:`find_market_data`.

    The registry holds a back-reference to the owning :class:`Wrapper`
    so a :meth:`Subscription.close` call can find the IB client to send
    its cancel. The reference is set at construction time.
    """

    __slots__ = (
        "_wrapper",
        "_by_reqid",
        "_ticker_by_reqid",
        "_tickers",
        "_by_market_data_key",
        "_by_pnl_key",
        "_by_pnl_single_key",
    )

    def __init__(self, wrapper: Wrapper | None = None) -> None:
        self._wrapper: Wrapper | None = wrapper
        self._by_reqid: dict[int, Subscription] = {}
        # Hot-path view; equal value identity to ``MktDataSub.ticker`` /
        # ``TickByTickSub.ticker`` / ``MktDepthSub.ticker`` for the same
        # reqId. Tick handlers do one dict.get on this map.
        self._ticker_by_reqid: dict[int, Ticker] = {}
        # Per-contract Ticker pool. The same Ticker is shared across all
        # market-data shapes (mktData / tickByTick / mktDepth / snapshot)
        # for a given contract so a single Ticker reflects every live
        # tick stream. Keyed by ``hash(contract)`` (which uses conId).
        self._tickers: dict[int, Ticker] = {}
        # (conId, kind) -> Subscription, where kind is the IB-level
        # market-data type ("mktData", "Last", "AllLast", "BidAsk",
        # "MidPoint", "mktDepth").
        self._by_market_data_key: dict[tuple[int, str], Subscription] = {}
        # (account, modelCode) -> PnLSub.
        self._by_pnl_key: dict[tuple[str, str], PnLSub] = {}
        # (account, modelCode, conId) -> PnLSingleSub.
        self._by_pnl_single_key: dict[tuple[str, str, int], PnLSingleSub] = {}

    # ---- registration ---------------------------------------------------

    def add(self, sub: Subscription) -> None:
        """Register ``sub`` and stamp the registry back-reference.

        Raises :class:`KeyError` if the reqId is already in use, or if a
        market-data subscription already exists for the
        ``(conId, kind)`` pair (caller should idempotently dedupe via
        :meth:`find_market_data` first).
        """

        if sub.reqId in self._by_reqid:
            raise KeyError(f"reqId {sub.reqId} already registered")

        kind = self._market_data_kind(sub)
        if kind is not None:
            mkey = (sub.contract.conId, kind)
            if mkey in self._by_market_data_key:
                raise KeyError(
                    f"market-data subscription for {mkey!r} already registered"
                )
            self._by_market_data_key[mkey] = sub

        if isinstance(sub, PnLSub):
            self._by_pnl_key[(sub.account, sub.modelCode)] = sub
        elif isinstance(sub, PnLSingleSub):
            self._by_pnl_single_key[(sub.account, sub.modelCode, sub.conId)] = sub

        self._by_reqid[sub.reqId] = sub
        ticker = getattr(sub, "ticker", None)
        if ticker is not None:
            self._ticker_by_reqid[sub.reqId] = ticker

        sub._registry = self

    def _unregister(self, sub: Subscription) -> None:
        """Remove ``sub`` from every index. Called from :meth:`Subscription.close`."""

        self._by_reqid.pop(sub.reqId, None)
        self._ticker_by_reqid.pop(sub.reqId, None)

        kind = self._market_data_kind(sub)
        if kind is not None:
            self._by_market_data_key.pop((sub.contract.conId, kind), None)

        if isinstance(sub, PnLSub):
            self._by_pnl_key.pop((sub.account, sub.modelCode), None)
        elif isinstance(sub, PnLSingleSub):
            self._by_pnl_single_key.pop((sub.account, sub.modelCode, sub.conId), None)

    # ---- queries --------------------------------------------------------

    def get_sub(self, reqId: int) -> Subscription | None:
        """Return the :class:`Subscription` registered for ``reqId``, or ``None``."""

        return self._by_reqid.get(reqId)

    def get_ticker(self, reqId: int) -> Ticker | None:
        """Hot-path lookup: one ``dict.get`` to find the ticker for a tick reqId."""

        return self._ticker_by_reqid.get(reqId)

    # ---- ticker pool ----------------------------------------------------

    def get_or_create_ticker(self, contract: Contract) -> Ticker:
        """Return the pooled :class:`Ticker` for ``contract``, allocating
        one with the wrapper's :class:`IBDefaults` if no entry exists yet.
        """

        # Local import keeps the module's public surface free of a
        # cycle: Ticker imports IBDefaults from objects.py, which is fine.
        from ib_async.ticker import Ticker as _Ticker

        key = hash(contract)
        ticker = self._tickers.get(key)
        if ticker is None:
            assert self._wrapper is not None, "registry must be wrapper-bound"
            ticker = _Ticker(contract=contract, defaults=self._wrapper.defaults)
            self._tickers[key] = ticker
        return ticker

    def ticker_for_contract(self, contract: Contract) -> Ticker | None:
        """Return the pooled Ticker for ``contract`` if one exists. Used
        by :meth:`IB.ticker` as the public lookup."""

        return self._tickers.get(hash(contract))

    def pooled_tickers(self) -> list[Ticker]:
        """Snapshot of every pooled Ticker. Used by :meth:`IB.tickers`
        and by :meth:`Wrapper.connectionClosed` to set done on every
        Ticker's ``updateEvent``."""

        return list(self._tickers.values())

    def find_market_data(self, conId: int, kind: str) -> Subscription | None:
        """Return any in-flight market-data subscription for ``(conId, kind)``.

        Used by ``IB.reqMktData`` / ``IB.reqTickByTickData`` /
        ``IB.reqMktDepth`` for idempotent re-subscribe (the second call
        returns the existing subscription instead of double-billing).
        """

        return self._by_market_data_key.get((conId, kind))

    def get_pnl(self, account: str, modelCode: str) -> PnLSub | None:
        return self._by_pnl_key.get((account, modelCode))

    def get_pnl_single(
        self, account: str, modelCode: str, conId: int
    ) -> PnLSingleSub | None:
        return self._by_pnl_single_key.get((account, modelCode, conId))

    def subs_of_type(self, sub_class: type[_S]) -> Iterator[_S]:
        """Iterate every live subscription that is an instance of ``sub_class``.

        Used by the public IB accessors that historically read parallel
        legacy maps (``IB.pnl()``, ``IB.pnlSingle()``,
        ``IB.realtimeBars()``). One indexed lookup per Subscription
        type is fine here — these accessors are not on the per-tick
        hot path.
        """

        for sub in self._by_reqid.values():
            if isinstance(sub, sub_class):
                yield sub

    def __contains__(self, reqId: int) -> bool:
        return reqId in self._by_reqid

    def __len__(self) -> int:
        return len(self._by_reqid)

    def __iter__(self) -> Iterator[Subscription]:
        return iter(self._by_reqid.values())

    # ---- bulk lifecycle -------------------------------------------------

    def close_all(self, *, send_cancel: bool = False) -> None:
        """Close every live subscription.

        Disconnect path uses ``send_cancel=False`` because the socket is
        already gone; manual teardown could pass ``True``. After this
        returns the registry is empty.
        """

        for sub in list(self._by_reqid.values()):
            sub.close(send_cancel=send_cancel)

    # ---- internals ------------------------------------------------------

    @staticmethod
    def _market_data_kind(sub: Subscription) -> str | None:
        """Resolve the dedup-index kind for a market-data-shaped subscription.

        Returning ``None`` keeps the subscription out of
        ``by_market_data_key`` (the ``(conId, kind)`` dedup index) but
        still places it in ``by_reqid`` and ``ticker_by_reqid``. That is
        the right behaviour for:

          * Unqualified contracts (``conId == 0``) — multiple unrelated
            callers must not collapse into one entry.
          * Snapshot :class:`MktDataSub` — concurrent snapshots for the
            same contract are legitimate (each call is its own one-shot).

        :class:`TickByTickSub` carries its kind on the instance
        (``tickType``); other concrete classes use the class-level
        ``KIND``.
        """

        if not getattr(sub.contract, "conId", 0):
            return None
        if isinstance(sub, TickByTickSub):
            return sub.tickType or None
        if isinstance(sub, MktDataSub):
            return None if sub.snapshot else "mktData"
        if isinstance(sub, MktDepthSub):
            return type(sub).KIND
        return None
