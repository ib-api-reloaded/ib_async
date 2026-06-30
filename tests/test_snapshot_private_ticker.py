"""Snapshot market-data requests must not hand back a *pooled* Ticker.

``reqMktData(snapshot=True)`` returns synchronously, before the snapshot's
ticks arrive. If it returned the per-contract pooled Ticker (shared across
streaming / tick-by-tick / depth and every prior snapshot), a caller that
read ``ticker.last`` / ``ticker.marketPrice()`` in the window before
``tickSnapshotEnd`` would observe scalar prices carried over from a *prior*
snapshot of the same contract — silently stale data.

The fix gives every snapshot a private, unpooled Ticker
(:meth:`SubscriptionRegistry.new_snapshot_ticker`):

  * it starts clean, so a racing read sees the unset sentinel
    (``Ticker.isUnset`` — ``None`` or the configured ``IBDefaults.unset``)
    rather than a stale prior value;
  * it is isolated, so a snapshot can neither blank nor be blanked by a
    concurrent consumer of the contract's pooled Ticker;
  * its subscription lifecycle ends at ``tickSnapshotEnd`` so it does not
    accumulate in the registry.

Streaming (``snapshot=False``) is unchanged: it still returns the shared
pooled Ticker so one object reflects every live tick stream.
"""

from unittest.mock import MagicMock

import ib_async as ibi
from ib_async._subscriptions import TickByTickSub


def _wired_ib() -> ibi.IB:
    """An IB whose client is a MagicMock so wire calls can be asserted
    without a real connection."""
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.side_effect = iter(range(100, 1000))
    # IB.__del__ -> disconnect short-circuits when isConnected() is False.
    ib.client.isConnected.return_value = False
    return ib


def _stock(conId: int) -> ibi.Stock:
    s = ibi.Stock("ABC", "SMART", "USD")
    s.conId = conId
    return s


# ---- private, clean snapshot ticker ---------------------------------------


def test_snapshot_ticker_is_private_and_starts_clean():
    """A snapshot must return its own Ticker, never the pooled one, and it
    must start clean even when the pool already holds stale scalars."""
    ib = _wired_ib()
    contract = _stock(123)

    # A prior stream/snapshot left stale values on the pooled Ticker.
    pooled = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    pooled.last = 4032.3
    pooled.bid = 4031.9
    pooled.ask = 4032.2

    snap = ib.reqMktData(contract, snapshot=True)

    # Distinct object, not the pooled one, and not added to the pool.
    assert snap is not pooled
    assert ib.wrapper.subscriptions.ticker_for_contract(contract) is pooled
    # Clean slate — a racing read sees the unset sentinel, not the stale
    # 4032.3. Asserted via Ticker.isUnset so this holds whether the branch's
    # IBDefaults.unset is None or nan.
    assert snap.isUnset(snap.last)
    assert snap.isUnset(snap.bid)
    assert snap.isUnset(snap.ask)
    assert snap.isUnset(snap.marketPrice())
    # A wire snapshot request was issued.
    ib.client.reqMktData.assert_called_once()


def test_snapshot_ticks_route_to_private_ticker_only():
    """Ticks for the snapshot's reqId update the private snapshot Ticker
    and never leak onto the pooled Ticker."""
    ib = _wired_ib()
    contract = _stock(123)

    pooled = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    pooled.last = 4032.3

    snap = ib.reqMktData(contract, snapshot=True)
    reqId = 100  # first id from the side_effect

    # tickType 4 == last trade.
    ib.wrapper.priceSizeTick(reqId, 4, 4040.5, 1)

    assert snap.last == 4040.5
    assert pooled.last == 4032.3  # untouched


def test_two_snapshots_same_contract_are_distinct_objects():
    """Consecutive snapshots of one contract must be independent objects so
    the second never inherits the first's scalars."""
    ib = _wired_ib()
    contract = _stock(123)

    first = ib.reqMktData(contract, snapshot=True)
    second = ib.reqMktData(contract, snapshot=True)

    assert first is not second
    assert ib.client.reqMktData.call_count == 2


