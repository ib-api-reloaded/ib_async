import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import marimo as mo

    from ib_async import IB, Contract, Forex, Stock, util

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 11


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Contract details

    Looking up contracts: contract details, qualifying contracts, and
    searching for symbols.
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
    Suppose we want the contract details of AMD stock. Create a stock
    contract with only the symbol and request the details for it; the
    number of contracts that match:
    """)
    return


@app.cell
async def _(ib):
    cds = await ib.reqContractDetailsAsync(Stock("AMD"))
    len(cds)
    return (cds,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    A long list of contract details. The first one:
    """)
    return


@app.cell
def _(cds):
    cds[0]
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The contract itself is the `contract` attribute of the contract details.
    The list of contracts, and the first one:
    """)
    return


@app.cell
def _(cds):
    contracts = [_cd.contract for _cd in cds]
    contracts[0]
    return (contracts,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The differences between the contracts are easier to spot in a table;
    `util.df` makes a polars DataFrame with one row per contract:
    """)
    return


@app.cell
def _(contracts):
    util.df(contracts)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    AMD trades in different currencies on different exchanges. With the
    exchange SMART and the currency USD the contract becomes unique: one
    match.
    """)
    return


@app.cell
async def _(ib):
    len(await ib.reqContractDetailsAsync(Stock("AMD", "SMART", "USD")))
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The same for Intel:
    """)
    return


@app.cell
async def _(ib):
    intc = Stock("INTC", "SMART", "USD")
    len(await ib.reqContractDetailsAsync(intc))
    return (intc,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    A contract that does not exist has no matches (and TWS reports an
    error, which is logged):
    """)
    return


@app.cell
async def _(ib):
    xxx = Stock("XXX", "SMART", "USD")
    len(await ib.reqContractDetailsAsync(xxx))
    return (xxx,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    A Forex pair:
    """)
    return


@app.cell
async def _(ib):
    eurusd = Forex("EURUSD")
    len(await ib.reqContractDetailsAsync(eurusd))
    return (eurusd,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Qualifying contracts

    `qualifyContractsAsync` requests the contract details and fills the
    contracts it is given in with what comes back, such as the `conId`.
    The AMD contract before and after:
    """)
    return


@app.cell
async def _(ib):
    amd = Stock("AMD", "SMART", "USD")
    _before = repr(amd)
    await ib.qualifyContractsAsync(amd)
    mo.md(f"""
    Before:

    ```python
    {_before}
    ```

    After:

    ```python
    {amd!r}
    ```
    """)
    return (amd,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    **Tip:** the printed form of a contract is valid Python, so it can be
    copied into code.

    The `conId` alone specifies a contract uniquely. Qualifying a contract
    that has only the `conId` gives the same contract as AMD above:
    """)
    return


@app.cell
async def _(amd, ib):
    _byConId = Contract(conId=4391)
    await ib.qualifyContractsAsync(_byConId)
    _byConId == amd
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Many contracts can be qualified at once. The result is aligned with
    the input: each position holds the qualified contract, or `None` where
    the contract could not be qualified (it does not exist, or it is
    ambiguous). Here XXX, the third, is `None`; keep only the qualified
    ones with `[c for c in result if c is not None]`.
    """)
    return


@app.cell
async def _(amd, eurusd, ib, intc, xxx):
    qualContracts = await ib.qualifyContractsAsync(amd, intc, xxx, eurusd)
    qualContracts
    return (qualContracts,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Matching symbols

    There is also an API request for the stocks whose symbol or name
    matches a pattern:
    """)
    return


@app.cell
async def _(ib):
    matches = await ib.reqMatchingSymbolsAsync("intc")
    matches
    return (matches,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The qualified Intel contract from above (`qualContracts[1]`) is one of
    the matches:
    """)
    return


@app.cell
def _(matches, qualContracts):
    _matchContracts = [_m.contract for _m in matches or []]
    qualContracts[1] in _matchContracts
    return


if __name__ == "__main__":
    app.run()
