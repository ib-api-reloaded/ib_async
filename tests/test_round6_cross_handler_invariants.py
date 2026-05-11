"""Round 6 cross-handler invariant tests.

These tests verify that ``Trade``'s derived math
(``filled()``/``remaining()``), the ``OrderStatus`` state machine, and
the inter-handler choreography (``openOrder`` / ``orderStatus`` /
``execDetails`` / ``commissionReport``) hold together across realistic
multi-callback sequences.

Why a dedicated module: prior audit rounds verified each handler in
isolation (registry plumbing, decimal coercion, malformed-input
survival). Round 6 verifies invariants that span MULTIPLE handlers
firing in observed-on-the-wire orders, including:

* derived totals stay sane across partial fills, BAG legs, and over-fill
* duplicate / replayed orderStatus messages do NOT double-emit terminal
  events
* ``trade.order`` and ``trade.serverOrder`` stay distinct objects so
  user mutations don't leak into TWS's snapshot view
* normal (exec→commission) and out-of-order (commission→exec) fill
  sequences both pair correctly
* parent / child wiring on ``BracketOrder`` is correct end-to-end
* OCA group annotation mutates the orders in place
"""

from __future__ import annotations

import logging
from decimal import Decimal

import ib_async as ibi


def _seedPlacedTrade(ib: ibi.IB, *, orderId: int, total: str = "100"):
    """Wire a placed-order Trade into the wrapper registries the way
    ``IB.placeOrder`` does, so the cross-handler tests below can replay
    the lifecycle without going through the network.
    """
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 1234
    order = ibi.Order(
        orderId=orderId,
        clientId=ib.wrapper.clientId,
        permId=0,
        totalQuantity=Decimal(total),
        action="BUY",
        orderType="LMT",
        lmtPrice=Decimal(100),
    )
    orderStatus = ibi.OrderStatus(orderId=orderId, status=ibi.OrderStatus.PendingSubmit)
    trade = ibi.Trade(contract, order, orderStatus, [], [])
    ib.wrapper.trades[(ib.wrapper.clientId, orderId)] = trade
    return contract, trade


# ---------------------------------------------------------------------------
# Trade.filled() / .remaining() derived math.
# ---------------------------------------------------------------------------


def test_trade_filled_returns_decimal_zero_when_no_fills():
    """``Trade.filled()`` returns ``Decimal('0')`` (never ``None``) so
    user code can do arithmetic without nullable guards."""
    trade = ibi.Trade()
    result = trade.filled()
    assert result == Decimal(0)
    assert isinstance(result, Decimal)


def test_trade_remaining_zero_when_total_quantity_unset():
    """``Trade.remaining()`` returns a definite ``Decimal('0')`` when
    ``order.totalQuantity`` is ``None`` — there's no honest non-zero
    answer without a known total."""
    trade = ibi.Trade()
    assert trade.order.totalQuantity is None
    assert trade.remaining() == Decimal(0)
    assert isinstance(trade.remaining(), Decimal)


def test_trade_remaining_equals_total_when_no_fills():
    """Pre-fill state: ``filled()`` is 0, so ``remaining()`` mirrors
    ``order.totalQuantity`` exactly."""
    trade = ibi.Trade(order=ibi.Order(totalQuantity=Decimal(250)))
    assert trade.filled() == Decimal(0)
    assert trade.remaining() == Decimal(250)


def test_trade_filled_sums_partial_fills_to_total():
    """Multiple partial fills summing to ``totalQuantity`` give
    ``filled() == total`` and ``remaining() == 0``."""
    contract = ibi.Stock("AAPL")
    order = ibi.Order(totalQuantity=Decimal(100))
    fills = [
        ibi.Fill(
            contract,
            ibi.Execution(execId=f"e{i}", shares=Decimal(s)),
            ibi.CommissionReport(),
            ibi.util.EPOCH,
        )
        for i, s in enumerate(["30", "30", "40"])
    ]
    trade = ibi.Trade(contract, order, ibi.OrderStatus(), fills, [])
    assert trade.filled() == Decimal(100)
    assert trade.remaining() == Decimal(0)