# ---- snapshot subscription lifecycle --------------------------------------


def test_tick_snapshot_end_closes_snapshot_sub_without_cancel():
    """``tickSnapshotEnd`` drops the one-shot snapshot subscription from the
    registry and must not send a wire cancel (cancelling a snapshot is a
    protocol error)."""
    ib = _wired_ib()
    contract = _stock(123)

    snap = ib.reqMktData(contract, snapshot=True)
    reqId = 100

    assert ib.wrapper.subscriptions.get_sub(reqId) is not None
    assert ib.wrapper.subscriptions.get_ticker(reqId) is snap

    ib.wrapper.tickSnapshotEnd(reqId)

    # Subscription and its reqId views are gone; no cancel was sent.
    assert ib.wrapper.subscriptions.get_sub(reqId) is None
    assert ib.wrapper.subscriptions.get_ticker(reqId) is None
    ib.client.cancelMktData.assert_not_called()

    # A late tick after the snapshot ends finds no ticker and is a no-op,
    # so the (now caller-owned) snapshot Ticker is frozen at its unset state.
    ib.wrapper.priceSizeTick(reqId, 4, 9999.0, 1)
    assert snap.isUnset(snap.last)


def test_hard_error_closes_snapshot_sub():
    """A snapshot terminates on a hard IB rejection (e.g. 354 'not
    subscribed') with no ``tickSnapshotEnd``. Since ``reqMktData(snapshot=
    True)`` has no awaited future / ``finally`` to reclaim it, ``error``
    must drop the one-shot sub and its private Ticker — otherwise they leak
    in the registry for the life of the connection (uncancellable, because
    snapshot subs are not in the market-data dedup index)."""
    ib = _wired_ib()
    contract = _stock(987)

    snap = ib.reqMktData(contract, snapshot=True)
    reqId = 100
    assert ib.wrapper.subscriptions.get_sub(reqId) is not None
    assert ib.wrapper.subscriptions.get_ticker(reqId) is snap

    # 354 == "Requested market data is not subscribed" (terminal, no data).
    ib.wrapper.error(reqId, 354, "not subscribed", "")

    assert ib.wrapper.subscriptions.get_sub(reqId) is None
    assert ib.wrapper.subscriptions.get_ticker(reqId) is None
    ib.client.cancelMktData.assert_not_called()


def test_repeated_failed_snapshots_do_not_accumulate():
    """Polling a contract that IB keeps rejecting must not grow the
    registry — each failed snapshot is fully reclaimed."""
    ib = _wired_ib()
    contract = _stock(987)

    for _ in range(5):
        ib.reqMktData(contract, snapshot=True)
        # Each registered sub is the most recent reqId.
        reqId = next(iter(s.reqId for s in ib.wrapper.subscriptions))
        ib.wrapper.error(reqId, 354, "not subscribed", "")

    assert list(ib.wrapper.subscriptions) == []


def test_warning_does_not_close_snapshot_sub():
    """A *warning* (e.g. 10167 'displaying delayed market data') is not
    terminal — IB still finishes the snapshot with ``tickSnapshotEnd`` — so
    the snapshot sub must survive the warning."""
    ib = _wired_ib()
    contract = _stock(987)

    ib.reqMktData(contract, snapshot=True)
    reqId = 100

    # 10167 is in _WARNING_CODES: delayed data is substituted, snapshot
    # still completes.
    ib.wrapper.error(reqId, 10167, "displaying delayed market data", "")

    assert ib.wrapper.subscriptions.get_sub(reqId) is not None


def test_tick_snapshot_end_leaves_streaming_sub_alone():
    """``tickSnapshotEnd`` must only close *snapshot* subscriptions, never a
    streaming mktData subscription that happens to share the reqId space."""
    ib = _wired_ib()
    contract = _stock(456)

    ib.reqMktData(contract, snapshot=False)
    reqId = 100

    ib.wrapper.tickSnapshotEnd(reqId)

    # Streaming sub survives — it is not a one-shot.
    assert ib.wrapper.subscriptions.get_sub(reqId) is not None


# ---- streaming path is unchanged ------------------------------------------


