import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import asyncio
    import contextlib

    import marimo as mo
    import matplotlib.pyplot as plt
    import polars as pl

    from ib_async import IB, Forex, Stock, util

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 14


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Bar data

    Historical bars, historical bars that keep updating, and realtime bars.

    Every request uses the async API (`await ib.reqHistoricalDataAsync(...)`):
    marimo runs cells inside a running event loop, so there is no
    `util.startLoop()`. Streaming cells run for a bounded time and cancel
    their subscription when they end.
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
    ## Historical data

    The earliest date with bar data available, the "head timestamp":
    """)
    return


@app.cell
async def _(ib):
    tsla = Stock("TSLA", "SMART", "USD")
    await ib.reqHeadTimeStampAsync(tsla, whatToShow="TRADES", useRTH=True, formatDate=1)
    return (tsla,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Hourly bars of the last 60 trading days:
    """)
    return


@app.cell
async def _(ib, tsla):
    bars = await ib.reqHistoricalDataAsync(
        tsla,
        endDateTime="",
        durationStr="60 D",
        barSizeSetting="1 hour",
        whatToShow="TRADES",
        useRTH=True,
    )
    bars[0]
    return (bars,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    As a polars DataFrame, one row per bar. Prices and volumes are `Decimal`
    columns and `date` keeps its time zone:
    """)
    return


@app.cell
def _(bars):
    df = util.df(bars)
    df
    return (df,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The closing prices (matplotlib plots floats, so the `Decimal` column is
    cast for the plot):
    """)
    return


@app.cell
def _(df):
    _fig, _ax = plt.subplots(figsize=(10, 4))
    _ax.plot(df["date"], df["close"].cast(pl.Float64))
    _ax.set_title("TSLA close")
    _fig
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    `util.barplot` draws candlesticks from bars or from their DataFrame;
    here the last 100 bars:
    """)
    return


@app.cell
def _(bars, tsla):
    util.barplot(bars[-100:], title=tsla.symbol)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Historical data that keeps updating

    With `keepUpToDate=True` (and no end date) the bars keep updating: the
    last bar changes, and a new bar is added when its time comes. Each
    update emits `updateEvent(bars, hasNewBar)`. This cell redraws the chart
    on every update for 30 seconds, then cancels the subscription.
    """)
    return


@app.cell
async def _(ib):
    eurusd = Forex("EURUSD")
    live = await ib.reqHistoricalDataAsync(
        eurusd,
        endDateTime="",
        durationStr="900 S",
        barSizeSetting="10 secs",
        whatToShow="MIDPOINT",
        useRTH=True,
        keepUpToDate=True,
    )
    try:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(30):
                async for _bars, _hasNewBar in live.updateEvent:
                    _fig = util.barplot(live, title="EURUSD, updating")
                    mo.output.replace(_fig)
                    plt.close(_fig)
    finally:
        ib.cancelHistoricalData(live)
    return (eurusd,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Realtime bars

    `reqRealTimeBars` sends a new 5-second bar every 5 seconds. After a
    network interruption it backfills the bars it missed and resumes, which
    makes it the sturdier choice for a long-running subscription. This cell
    shows the latest bars for 30 seconds, then cancels them.
    """)
    return


@app.cell
async def _(eurusd, ib):
    realtime = ib.reqRealTimeBars(eurusd, 5, "MIDPOINT", False)
    try:
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(30):
                async for _bars, _hasNewBar in realtime.updateEvent:
                    mo.output.replace(util.df(realtime[-10:]))
    finally:
        ib.cancelRealTimeBars(realtime)
    return


if __name__ == "__main__":
    app.run()