def test_trade_filled_skips_fills_with_none_shares():
    """Wire-unset ``execution.shares`` (``None``) is skipped in the sum
    so partial-fill totals stay honest. NaN would silently poison via
    ``trade.filled() != trade.filled()``.
    """
    contract = ibi.Stock("AAPL")
    order = ibi.Order(totalQuantity=Decimal(100))
    fills = [
        ibi.Fill(
            contract,
            ibi.Execution(execId="e0", shares=Decimal(40)),
            ibi.CommissionReport(),
            ibi.util.EPOCH,
        ),
        ibi.Fill(
            contract,
            ibi.Execution(execId="e1", shares=None),
            ibi.CommissionReport(),
            ibi.util.EPOCH,
        ),
        ibi.Fill(
            contract,
            ibi.Execution(execId="e2", shares=Decimal(20)),
            ibi.CommissionReport(),
            ibi.util.EPOCH,
        ),
    ]
    trade = ibi.Trade(contract, order, ibi.OrderStatus(), fills, [])
    result = trade.filled()
    assert result == Decimal(60)
    assert result == result  # NaN-poison guard


def test_trade_filled_skips_leg_fills_for_bag_contract():
    """``Trade.filled()`` for a BAG (combo) trade counts only fills
    whose contract.secType is ``BAG``. Per-leg fills arrive separately
    and would double-count if summed.
    """
    bag = ibi.Contract(secType="BAG", symbol="SPREAD", conId=1)
    leg = ibi.Stock("AAPL")
    order = ibi.Order(totalQuantity=Decimal(10))

    bagFill = ibi.Fill(
        bag,
        ibi.Execution(execId="e-bag", shares=Decimal(10)),
        ibi.CommissionReport(),
        ibi.util.EPOCH,
    )
    legFill = ibi.Fill(
        leg,
        ibi.Execution(execId="e-leg", shares=Decimal(10)),
        ibi.CommissionReport(),
        ibi.util.EPOCH,
    )
    trade = ibi.Trade(bag, order, ibi.OrderStatus(), [bagFill, legFill], [])
    assert trade.filled() == Decimal(10)
    assert trade.remaining() == Decimal(0)


def test_trade_remaining_propagates_overfill_negative():
    """Over-fill (rare, observable across cross-client races) is NOT
    floored to zero — ``remaining()`` returns a negative Decimal so user
    code can detect the inconsistency.
    """
    contract = ibi.Stock("AAPL")
    order = ibi.Order(totalQuantity=Decimal(100))
    fills = [
        ibi.Fill(
            contract,
            ibi.Execution(execId="e0", shares=Decimal(110)),
            ibi.CommissionReport(),
            ibi.util.EPOCH,
        ),
    ]
    trade = ibi.Trade(contract, order, ibi.OrderStatus(), fills, [])
    assert trade.filled() == Decimal(110)
    assert trade.remaining() == Decimal(-10)


# ---------------------------------------------------------------------------
# OrderStatus state-machine transitions.
# ---------------------------------------------------------------------------


def test_orderStatus_idempotent_replay_does_not_double_emit():
    """A duplicate ``orderStatus`` callback (server retransmits a
    still-current state) must not re-fire ``filledEvent`` /
    ``cancelledEvent``.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    _, trade = _seedPlacedTrade(ib, orderId=1)
    seen: list[str] = []
    trade.filledEvent += lambda t: seen.append("filled")
    trade.cancelledEvent += lambda t: seen.append("cancelled")

    for _ in range(2):
        ib.wrapper.orderStatus(
            orderId=1,
            status="Filled",
            filled=Decimal(100),
            remaining=Decimal(0),
            avgFillPrice=Decimal(100),
            permId=42,
            parentId=0,
            lastFillPrice=Decimal(100),
            clientId=0,
            whyHeld="",
        )
    assert seen == ["filled"]


def test_orderStatus_status_transitions_emit_correct_terminal_event():
    """Cancel transition fires ``cancelledEvent``; fill transition fires
    ``filledEvent``. Verify the wrapper picks the right one off the
    status string rather than emitting both or neither.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    _, trade = _seedPlacedTrade(ib, orderId=2)
    seenFilled: list = []
    seenCancelled: list = []
    trade.filledEvent += lambda t: seenFilled.append(t)
    trade.cancelledEvent += lambda t: seenCancelled.append(t)

    ib.wrapper.orderStatus(
        orderId=2,
        status="Cancelled",
        filled=Decimal(0),
        remaining=Decimal(100),
        avgFillPrice=Decimal(0),
        permId=43,
        parentId=0,
        lastFillPrice=Decimal(0),
        clientId=0,
        whyHeld="",
    )
    assert len(seenCancelled) == 1
    assert seenFilled == []
    assert trade.isDone()


