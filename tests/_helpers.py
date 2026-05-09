"""Shared test helpers for injecting trades and fills directly into a
Wrapper without going through the wire.

Used by tests that exercise post-state behaviour (a late error, a
disconnect-driven teardown, a commissionReport callback for a known fill)
without setting up the full IB connection lifecycle.

Existing tests pre-date these helpers and use inline construction; new
tests should prefer ``inject_trade`` / ``inject_fill`` so the test layer
has one place to update if Wrapper's internal trade/fill maps ever
restructure.
"""

from __future__ import annotations

import ib_async as ibi
from ib_async.order import Order, OrderStatus, Trade


def inject_trade(
    ib: ibi.IB,
    *,
    orderId: int = 1,
    permId: int = 1,
    clientId: int | None = None,
    status: str = OrderStatus.Submitted,
    contract: ibi.Contract | None = None,
    conId: int | None = 12345,
) -> Trade:
    """Construct a Trade and register it on the wrapper's trades map.

    The trade is keyed by ``(clientId, orderId)`` exactly as the live
    ``openOrder`` callback would key it. ``clientId`` defaults to whatever
    is currently set on the wrapper, so callers in tests that pin
    ``ib.wrapper.clientId = 0`` can omit it.
    """
    if clientId is None:
        clientId = ib.wrapper.clientId
    if contract is None:
        contract = ibi.Stock("ABC", "SMART", "USD")
    if conId is not None:
        contract.conId = conId

    order = Order(orderId=orderId, clientId=clientId, permId=permId)
    orderStatus = OrderStatus(orderId=orderId, status=status)
    trade = Trade(contract, order, orderStatus, [], [])
    ib.wrapper.trades[(clientId, orderId)] = trade
    return trade


def inject_fill(
    ib: ibi.IB,
    *,
    execId: str,
    permId: int = 1,
    contract: ibi.Contract | None = None,
    time: object | None = None,
) -> ibi.Fill:
    """Construct a Fill and register it on the wrapper's fills map keyed
    by execId."""
    if contract is None:
        contract = ibi.Stock("AAPL")
    if time is None:
        time = ibi.util.EPOCH

    fill = ibi.Fill(
        contract=contract,
        execution=ibi.Execution(execId=execId, permId=permId),
        commissionReport=ibi.CommissionReport(),
        time=time,
    )
    ib.wrapper.fills[execId] = fill
    return fill
