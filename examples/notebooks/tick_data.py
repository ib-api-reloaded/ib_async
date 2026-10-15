import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import asyncio
    import contextlib
    import datetime

    import marimo as mo

    from ib_async import IB, Forex, util

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 15


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Tick data

    Streaming ticks, tick-by-tick data and historical ticks. Run it while
    the Forex market is open, or the streaming cells have nothing to show.

    Every request uses the async API: marimo runs cells inside a running
    event loop, so there is no `util.startLoop()`. Streaming cells run for
    a bounded time and cancel their subscriptions when they end.
    """)
    return


@app.cell
async def _():
    # Re-running this cell, or stopping the notebook, releases the previous
    # connection.
    ib = IB()
    await ib.connectAsync(HOST, PORT, clientId=CLIENT_ID)
    ib
    return (ib,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Streaming tick data

    Some Forex contracts, qualified so they carry their contract ids:
    """)
    return


@app.cell
async def _(ib):
    contracts = [
        Forex(pair)
        for pair in ("EURUSD", "USDJPY", "GBPUSD", "USDCHF", "USDCAD", "AUDUSD")
    ]
    await ib.qualifyContractsAsync(*contracts)
    eurusd = contracts[0]
    contracts
    return contracts, eurusd


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    `reqMktData` subscribes to streaming ticks and returns the `Ticker` that
    holds them. The ticker starts empty, fills within a couple of seconds
    and then keeps updating, emitting `ticker.updateEvent` on every change.
    This cell shows the EURUSD ticker on every update for 10 seconds, then
    cancels the subscription:
    """)
    return


@app.cell
async def _(eurusd, ib):
    ticker = ib.reqMktData(eurusd)
    try:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(10):
                async for _ticker in ticker.updateEvent:
                    mo.output.replace(_ticker)
    finally:
        ib.cancelMktData(eurusd)
    return (ticker,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Forex quotes have no trades, so `last` stays `None`. For a price use
    `midpoint()`, the average of bid and ask, or `marketPrice()`, which is
    the last price when it lies within the bid and ask and the midpoint
    otherwise. Here as the subscription above left the ticker:
    """)
    return


@app.cell
def _(ticker):
    {
        "last": ticker.last,
        "midpoint": ticker.midpoint(),
        "marketPrice": ticker.marketPrice(),
    }
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    `ib.pendingTickersEvent` emits the set of tickers that changed in the
    last batch of messages from TWS. This cell subscribes to all the pairs
    and redraws a table, one row per pair, on every change for 30 seconds,
    then cancels the subscriptions:
    """)
    return


@app.cell
async def _(contracts, ib):
    for _contract in contracts:
        ib.reqMktData(_contract)
    _quotes = {}
    try:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(30):
                async for _tickers in ib.pendingTickersEvent:
                    for _t in _tickers:
                        _quotes[_t.contract.pair()] = {
                            "pair": _t.contract.pair(),
                            "bidSize": _t.bidSize,
                            "bid": _t.bid,
                            "ask": _t.ask,
                            "askSize": _t.askSize,
                            "high": _t.high,
                            "low": _t.low,
                            "close": _t.close,
                        }
                    mo.output.replace(util.df(_quotes.values()))
    finally:
        for _contract in contracts:
            ib.cancelMktData(_contract)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Besides its latest values, each pending ticker holds the ticks that
    just arrived in `ticker.ticks`, a list of `TickData`. The list is
    cleared when the next batch of messages arrives, so read it on the
    update that delivered it.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Tick-by-tick data

    `reqMktData` ticks are sampled by IBKR to save bandwidth, so not every
    tick from the exchange is sent. `reqTickByTickData` sends every tick, as
    it appears in the TWS Time & Sales window. IBKR allows only a few
    simultaneous tick-by-tick subscriptions (as few as three), and each tick
    type of a contract (`"BidAsk"`, `"Last"`, ...) takes one.

    The ticks arrive in `ticker.tickByTicks`, cleared on the next batch like
    `ticker.ticks`, and each batch emits `ticker.updateEvent` and
    `ib.pendingTickersEvent`. This cell collects the EURUSD bid-ask ticks
    for 10 seconds, shows the latest ten, then cancels the subscription:
    """)
    return


@app.cell
async def _(eurusd, ib):
    _ticker = ib.reqTickByTickData(eurusd, "BidAsk")
    _ticks = []
    try:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(10):
                async for _updated in _ticker.updateEvent:
                    _ticks.extend(_updated.tickByTicks)
                    mo.output.replace(util.df(_ticks[-10:]))
    finally:
        ib.cancelTickByTickData(eurusd, "BidAsk")
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Historical tick data

    Historical ticks come at most 1000 per request (a few more when needed
    to complete the last second). Give either the start or the end time and
    leave the other empty; here the 1000 bid-ask ticks up to now:
    """)
    return


@app.cell
async def _(eurusd, ib):
    ticks = await ib.reqHistoricalTicksAsync(
        eurusd,
        startDateTime="",
        endDateTime=datetime.datetime.now(datetime.UTC),
        numberOfTicks=1000,
        whatToShow="BID_ASK",
        useRth=False,
    )
    util.df(ticks)
    return (ticks,)


if __name__ == "__main__":
    app.run()