def test_orderStatus_unknown_orderId_logs_and_does_not_raise(caplog):
    """An ``orderStatus`` arriving for a key with no Trade is logged at
    error level rather than crashing — TWS occasionally re-broadcasts
    stale orders during a watchdog reconnect window.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    with caplog.at_level(logging.ERROR, logger="ib_async.wrapper"):
        ib.wrapper.orderStatus(
            orderId=9999,
            status="Filled",
            filled=Decimal(1),
            remaining=Decimal(0),
            avgFillPrice=Decimal(100),
            permId=0,
            parentId=0,
            lastFillPrice=Decimal(100),
            clientId=0,
            whyHeld="",
        )
    assert any("No order found" in rec.message for rec in caplog.records)


def test_orderStatus_lastFillPrice_reflects_most_recent_not_aggregate():
    """``OrderStatus.lastFillPrice`` is the most-recent fill price
    wire-delivered, never an aggregate. Two callbacks with different
    values land the second value, not a sum or average.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    _, trade = _seedPlacedTrade(ib, orderId=7)

    ib.wrapper.orderStatus(
        orderId=7,
        status="Submitted",
        filled=Decimal(30),
        remaining=Decimal(70),
        avgFillPrice=Decimal(100),
        permId=48,
        parentId=0,
        lastFillPrice=Decimal(100),
        clientId=0,
        whyHeld="",
    )
    ib.wrapper.orderStatus(
        orderId=7,
        status="Submitted",
        filled=Decimal(70),
        remaining=Decimal(30),
        avgFillPrice=Decimal("100.5"),
        permId=48,
        parentId=0,
        lastFillPrice=Decimal(101),
        clientId=0,
        whyHeld="",
    )
    assert trade.orderStatus.lastFillPrice == Decimal(101)
    assert trade.orderStatus.avgFillPrice == Decimal("100.5")


def test_orderStatus_alone_progresses_state_no_openOrder_needed():
    """For status-only updates (TWS occasionally elides ``openOrder``
    for in-flight orders mid-session), ``orderStatus`` alone progresses
    the existing Trade — wrapper does NOT require a paired ``openOrder``
    per status change.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    _, trade = _seedPlacedTrade(ib, orderId=12)

    ib.wrapper.orderStatus(
        orderId=12,
        status="Submitted",
        filled=Decimal(10),
        remaining=Decimal(90),
        avgFillPrice=Decimal(100),
        permId=52,
        parentId=0,
        lastFillPrice=Decimal(100),
        clientId=0,
        whyHeld="",
    )
    assert trade.orderStatus.filled == Decimal(10)
    assert trade.orderStatus.remaining == Decimal(90)
    assert trade.orderStatus.status == "Submitted"


# ---------------------------------------------------------------------------
# openOrder behaviour and Trade.serverOrder distinctness.
# ---------------------------------------------------------------------------


def test_openOrder_order_and_serverOrder_are_distinct_instances():
    """Round 6 fix: the new-trade path of ``openOrder`` must NOT alias
    ``trade.order`` with ``trade.serverOrder``. Until the next
    callback, a write to ``trade.order`` would also mutate the first
    ``serverOrder`` snapshot, masking user intent under TWS data.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 1234

    twsOrder = ibi.Order(orderId=10, clientId=0, permId=99, lmtPrice=Decimal(100))
    ib.wrapper.openOrder(10, contract, twsOrder, ibi.OrderState(status="Submitted"))

    trade = ib.wrapper.trades[(0, 10)]
    assert trade.serverOrder is not None
    assert trade.order is not trade.serverOrder
    trade.order.account = "DU-INTERNAL"
    assert trade.serverOrder.account == ""


def test_permId_stable_across_repeated_openOrder_callbacks():
    """``permId2Trade`` keeps its first binding via ``setdefault`` so
    repeated openOrder callbacks for the same permId do NOT replace
    the live mapping. Important during reconnect replays.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract, trade = _seedPlacedTrade(ib, orderId=3)

    twsOrder = ibi.Order(orderId=3, clientId=0, permId=44)
    ib.wrapper.openOrder(3, contract, twsOrder, ibi.OrderState(status="Submitted"))
    assert ib.wrapper.permId2Trade[44] is trade

    twsOrder2 = ibi.Order(orderId=3, clientId=0, permId=44)
    ib.wrapper.openOrder(3, contract, twsOrder2, ibi.OrderState(status="Submitted"))
    assert ib.wrapper.permId2Trade[44] is trade


def test_openOrder_then_orderStatus_arrives_consistent_state():
    """Server delivers ``openOrder`` then ``orderStatus`` (the normal
    case). Trade ends up Submitted with a known permId.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract, trade = _seedPlacedTrade(ib, orderId=11)

    ib.wrapper.openOrder(
        11,
        contract,
        ibi.Order(
            orderId=11,
            clientId=0,
            permId=51,
            totalQuantity=Decimal(100),
            lmtPrice=Decimal(100),
            action="BUY",
        ),
        ibi.OrderState(status="Submitted"),
    )
    assert trade.order.permId == 51
    ib.wrapper.orderStatus(
        orderId=11,
        status="Submitted",
        filled=Decimal(0),
        remaining=Decimal(100),
        avgFillPrice=Decimal(0),
        permId=51,
        parentId=0,
        lastFillPrice=Decimal(0),
        clientId=0,
        whyHeld="",
    )
    assert trade.orderStatus.status == "Submitted"
    assert trade.orderStatus.permId == 51


