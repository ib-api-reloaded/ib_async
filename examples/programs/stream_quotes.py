"""Stream quotes for one or more stocks until stopped.

Subscribes to market data for each stock and prints a line whenever a
quote changes, for a set number of seconds or until Ctrl-C. If the
connection to TWS / IB Gateway drops, the program stops with exit code 1
instead of waiting for quotes that will not come. The subscriptions are
cancelled however the program ends.

Run::

    uv run --group examples examples/programs/stream_quotes.py AAPL MSFT \\
        --seconds 60 --delayed
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys

from ib_async import IB, Contract, Stock, Ticker

log = logging.getLogger("stream_quotes")

# reqMarketDataType: 1 is live data, 3 is delayed data (free, 15-20 minutes
# behind) where there is no live subscription.
LIVE = 1
DELAYED = 3


def parseArgs(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("symbols", nargs="+", help="stock symbols, e.g. AAPL MSFT")
    parser.add_argument("--exchange", default="SMART")
    parser.add_argument("--currency", default="USD")
    parser.add_argument(
        "--seconds",
        type=float,
        default=0,
        help="stop after this long; 0 runs until Ctrl-C",
    )
    parser.add_argument(
        "--delayed",
        action="store_true",
        help="use delayed data where there is no live subscription",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497)
    parser.add_argument("--client-id", type=int, default=22)
    return parser.parse_args(argv)


def formatQuote(ticker: Ticker) -> str:
    def value(x: float | None) -> str:
        return "-" if x is None else f"{x:g}"

    time = ticker.time.strftime("%H:%M:%S") if ticker.time else "--:--:--"
    symbol = ticker.contract.symbol if ticker.contract else "?"
    return (
        f"{time} {symbol:<6} "
        f"bid {value(ticker.bidSize)} @ {value(ticker.bid)}  "
        f"ask {value(ticker.askSize)} @ {value(ticker.ask)}  "
        f"last {value(ticker.last)}"
    )


async def printQuotes(ib: IB) -> None:
    """Print every quote update, forever."""
    async for tickers in ib.pendingTickersEvent:
        for ticker in tickers:
            print(formatQuote(ticker), flush=True)


async def streamUntil(ib: IB, seconds: float) -> bool:
    """Print quotes for ``seconds`` (forever if 0). False if the
    connection dropped first."""
    printing = asyncio.ensure_future(printQuotes(ib))
    # an event is awaitable: this completes on its next emit
    dropped = asyncio.ensure_future(ib.disconnectedEvent)
    try:
        done, _ = await asyncio.wait(
            {printing, dropped},
            timeout=seconds or None,
            return_when=asyncio.FIRST_COMPLETED,
        )
    finally:
        for task in (printing, dropped):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
    return dropped not in done


async def main(args: argparse.Namespace) -> int:
    with IB() as ib:
        await ib.connectAsync(args.host, args.port, clientId=args.client_id)
        ib.reqMarketDataType(DELAYED if args.delayed else LIVE)
        stocks = [Stock(s, args.exchange, args.currency) for s in args.symbols]
        qualified = await ib.qualifyContractsAsync(*stocks)
        contracts = [c for c in qualified if isinstance(c, Contract)]
        for symbol, contract in zip(args.symbols, qualified, strict=True):
            if not isinstance(contract, Contract):
                log.warning("skipping %s: not a unique stock", symbol)
        if not contracts:
            log.error("none of the symbols is a unique stock")
            return 1
        for contract in contracts:
            ib.reqMktData(contract)
        try:
            if not await streamUntil(ib, args.seconds):
                log.error("the connection to TWS / IB Gateway dropped")
                return 1
        finally:
            if ib.isConnected():
                for contract in contracts:
                    ib.cancelMktData(contract)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    try:
        sys.exit(asyncio.run(main(parseArgs())))
    except KeyboardInterrupt:
        sys.exit(130)
