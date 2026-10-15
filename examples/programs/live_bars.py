"""Build bars from a stock's live trades, with a session VWAP and an EMA.

Subscribes to one stock's market data and aggregates its trades into
bars locally, one per interval (a minute by default). Each completed bar
is printed with two indicators computed over the completed bars: the
session's volume-weighted average price (VWAP), and an exponential
moving average (EMA) of the closes. Each indicator is a running fold over
the bars, constant time per bar, built from the bar stream's operators.
Runs for a set number of seconds or until Ctrl-C, and stops with exit
code 1 if the connection to TWS / IB Gateway drops.

Run::

    uv run --group examples examples/programs/live_bars.py AAPL \\
        --interval 60 --seconds 600 --delayed
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
from dataclasses import dataclass
from decimal import Decimal

from eventkit import Event

from ib_async import IB, Contract, RealTimeBar, Stock

log = logging.getLogger("live_bars")

# reqMarketDataType: 1 is live data, 3 is delayed data (free, 15-20 minutes
# behind) where there is no live subscription.
LIVE = 1
DELAYED = 3


def parseArgs(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("symbol", help="stock symbol, e.g. AAPL")
    parser.add_argument("--exchange", default="SMART")
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--interval", type=float, default=60, help="seconds of one bar")
    parser.add_argument("--ema", type=int, default=10, help="bars in the EMA")
    parser.add_argument(
        "--seconds", type=float, default=0, help="stop after this long; 0 runs on"
    )
    parser.add_argument(
        "--delayed",
        action="store_true",
        help="use delayed data where there is no live subscription",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497)
    parser.add_argument("--client-id", type=int, default=23)
    return parser.parse_args(argv)


@dataclass(frozen=True, slots=True)
class SessionVwap:
    """The session's volume-weighted average price so far: the running
    sums of price × volume and of volume over the completed bars."""

    priceVolume: Decimal = Decimal(0)
    volume: Decimal = Decimal(0)

    def add(self, bar: RealTimeBar) -> SessionVwap:
        if bar.wap is None or not bar.volume:
            return self
        return SessionVwap(
            self.priceVolume + bar.wap * bar.volume, self.volume + bar.volume
        )

    @property
    def value(self) -> Decimal | None:
        return self.priceVolume / self.volume if self.volume else None


@dataclass(frozen=True, slots=True)
class Annotated:
    """A completed bar, with the indicators as of that bar."""

    bar: RealTimeBar
    vwap: Decimal | None
    ema: float


def annotate(bars: Event, emaBars: int) -> Event:
    """Each completed bar, as an :class:`Annotated`: the session VWAP is
    a running fold (``reduce``) over the bars, the EMA eventkit's own
    operator over their closes (a completed bar always has one)."""
    vwap = bars.reduce(SessionVwap.add, SessionVwap()).map(lambda s: s.value)
    ema = bars.map(lambda bar: float(bar.close)).ema(emaBars)
    return bars.zip(vwap, ema).map(Annotated)


def formatBar(annotated: Annotated) -> str:
    bar = annotated.bar
    vwap = "-" if annotated.vwap is None else f"{annotated.vwap:.4f}"
    return (
        f"{bar.time:%H:%M:%S} "
        f"open {bar.open} high {bar.high} low {bar.low} close {bar.close} "
        f"volume {bar.volume} wap {bar.wap if bar.wap is not None else '-'}  "
        f"session vwap {vwap}  ema {annotated.ema:.4f}"
    )


async def printBars(annotated: Event) -> None:
    """Print every annotated bar, forever."""
    async for bar in annotated:
        print(formatBar(bar), flush=True)


async def streamUntil(ib: IB, annotated: Event, seconds: float) -> bool:
    """Print bars for ``seconds`` (forever if 0). False if the connection
    dropped first."""
    printing = asyncio.ensure_future(printBars(annotated))
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
        [contract] = await ib.qualifyContractsAsync(
            Stock(args.symbol, args.exchange, args.currency)
        )
        if not isinstance(contract, Contract):
            log.error("%s is not a unique stock", args.symbol)
            return 1
        ticker = ib.reqMktData(contract)
        # A bar per interval, each starting on the interval's boundary.
        timer = Event.timerange(start=0, step=args.interval)
        bars = ticker.updateEvent.trades().timebars(timer)
        try:
            if not await streamUntil(ib, annotate(bars, args.ema), args.seconds):
                log.error("the connection to TWS / IB Gateway dropped")
                return 1
        finally:
            if ib.isConnected():
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
