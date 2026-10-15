import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import asyncio
    import contextlib
    import time
    from decimal import Decimal

    import marimo as mo

    from ib_async import IB, Forex, LimitOrder, MarketOrder

    # TWS paper trading listens on 7497, IB Gateway paper trading on 4002.
    HOST = "127.0.0.1"
    PORT = 7497
    CLIENT_ID = 13


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    # Ordering

    Placing, modifying and cancelling orders, waiting for an order to
    finish, and previewing an order without placing it.

    /// danger | Warning: this notebook places real orders

    Use a paper trading account, during market hours.
    ///

    Every step that places, modifies or cancels an order runs only when you
    click its button. Opening the notebook, running it as an app
    (`marimo run`) or as a script places no orders: the cells that follow
    an order (its log, its status) wait until that order exists.
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
    The contract: EURUSD on IDEALPRO. `qualifyContractsAsync` fills in its
    details (such as `conId`) in place and returns a list aligned with its
    arguments, with `None` for a contract it could not qualify:
    """)
    return


@app.cell
async def _(ib):
    contract = Forex("EURUSD")
    _qualified = await ib.qualifyContractsAsync(contract)
    mo.stop(
        _qualified[0] is None,
        mo.md("**EURUSD could not be qualified**; the log says why."),
    )
    contract
    return (contract,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Placing an order

    `placeOrder` sends the order and returns a `Trade` right away, without
    waiting for anything to happen to the order. This is a limit order to
    sell 20,000 EUR at 1.11 USD or better; with EURUSD above 1.11 it fills
    at once. Each click places a new order.
    """)
    return


@app.cell
def _():
    sellButton = mo.ui.run_button(kind="danger", label="Place the SELL limit order")
    sellButton
    return (sellButton,)


@app.cell
def _(contract, ib, sellButton):
    mo.stop(
        not sellButton.value,
        mo.md("Click **Place the SELL limit order** to place it."),
    )
    order = LimitOrder("SELL", 20000, 1.11)
    trade = ib.placeOrder(contract, order)
    trade
    return order, trade


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    `trade` holds the order and everything that happens to it: its status,
    its fills and a log. ib_async updates it with every status change and
    fill. Its log a second later:
    """)
    return


@app.cell
async def _(trade):
    await asyncio.sleep(1)
    trade.log
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The trade is one of `ib.trades()`, the trades of this session:
    """)
    return


@app.cell
def _(ib, trade):
    trade in ib.trades()
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Likewise its order is one of `ib.orders()`:
    """)
    return


@app.cell
def _(ib, order):
    order in ib.orders()
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## An order that stays open

    A limit order to buy at an unrealistic price, 0.05 USD per EUR, stays
    open until it is cancelled:
    """)
    return


@app.cell
def _():
    limitButton = mo.ui.run_button(
        kind="danger", label="Place the BUY limit order at 0.05"
    )
    limitButton
    return (limitButton,)


@app.cell
def _(contract, ib, limitButton):
    mo.stop(
        not limitButton.value,
        mo.md("Click **Place the BUY limit order at 0.05** to place it."),
    )
    limitOrder = LimitOrder("BUY", 20000, 0.05)
    limitTrade = ib.placeOrder(contract, limitOrder)
    limitTrade
    return limitOrder, limitTrade


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    Its status starts as `PendingSubmit` and becomes `Submitted` once the
    order is working. A second later:
    """)
    return


@app.cell
async def _(limitTrade):
    await asyncio.sleep(1)
    limitTrade.orderStatus.status
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    An order that is not done (filled or cancelled) is one of
    `ib.openTrades()`:
    """)
    return


@app.cell
def _(ib, limitTrade):
    limitTrade in ib.openTrades()
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Modifying an order

    To modify an order, change it and place it again: `placeOrder` with an
    order that has already been placed modifies it. Here the limit price
    goes up to 0.10 (prices are `Decimal`):
    """)
    return


@app.cell
def _():
    modifyButton = mo.ui.run_button(kind="warn", label="Modify the limit price to 0.10")
    modifyButton
    return (modifyButton,)


@app.cell
def _(contract, ib, limitOrder, modifyButton):
    mo.stop(
        not modifyButton.value,
        mo.md("Click **Modify the limit price to 0.10** to modify the order."),
    )
    limitOrder.lmtPrice = Decimal("0.10")
    ib.placeOrder(contract, limitOrder)
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Cancelling an order

    `cancelOrder` asks TWS to cancel the order: its status becomes
    `PendingCancel`, then `Cancelled`. Its log a second later:
    """)
    return


@app.cell
def _():
    cancelButton = mo.ui.run_button(kind="warn", label="Cancel the BUY limit order")
    cancelButton
    return (cancelButton,)


@app.cell
async def _(cancelButton, ib, limitOrder, limitTrade):
    mo.stop(
        not cancelButton.value,
        mo.md("Click **Cancel the BUY limit order** to cancel it."),
    )
    ib.cancelOrder(limitOrder)
    await asyncio.sleep(1)
    limitTrade.log
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Waiting for an order to finish

    `placeOrder` does not wait for what happens to the order. To wait until
    it is done, filled or cancelled, iterate the trade's `statusEvent` until
    `isDone()`. The timeout stops the wait after 30 seconds; the event also
    ends if the connection drops.

    This places a market order to buy 100 EUR and shows how long it took:
    """)
    return


@app.cell
def _():
    marketButton = mo.ui.run_button(kind="danger", label="Place the BUY market order")
    marketButton
    return (marketButton,)


@app.cell
async def _(contract, ib, marketButton):
    mo.stop(
        not marketButton.value,
        mo.md("Click **Place the BUY market order** to place it."),
    )
    _start = time.perf_counter()
    marketTrade = ib.placeOrder(contract, MarketOrder("BUY", 100))
    with contextlib.suppress(TimeoutError):
        async with asyncio.timeout(30):
            async for _trade in marketTrade.statusEvent:
                if _trade.isDone():
                    break
    mo.vstack(
        [
            mo.md(
                f"**{marketTrade.orderStatus.status}** after "
                f"{time.perf_counter() - _start:.1f} seconds"
            ),
            marketTrade,
        ]
    )
    return (marketTrade,)


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Positions and commissions

    The positions of all accounts (re-run the cell after an order fills to
    include it):
    """)
    return


@app.cell
def _(ib):
    ib.positions()
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    The commissions paid today: `ib.fills()` holds the fills of this session
    and the executions TWS reported at connect, each with its
    `commissionReport`. Its `commissionAndFees` (called `commission` before
    ib_async 3.0) is a `Decimal` in the report's `currency`, and `None`
    until the report arrives:
    """)
    return


@app.cell
def _(ib):
    _commissions = [fill.commissionReport.commissionAndFees for fill in ib.fills()]
    sum((c for c in _commissions if c is not None), Decimal(0))
    return


@app.cell(hide_code=True)
def _():
    mo.md(r"""
    ## Previewing an order

    `whatIfOrderAsync` returns the commission and the margin impact of an
    order without placing it, so it needs no button. The answer is an
    `OrderState`; if the broker refuses the preview, its `whatIfRefused` is
    `True` and `whatIfErrorString` says why.
    """)
    return


@app.cell
async def _(contract, ib):
    await ib.whatIfOrderAsync(contract, MarketOrder("SELL", 20000))
    return


if __name__ == "__main__":
    app.run()