def test_streaming_reqMktData_still_returns_pooled_ticker():
    """``snapshot=False`` keeps the shared pooled Ticker and its idempotent
    re-subscribe (one wire call, same object)."""
    ib = _wired_ib()
    contract = _stock(789)

    a = ib.reqMktData(contract, snapshot=False)
    b = ib.reqMktData(contract, snapshot=False)

    assert a is b
    assert a is ib.wrapper.subscriptions.ticker_for_contract(contract)
    assert ib.client.reqMktData.call_count == 1


def test_snapshot_reuses_live_stream_ticker():
    """When a stream is already live, ``snapshot=True`` returns that fresh
    pooled Ticker and issues no extra request — the stream keeps it fresh,
    so there is no staleness to guard against."""
    ib = _wired_ib()
    contract = _stock(321)

    streamed = ib.reqMktData(contract, snapshot=False)
    assert ib.client.reqMktData.call_count == 1

    snap = ib.reqMktData(contract, snapshot=True)

    assert snap is streamed  # reused the live pooled Ticker
    assert ib.client.reqMktData.call_count == 1  # no second wire request


def test_snapshot_isolated_from_live_tickbytick_consumer():
    """A snapshot taken while a tick-by-tick subscription is live must get
    its own Ticker — the snapshot can neither be blanked by, nor blank, the
    tick-by-tick consumer's pooled Ticker."""
    ib = _wired_ib()
    contract = _stock(654)

    tbt_ticker = ib.reqTickByTickData(contract, "BidAsk")
    tbt_ticker.bid = 100.0  # live value owned by the tickByTick consumer

    snap = ib.reqMktData(contract, snapshot=True)

    assert snap is not tbt_ticker
    assert snap.isUnset(snap.bid)  # private + clean
    assert tbt_ticker.bid == 100.0  # untouched by the snapshot
    # The tick-by-tick consumer still owns the pooled Ticker.
    assert ib.wrapper.subscriptions.ticker_for_contract(contract) is tbt_ticker
    assert isinstance(
        ib.wrapper.subscriptions.find_market_data(654, "BidAsk"), TickByTickSub
    )


# ---- reqTickersAsync ------------------------------------------------------


async def test_reqTickersAsync_returns_private_clean_tickers():
    """``reqTickersAsync`` returns private snapshot Tickers (not the pooled
    ones), each filled with only its own snapshot, and cleans up its subs."""
    ib = _wired_ib()
    contracts = [_stock(11), _stock(22)]

    # Seed stale values into each pooled Ticker.
    for c in contracts:
        pooled = ib.wrapper.subscriptions.get_or_create_ticker(c)
        pooled.last = 1234.0

    # Resolve each snapshot the moment its wire request is "sent".
    def _complete_snapshot(reqId, *_args, **_kwargs):
        ib.wrapper.tickSnapshotEnd(reqId)

    ib.client.reqMktData.side_effect = _complete_snapshot

    tickers = await ib.reqTickersAsync(*contracts)

    assert len(tickers) == 2
    for c, t in zip(contracts, tickers):
        pooled = ib.wrapper.subscriptions.ticker_for_contract(c)
        assert t is not pooled  # private snapshot object
        assert t.isUnset(t.last)  # clean — no stale 1234.0 carried over
        assert pooled.last == 1234.0  # pooled Ticker untouched

    # Every snapshot sub was unregistered (by tickSnapshotEnd and/or the
    # finally clause).
    assert list(ib.wrapper.subscriptions) == []


# ---- disconnect ------------------------------------------------------------


def test_disconnect_sets_done_on_inflight_snapshot_ticker():
    """A private snapshot Ticker is not in the pool, so connectionClosed
    must still wake awaiters on its ``updateEvent`` — otherwise an awaiter
    would hang after a mid-snapshot disconnect."""
    ib = _wired_ib()
    contract = _stock(777)

    snap = ib.reqMktData(contract, snapshot=True)
    assert snap.updateEvent.done() is False

    ib.wrapper.connectionClosed()

    assert snap.updateEvent.done() is True
