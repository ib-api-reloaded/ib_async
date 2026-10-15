import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import logging
    import time

    import marimo as mo

    import ib_async
    from ib_async import CFD, IB, Bond, Contract, Forex, Future, Option, Stock, util

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 10


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Basics

    Connecting, the current state, contracts, requests and logging.

    First, what the `ib_async` package exports:
    """)
    return


@app.cell
def _():
    ib_async.__all__
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Importing

    The setup cell at the top of the notebook imports, by name, everything
    the notebook uses (`from ib_async import IB, Stock, ...`), so each name
    can be traced to where it comes from. It also holds the connection
    settings `HOST`, `PORT` and `CLIENT_ID`.

    The legacy Jupyter notebooks called `util.startLoop()` here. That
    patched the event loop so that the synchronous API, which runs its own
    loop until a request finishes, could be used inside a notebook. marimo
    runs cells inside a running event loop and lets a cell `await`, so the
    notebooks use the async API instead (`await ib.connectAsync(...)`,
    `await ib.reqContractDetailsAsync(...)`) and need no patching. The same
    code works unchanged in an async program.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Connecting

    The main class of the package is `IB`. Create an instance and connect it
    to a running TWS or IB Gateway:
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
    If the connection fails, check that the API is enabled in TWS or IB
    Gateway and that `HOST` and `PORT` are right (TWS paper trading listens
    on 7497, IB Gateway paper trading on 4002), and that no other client is
    connected with the same `CLIENT_ID`.

    Once connected, `ib` is synchronized with TWS: positions, open and
    completed orders, account values and executions were fetched while
    connecting. This "current state" is available immediately from methods
    such as `ib.positions()`, `ib.trades()`, `ib.openTrades()`,
    `ib.accountValues()` and `ib.tickers()`. The current positions:
    """)
    return


@app.cell
def _(ib):
    ib.positions()
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Or the account values filtered down to the net liquidation value in the
    base currency. `value` is the string TWS sends; `decimalValue` is the
    same amount as a `Decimal` (or `None` for a tag that is not an amount):
    """)
    return


@app.cell
def _(ib):
    [
        _v
        for _v in ib.accountValues()
        if _v.tag == "NetLiquidationByCurrency" and _v.currency == "BASE"
    ]
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The current state is kept in sync with TWS as long as the connection
    lasts: a fill is added as soon as it is reported, and account values
    are updated as soon as they change in TWS.

    ## Contracts

    A contract can be specified in different ways:

    * by creating an empty `Contract` and setting its attributes one
      by one;
    * with `Contract`, giving the attributes as keyword arguments;
    * with one of the specialized classes `Stock`, `Option`, `Future`,
      `Forex`, `Index`, `CFD`, `Commodity`, `Bond`, `FuturesOption`,
      `MutualFund`, `Warrant` or `Crypto`.

    Some examples (creating a contract does not contact TWS):
    """)
    return


@app.cell
def _():
    [
        Contract(conId=270639),
        Stock("AMD", "SMART", "USD"),
        Stock("INTC", "SMART", "USD", primaryExchange="NASDAQ"),
        Forex("EURUSD"),
        CFD("IBUS30"),
        Future("ES", "20180921", "GLOBEX"),
        Option("SPY", "20170721", 240, "C", "SMART"),
        Bond(secIdType="ISIN", secId="US03076KAA60"),
    ]
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Sending a request

    `IB` has a method for nearly every request of the IB API. A request
    that returns a result has an async variant, named with an `Async`
    suffix, that is awaited for the result. For example
    `reqContractDetailsAsync`:
    """)
    return


@app.cell
async def _(ib):
    _contract = Stock("TSLA", "SMART", "USD")
    await ib.reqContractDetailsAsync(_contract)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Current state vs request

    A request makes a round trip to TWS and can take a noticeable time; the
    current state is always available immediately. So prefer the current
    state methods over requests: `ib.openOrders()` over
    `ib.reqOpenOrdersAsync()`, `ib.positions()` over
    `ib.reqPositionsAsync()`, and so on. Timing both for the positions:
    """)
    return


@app.cell
async def _(ib):
    _start = time.perf_counter()
    _current = ib.positions()
    _currentSeconds = time.perf_counter() - _start

    _start = time.perf_counter()
    _requested = await ib.reqPositionsAsync()
    _requestedSeconds = time.perf_counter() - _start

    mo.md(f"""
    | Call | Time | Positions |
    |---|---|---|
    | `ib.positions()` | {_currentSeconds * 1000:.3f} ms | {len(_current)} |
    | `await ib.reqPositionsAsync()` | {_requestedSeconds * 1000:.3f} ms | {len(_requested)} |
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Logging

    `util.logToConsole()` prints the log messages of `ib_async` at level
    `INFO` and higher to stderr; marimo shows a cell's stderr in the console
    output under it. Passing `logging.DEBUG` shows all debug messages too,
    including the network traffic. That is a lot of output, so here it is
    behind a switch:
    """)
    return


@app.cell
def _():
    debug = mo.ui.switch(label="Debug messages")
    debug
    return (debug,)


@app.cell
def _(debug):
    util.logToConsole(logging.DEBUG if debug.value else logging.INFO)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Disconnecting

    `ib.disconnect()` closes the connection and clears all of the state of
    `ib`. This notebook has no cell for it: re-running the connection cell
    or stopping the notebook releases the connection. In a program,
    `with IB() as ib:` disconnects however the program ends.
    """)
    return


if __name__ == "__main__":
    app.run()
