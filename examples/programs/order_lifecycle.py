"""Check a limit order with what-if, and optionally place and cancel it.

By default this only asks TWS what the order would do (margin change and
commission); nothing is sent to the market. With ``--place`` it places the
order, waits until the order is working, cancels it, waits until it is
cancelled, and prints the order's log. Use a paper trading account and a
limit price away from the market, so the order does not fill.

Run::

    uv run --group examples examples/programs/order_lifecycle.py AAPL \\
        --action BUY --quantity 1 --limit 1.00            # what-if only
    uv run --group examples examples/programs/order_lifecycle.py AAPL \\
        --action BUY --quantity 1 --limit 1.00 --place    # place, then cancel
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from collections.abc import Callable
from decimal import Decimal

from ib_async import IB, Contract, LimitOrder, Order, OrderStatus, Stock, Trade

log = logging.getLogger("order_lifecycle")


def parseArgs(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("symbol", help="stock symbol, e.g. AAPL")
    parser.add_argument("--exchange", default="SMART")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--action", choices=("BUY", "SELL"), required=True)
    parser.add_argument("--quantity", type=Decimal, required=True)
    parser.add_argument("--limit", type=Decimal, required=True, help="limit price")
    parser.add_argument(
        "--place",
        action="store_true",
        help="place the order and cancel it (without this, what-if only)",
    )
    parser.add_argument(
        "--timeout", type=float, default=10, help="seconds to wait for each step"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497)
    parser.add_argument("--client-id", type=int, default=23)
    return parser.parse_args(argv)


async def whatIf(ib: IB, contract: Contract, order: Order) -> None:
    state = await ib.whatIfOrderAsync(contract, order)
    print(f"what-if for {order.action} {order.totalQuantity} {contract.symbol}:")
    print(f"  initial margin change      {state.initMarginChange or '-'}")
    print(f"  maintenance margin change  {state.maintMarginChange or '-'}")
    print(
        f"  commission and fees        {state.commissionAndFees or '-'} "
        f"{state.commissionCurrency}"
    )
    if state.warningText:
        print(f"  warning: {state.warningText}")


def acknowledged(trade: Trade) -> bool:
    """TWS has accepted the order (it may wait for the market to open as
    PreSubmitted) or has already finished it."""
    status = trade.orderStatus.status
    return status in (OrderStatus.PreSubmitted, OrderStatus.Submitted) or (
        trade.isDone()
    )


async def waitUntil(trade: Trade, reached: Callable[[], bool], seconds: float) -> bool:
    """Wait for each status change until ``reached()``; False if it is not
    reached within ``seconds``, or the connection drops first (which ends
    the trade's events, and so the loop)."""
    if not reached():
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(seconds):
                async for _ in trade.statusEvent:
                    if reached():
                        break
    return reached()


async def placeAndCancel(
    ib: IB, contract: Contract, order: Order, seconds: float
) -> bool:
    trade = ib.placeOrder(contract, order)
    log.info("placed order %s", trade.order.orderId)
    try:
        if not await waitUntil(trade, lambda: acknowledged(trade), seconds):
            log.error("TWS did not accept the order: %s", trade.orderStatus.status)
            return False
        log.info("order is %s", trade.orderStatus.status)
    finally:
        if not trade.isDone():
            ib.cancelOrder(order)
            if not await waitUntil(trade, trade.isDone, seconds):
                log.error("the order did not cancel: %s", trade.orderStatus.status)
        print(f"order {trade.order.orderId} log:")
        for entry in trade.log:
            print(f"  {entry.time:%H:%M:%S} {entry.status:<14} {entry.message}")
    return trade.orderStatus.status in (OrderStatus.Cancelled, OrderStatus.ApiCancelled)


async def main(args: argparse.Namespace) -> int:
    order = LimitOrder(args.action, args.quantity, args.limit)
    with IB() as ib:
        await ib.connectAsync(args.host, args.port, clientId=args.client_id)
        [contract] = await ib.qualifyContractsAsync(
            Stock(args.symbol, args.exchange, args.currency)
        )
        if not isinstance(contract, Contract):
            log.error("%s is not a unique stock on %s", args.symbol, args.exchange)
            return 1
        await whatIf(ib, contract, order)
        if not args.place:
            return 0
        return 0 if await placeAndCancel(ib, contract, order, args.timeout) else 1


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    try:
        sys.exit(asyncio.run(main(parseArgs())))
    except KeyboardInterrupt:
        sys.exit(130)
