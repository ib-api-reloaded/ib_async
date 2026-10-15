"""Download historical bars for a stock into a Parquet file.

Requests the bars backwards from now, one chunk at a time, until it has
the number of chunks asked for or the server has no older bars. IBKR
limits how fast historical data may be requested, so the program pauses
between requests. The bars are written oldest first, without duplicates,
as a polars DataFrame: prices and volumes as Decimal columns, ``date``
with its time zone.

Run::

    uv run --group examples examples/programs/download_bars.py TSLA \\
        --bar-size "5 mins" --chunk "5 D" --chunks 4 --out tsla.parquet
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import sys
from pathlib import Path
from typing import get_args

from ib_async import (
    IB,
    BarData,
    BarSize,
    Contract,
    HistoricalData,
    Stock,
    WhatToShow,
    checkDuration,
    util,
)

log = logging.getLogger("download_bars")


def parseArgs(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("symbol", help="stock symbol, e.g. TSLA")
    parser.add_argument("--exchange", default="SMART")
    parser.add_argument("--currency", default="USD")
    parser.add_argument(
        "--bar-size", type=BarSize, choices=list(BarSize), default=BarSize.HOUR_1
    )
    parser.add_argument(
        "--chunk",
        type=checkDuration,
        default="30 D",
        help="duration of each request, e.g. 5 D, 1 W",
    )
    parser.add_argument("--chunks", type=int, default=3, help="requests to make")
    parser.add_argument(
        "--what",
        type=WhatToShow,
        # The data bars are built from: every whatToShow but SCHEDULE.
        choices=[w for w in WhatToShow if w in get_args(HistoricalData)],
        default=WhatToShow.TRADES,
    )
    parser.add_argument(
        "--all-hours",
        action="store_true",
        help="include bars outside regular trading hours",
    )
    parser.add_argument(
        "--pause", type=float, default=2.0, help="seconds between requests"
    )
    parser.add_argument("--out", type=Path, default=Path("bars.parquet"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7497)
    parser.add_argument("--client-id", type=int, default=21)
    return parser.parse_args(argv)


async def qualify(ib: IB, contract: Contract) -> Contract | None:
    """The contract with its details filled in, or None if it is unknown
    or ambiguous."""
    [qualified] = await ib.qualifyContractsAsync(contract)
    return qualified if isinstance(qualified, Contract) else None


async def downloadBars(
    ib: IB,
    contract: Contract,
    *,
    barSize: BarSize,
    chunk: str,
    chunks: int,
    what: HistoricalData,
    useRTH: bool,
    pause: float,
) -> list[BarData]:
    """Up to ``chunks`` requests of ``chunk`` each, newest first; returns
    the bars oldest first. Consecutive chunks can share a bar, so bars are
    keyed by their date."""
    byDate: dict[dt.date | dt.datetime, BarData] = {}
    end: dt.date | dt.datetime | str = ""
    for number in range(1, chunks + 1):
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime=end,
            durationStr=chunk,
            barSizeSetting=barSize,
            whatToShow=what,
            useRTH=useRTH,
        )
        if not bars:
            log.info("no bars before %s; stopping", end or "now")
            break
        log.info(
            "chunk %d/%d: %d bars from %s to %s",
            number,
            chunks,
            len(bars),
            bars[0].date,
            bars[-1].date,
        )
        byDate.update((bar.date, bar) for bar in bars)
        end = bars[0].date
        if number < chunks:
            await asyncio.sleep(pause)
    return [byDate[date] for date in sorted(byDate)]


async def main(args: argparse.Namespace) -> int:
    with IB() as ib:
        await ib.connectAsync(args.host, args.port, clientId=args.client_id)
        contract = await qualify(ib, Stock(args.symbol, args.exchange, args.currency))
        if contract is None:
            log.error("%s is not a unique stock on %s", args.symbol, args.exchange)
            return 1
        bars = await downloadBars(
            ib,
            contract,
            barSize=args.bar_size,
            chunk=args.chunk,
            chunks=args.chunks,
            what=args.what,
            useRTH=not args.all_hours,
            pause=args.pause,
        )
    if not bars:
        log.error("the server returned no bars for %s", args.symbol)
        return 1
    frame = util.df(bars)
    frame.write_parquet(args.out)
    log.info("wrote %d bars to %s", frame.height, args.out)
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    try:
        sys.exit(asyncio.run(main(parseArgs())))
    except KeyboardInterrupt:
        sys.exit(130)
