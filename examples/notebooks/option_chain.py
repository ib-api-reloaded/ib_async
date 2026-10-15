import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import marimo as mo

    from ib_async import IB, Future, FuturesOption, Index, Option, util

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 12


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Option chains

    Suppose we want the options on the SPX index that meet these
    conditions:

    * the next three monthly expiries;
    * strike prices within 20 dollars of the current SPX value;
    * strike prices that are a multiple of 5 dollars.
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
    For the current market value, first create and qualify a contract for
    the underlying, the S&P 500 index. Qualifying fills in its `conId`,
    which the option chain request below needs:
    """)
    return


@app.cell
async def _(ib):
    spx = Index("SPX", "CBOE")
    await ib.qualifyContractsAsync(spx)
    spx
    return (spx,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    To avoid needing market data permissions, the cell below switches to
    delayed data with `ib.reqMarketDataType(4)`: type 4 is "delayed
    frozen", delayed quotes that keep their last values when the market is
    closed (1 is live, 2 frozen, 3 delayed). The setting applies to every
    market data request that follows on this connection.

    Then it gets a ticker for SPX, a snapshot of its market data. A
    snapshot can take up to 11 seconds.
    """)
    return


@app.cell
async def _(ib, spx):
    ib.reqMarketDataType(4)
    [ticker] = await ib.reqTickersAsync(spx)
    ticker
    return (ticker,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The current market value of the ticker. `marketPrice()` is `None` when
    the snapshot has no last price or bid/ask, so this falls back to the
    previous close:
    """)
    return


@app.cell
def _(ticker):
    spxValue = ticker.marketPrice() or ticker.close
    spxValue
    return (spxValue,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    This request fetches the option chains of SPX:
    """)
    return


@app.cell
async def _(ib, spx):
    chains = await ib.reqSecDefOptParamsAsync(spx.symbol, "", spx.secType, spx.conId)
    util.df(chains)
    return (chains,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The chains differ in `exchange` and `tradingClass`. The trading class is
    SPX for the monthly options and SPXW for the weekly ones. The weekly
    expiries are disjoint from the monthly ones, so for the weekly options
    add the monthly ones as well.

    Here we want only the monthly options trading on SMART:
    """)
    return


@app.cell
def _(chains):
    chain = next(
        _c for _c in chains if _c.tradingClass == "SPX" and _c.exchange == "SMART"
    )
    chain
    return (chain,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The chain is the full matrix of expirations by strikes. From it, build
    every option contract that meets the conditions, and qualify them.
    Not every strike exists for every expiration: `qualifyContractsAsync`
    returns `None` for the ones that do not (and logs a warning for each),
    so they are left out. The number of options found:
    """)
    return


@app.cell
async def _(chain, ib, spxValue):
    _strikes = [
        _strike
        for _strike in chain.strikes
        if _strike % 5 == 0 and spxValue - 20 < _strike < spxValue + 20
    ]
    _expirations = sorted(chain.expirations)[:3]
    _rights = ["P", "C"]

    _candidates = [
        Option("SPX", _expiration, _strike, _right, "SMART", tradingClass="SPX")
        for _right in _rights
        for _expiration in _expirations
        for _strike in _strikes
    ]

    contracts = [
        _c for _c in await ib.qualifyContractsAsync(*_candidates) if _c is not None
    ]
    len(contracts)
    return (contracts,)


@app.cell
def _(contracts):
    contracts[0]
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Now the market data for all the options in one go:
    """)
    return


@app.cell
async def _(contracts, ib):
    _tickers = await ib.reqTickersAsync(*contracts)
    _tickers[0]
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The option greeks are in the ticker's `modelGreeks` attribute (computed
    by IB's option model) and, when there is a bid, ask or last price, also
    in `bidGreeks`, `askGreeks` and `lastGreeks`. For a streaming ticker
    (`ib.reqMktData`) the greeks are kept up to date with the market.
    """)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Futures options

    Options on a future work differently:

    * a future needs its exchange (CME for ES): IBKR does not look it up;
    * the options expiring in a month come in several trading classes
      (quarterly, weekly, end of month), and can be on more than one
      futures month;
    * `reqSecDefOptParams` returns each chain's expirations and strikes as
      two separate lists, many of whose combinations do not exist.

    `reqOptionStrikesAsync` asks contract details instead, and returns the
    strikes each expiration actually lists. First, the front ES future, the
    one expiring first:
    """)
    return


@app.cell
async def _(ib):
    _details = await ib.reqContractDetailsAsync(Future("ES", exchange="CME"))
    es = min(
        (_d.contract for _d in _details if _d.contract),
        key=lambda _c: _c.lastTradeDateOrContractMonth,
    )
    es
    return (es,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The strikes of the options expiring in the future's own month, one row
    per expiration, trading class and underlying future:
    """)
    return


@app.cell
async def _(es, ib):
    esStrikes = await ib.reqOptionStrikesAsync(es, es.lastTradeDateOrContractMonth[:6])
    util.df(esStrikes)
    return (esStrikes,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Keep the quarterly options (trading class ES) on this future, the ones
    whose `underlyingConId` is the future's `conId`, at the five strikes
    nearest the future's price:
    """)
    return


@app.cell
async def _(es, esStrikes, ib):
    ib.reqMarketDataType(4)  # delayed frozen, as for SPX above
    [_ticker] = await ib.reqTickersAsync(es)
    _price = _ticker.marketPrice() or _ticker.close
    esChain = next(
        _c
        for _c in esStrikes
        if _c.underlyingConId == es.conId and _c.tradingClass == "ES"
    )
    esNearest = sorted(esChain.strikes, key=lambda _s: abs(_s - _price))[:5]
    esChain.expiration, sorted(esNearest)
    return esChain, esNearest


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Build those options with their trading class and exchange, and qualify
    them. Without `tradingClass`, a lookup can match several contracts,
    such as a quarterly and a weekly option expiring the same day:
    `returnAll=True` returns those matches as a list in place of a single
    contract, instead of only logging them, so they can be told apart.
    """)
    return


@app.cell
async def _(es, esChain, esNearest, ib):
    _candidates = [
        FuturesOption(
            symbol="ES",
            lastTradeDateOrContractMonth=esChain.expiration,
            strike=_strike,
            right=_right,
            exchange=es.exchange,
            tradingClass=esChain.tradingClass,
        )
        for _strike in sorted(esNearest)
        for _right in ("P", "C")
    ]
    esOptions = await ib.qualifyContractsAsync(*_candidates, returnAll=True)
    esOptions
    return


if __name__ == "__main__":
    app.run()