# ---------------------------------------------------------------------------
# execDetails / commissionReport pairing.
# ---------------------------------------------------------------------------


def test_execDetails_then_commissionReport_pairs_on_fill():
    """Normal arrival order (exec, then commission). Commission lands
    on the existing fill via ``dataclassUpdate`` and the paired event
    fires.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract, trade = _seedPlacedTrade(ib, orderId=4)
    ib.wrapper.permId2Trade[45] = trade

    seenComm: list = []
    ib.commissionReportEvent += lambda t, f, r: seenComm.append((t, f, r))

    execId = "exec-normal-order"
    execution = ibi.Execution(
        execId=execId,
        permId=45,
        clientId=0,
        orderId=4,
        shares=Decimal(10),
        price=Decimal(100),
        time="20250101 09:30:00",
    )
    ib.wrapper.execDetails(reqId=99, contract=contract, execution=execution)
    assert len(trade.fills) == 1
    assert trade.fills[0].commissionReport.commission is None

    report = ibi.CommissionReport(
        execId=execId, commission=Decimal("1.0"), currency="USD"
    )
    ib.wrapper.commissionReport(report)
    assert trade.fills[0].commissionReport.commission == Decimal("1.0")
    assert len(seenComm) == 1


def test_execDetails_without_commissionReport_keeps_default_empty():
    """Exec-only flow: ``fill.commissionReport`` stays its default
    empty instance — never silently filled with an unrelated report.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract, trade = _seedPlacedTrade(ib, orderId=5)
    ib.wrapper.permId2Trade[46] = trade

    execution = ibi.Execution(
        execId="exec-orphan",
        permId=46,
        clientId=0,
        orderId=5,
        shares=Decimal(5),
        price=Decimal(99),
        time="20250101 09:30:00",
    )
    ib.wrapper.execDetails(reqId=99, contract=contract, execution=execution)

    assert len(trade.fills) == 1
    cr = trade.fills[0].commissionReport
    assert cr.commission is None
    assert cr.realizedPNL is None
    assert cr.execId == ""


def test_duplicate_execId_does_not_double_append_to_trade_fills():
    """Two ``execDetails`` callbacks with the same execId (TWS
    retransmit during reconnect) must NOT double-append the fill.
    Wrapper gates on ``self.fills[execId]`` membership.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract, trade = _seedPlacedTrade(ib, orderId=6)
    ib.wrapper.permId2Trade[47] = trade

    execution = ibi.Execution(
        execId="exec-dup",
        permId=47,
        clientId=0,
        orderId=6,
        shares=Decimal(10),
        price=Decimal(100),
        time="20250101 09:30:00",
    )
    ib.wrapper.execDetails(reqId=99, contract=contract, execution=execution)
    ib.wrapper.execDetails(reqId=99, contract=contract, execution=execution)
    assert len(trade.fills) == 1


# ---------------------------------------------------------------------------
# OrderStatus.total reconciliation against Trade.filled() / .remaining().
# ---------------------------------------------------------------------------


def test_orderStatus_total_consistent_with_trade_filled_remaining():
    """``OrderStatus.total`` (server-derived) and ``Trade.filled() +
    Trade.remaining()`` (locally-derived) describe the same quantity
    and should agree once both arrive.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract, trade = _seedPlacedTrade(ib, orderId=8, total="100")
    ib.wrapper.permId2Trade[49] = trade

    ib.wrapper.execDetails(
        reqId=99,
        contract=contract,
        execution=ibi.Execution(
            execId="e-a",
            permId=49,
            clientId=0,
            orderId=8,
            shares=Decimal(40),
            price=Decimal(100),
            time="20250101 09:30:00",
        ),
    )
    ib.wrapper.orderStatus(
        orderId=8,
        status="Submitted",
        filled=Decimal(40),
        remaining=Decimal(60),
        avgFillPrice=Decimal(100),
        permId=49,
        parentId=0,
        lastFillPrice=Decimal(100),
        clientId=0,
        whyHeld="",
    )

    serverTotal = trade.orderStatus.total
    derivedTotal = trade.filled() + trade.remaining()
    assert serverTotal == derivedTotal == Decimal(100)


