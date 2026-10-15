import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import asyncio
    import contextlib
    import itertools

    import marimo as mo

    from ib_async import IB, Forex, util

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 16


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Market depth (order book)

    The exchanges that offer market depth, and a live order book.

    Every request uses the async API: marimo runs cells inside a running
    event loop, so there is no `util.startLoop()`. The streaming cell runs
    for a bounded time and cancels its subscription when it ends.
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
    The exchanges that support market depth data, the first five:
    """)
    return


@app.cell
async def _(ib):
    exchanges = await ib.reqMktDepthExchangesAsync()
    util.df(exchanges[:5])
    return (exchanges,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The contract for the order book, EURUSD:
    """)
    return


@app.cell
async def _(ib):
    eurusd = Forex("EURUSD")
    await ib.qualifyContractsAsync(eurusd)
    eurusd
    return (eurusd,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    `reqMktDepth` subscribes to the order book and returns the `Ticker` that
    holds it: `ticker.domBids` and `ticker.domAsks` are the levels of each
    side, best price first, each a `DOMLevel` with `price`, `size` and
    `marketMaker`. Every change to the book emits `ticker.updateEvent`.

    This cell shows the top five levels as a table, one row per level, on
    every update for 15 seconds, then cancels the subscription:
    """)
    return


@app.cell
async def _(eurusd, ib):
    _ticker = ib.reqMktDepth(eurusd, numRows=5)
    try:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(15):
                async for _updated in _ticker.updateEvent:
                    _book = [
                        {
                            "bidSize": bid.size if bid else None,
                            "bidPrice": bid.price if bid else None,
                            "askPrice": ask.price if ask else None,
                            "askSize": ask.size if ask else None,
                        }
                        for bid, ask in itertools.zip_longest(
                            _updated.domBids[:5], _updated.domAsks[:5]
                        )
                    ]
                    mo.output.replace(util.df(_book))
    finally:
        ib.cancelMktDepth(eurusd)
    return


if __name__ == "__main__":
    app.run()
