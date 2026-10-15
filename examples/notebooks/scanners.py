import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import dataclasses
    import xml.etree.ElementTree as ET
    from decimal import Decimal

    import marimo as mo

    from ib_async import IB, ScannerSubscription, TagValue, util

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 17


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Scanners

    Market scanners rank instruments by a criterion, such as the biggest
    percentage gain today, and return the top results. Any scan the TWS
    "Advanced Market Scanner" can do can be done through the API.
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
    ## Basic scanner

    To scan, create a `ScannerSubscription` and pass it to
    `reqScannerDataAsync`. Every scan needs at least these three fields:
    `instrument` (the what), `locationCode` (the where) and `scanCode` (the
    ranking).

    For example, the top ranked US stocks by percentage gain:
    """)
    return


@app.cell
async def _(ib):
    sub = ScannerSubscription(
        instrument="STK", locationCode="STK.US.MAJOR", scanCode="TOP_PERC_GAIN"
    )
    scanData = await ib.reqScannerDataAsync(sub)
    mo.vstack([mo.md(f"{len(scanData)} results, the first one:"), scanData[0]])
    return scanData, sub


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    `reqScannerDataAsync` starts a scanner subscription and cancels it once
    the results are in; an error 162 that TWS sends about the cancelled
    subscription can be ignored.

    Each result is a `ScanData` with a rank and the contract details of an
    instrument, without market data (request that separately). This helper
    shows results as a table, one row per result:
    """)
    return


@app.cell
def _():
    def scanTable(results):
        """A polars DataFrame with the rank and contract of each scan result."""
        return util.df(
            [
                {
                    "rank": sd.rank,
                    "symbol": sd.contractDetails.contract.symbol,
                    "secType": sd.contractDetails.contract.secType,
                    "currency": sd.contractDetails.contract.currency,
                    "conId": sd.contractDetails.contract.conId,
                    "marketName": sd.contractDetails.marketName,
                }
                for sd in results
            ]
        )

    return (scanTable,)


@app.cell
def _(scanData, scanTable):
    scanTable(scanData)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Filtering, the old way

    `ScannerSubscription` has fields that filter the results, such as
    `abovePrice`, `aboveVolume`, `marketCapBelow` or `spRatingAbove`. Unset
    filters are `None`; the price and market cap filters are `Decimal`.

    For example, the same scan for stocks priced above 200 dollars (a
    changed copy of `sub`, since a marimo cell should not modify another
    cell's objects):
    """)
    return


@app.cell
async def _(ib, scanTable, sub):
    _priceSub = dataclasses.replace(sub, abovePrice=Decimal(200))
    _scanData = await ib.reqScannerDataAsync(_priceSub)
    scanTable(_scanData)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Filtering, the new way

    The new way has a vast number of filters. They map directly to the
    options of the TWS "Advanced Market Scanner", and are listed in a large
    XML document that `reqScannerParametersAsync` returns:
    """)
    return


@app.cell
async def _(ib):
    parametersXml = await ib.reqScannerParametersAsync()
    _data = parametersXml.encode()
    mo.vstack(
        [
            mo.md(f"{len(_data):,} bytes"),
            mo.download(
                _data,
                filename="scanner_parameters.xml",
                mimetype="application/xml",
                label="Download scanner_parameters.xml",
            ),
        ]
    )
    return (parametersXml,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Download it to read it in a browser or an editor. Parsed with
    `xml.etree.ElementTree`, these are the tags available for filtering:
    """)
    return


@app.cell
def _(parametersXml):
    root = ET.fromstring(parametersXml)
    _tags = [elem.text for elem in root.findall(".//AbstractField/code")]
    mo.vstack([mo.md(f"{len(_tags)} tags:"), _tags])
    return (root,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Notice how `abovePrice` is now called `priceAbove`.

    Using three of these tags, the US stocks that went up more than 20% and
    trade between 5 and 50 dollars, sorted by percentage gain (the same
    `sub`). The filters are `TagValue`s, whose values are strings, passed as
    `scannerSubscriptionFilterOptions`; the other list,
    `scannerSubscriptionOptions`, is undocumented by IBKR and stays empty:
    """)
    return


@app.cell
async def _(ib, scanTable, sub):
    _tagValues = [
        TagValue("changePercAbove", "20"),
        TagValue("priceAbove", "5"),
        TagValue("priceBelow", "50"),
    ]
    _scanData = await ib.reqScannerDataAsync(
        sub, scannerSubscriptionFilterOptions=_tagValues
    )
    scanTable(_scanData)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The `scanCode` values are those of the "Parameter" window of the TWS
    "Advanced Market Scanner". The ones starting with "TOP":
    """)
    return


@app.cell
def _(root):
    _scanCodes = [e.text for e in root.findall(".//scanCode")]
    mo.vstack(
        [
            mo.md(f'{len(_scanCodes)} scan codes, the ones starting with "TOP":'),
            [sc for sc in _scanCodes if sc and sc.startswith("TOP")],
        ]
    )
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Scans are not limited to stocks. The instrument types:
    """)
    return


@app.cell
def _(root):
    sorted({e.text for e in root.findall(".//Instrument/type") if e.text})
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    And the location codes:
    """)
    return


@app.cell
def _(root):
    [e.text for e in root.findall(".//locationCode")]
    return


if __name__ == "__main__":
    app.run()