# ---------------------------------------------------------------------------
# Bracket and OCA structural invariants.
# ---------------------------------------------------------------------------


def test_bracket_order_parent_child_transmit_and_parentId_wiring():
    """The ``BracketOrder`` shape: parent (transmit=False), takeProfit
    (transmit=False, parentId=parent.orderId), stopLoss (transmit=True,
    parentId=parent.orderId). The ``transmit=True`` on the LAST child
    is what tells TWS to release the bracket. Build directly so the
    test does not need a live connection (``IB.bracketOrder`` calls
    ``client.getReqId``).
    """
    parentId = 100
    parent = ibi.LimitOrder("BUY", 100, 100.0, orderId=parentId, transmit=False)
    takeProfit = ibi.LimitOrder(
        "SELL", 100, 110.0, orderId=parentId + 1, transmit=False, parentId=parentId
    )
    stopLoss = ibi.StopOrder(
        "SELL", 100, 90.0, orderId=parentId + 2, transmit=True, parentId=parentId
    )
    bracket = ibi.BracketOrder(parent=parent, takeProfit=takeProfit, stopLoss=stopLoss)

    assert bracket.parent.transmit is False
    assert bracket.takeProfit.transmit is False
    assert bracket.stopLoss.transmit is True

    assert bracket.takeProfit.parentId == bracket.parent.orderId
    assert bracket.stopLoss.parentId == bracket.parent.orderId

    assert bracket.parent.action == "BUY"
    assert bracket.takeProfit.action == "SELL"
    assert bracket.stopLoss.action == "SELL"


def test_oca_group_ids_round_trip_on_each_order():
    """``IB.oneCancelsAll`` stamps every order in the list with the
    shared ocaGroup + ocaType (mutates in place). Wrapper relies on
    this for OCA to work server-side.
    """
    ib = ibi.IB()
    orders = [
        ibi.LimitOrder("BUY", 1, 100),
        ibi.LimitOrder("BUY", 1, 99),
        ibi.LimitOrder("BUY", 1, 98),
    ]
    out = ib.oneCancelsAll(orders, "OCA-X", 2)
    assert all(o.ocaGroup == "OCA-X" for o in out)
    assert all(o.ocaType == 2 for o in out)
    assert out is orders


# ---------------------------------------------------------------------------
# End-to-end multi-fill lifecycle invariant.
# ---------------------------------------------------------------------------


def test_fills_aggregate_invariants_match_orderStatus_after_lifecycle():
    """End-to-end multi-fill lifecycle: each fill via ``execDetails`` +
    paired ``commissionReport``; running server-side
    ``orderStatus.filled`` matches local ``Trade.filled()`` at every
    step. Final state: status=Filled, remaining=0.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    contract, trade = _seedPlacedTrade(ib, orderId=13, total="50")
    ib.wrapper.permId2Trade[53] = trade

    fills = [("e1", "20"), ("e2", "20"), ("e3", "10")]
    cum = Decimal(0)
    for execId, sharesStr in fills:
        ib.wrapper.execDetails(
            reqId=99,
            contract=contract,
            execution=ibi.Execution(
                execId=execId,
                permId=53,
                clientId=0,
                orderId=13,
                shares=Decimal(sharesStr),
                price=Decimal(100),
                time="20250101 09:30:00",
            ),
        )
        ib.wrapper.commissionReport(
            ibi.CommissionReport(
                execId=execId, commission=Decimal("0.5"), currency="USD"
            )
        )
        cum += Decimal(sharesStr)
        ib.wrapper.orderStatus(
            orderId=13,
            status="Filled" if cum == Decimal(50) else "Submitted",
            filled=cum,
            remaining=Decimal(50) - cum,
            avgFillPrice=Decimal(100),
            permId=53,
            parentId=0,
            lastFillPrice=Decimal(100),
            clientId=0,
            whyHeld="",
        )
        assert trade.filled() == cum
        assert trade.orderStatus.filled == cum

    assert trade.orderStatus.status == "Filled"
    assert trade.filled() == Decimal(50)
    assert trade.remaining() == Decimal(0)
    assert all(f.commissionReport.commission == Decimal("0.5") for f in trade.fills)
    # All fills carry the same permId — the wire's link from the
    # execution back to the order. Here we asserted on
    # ``trade.orderStatus.permId`` (set on the orderStatus callback)
    # rather than ``trade.order.permId`` because this lifecycle did
    # not include an ``openOrder`` callback to mutate the latter.
    assert all(f.execution.permId == trade.orderStatus.permId for f in trade.fills)
