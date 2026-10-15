# Examples

Working examples of `ib_async`, from complete programs to interactive
exploration. All of them need a running TWS or IB Gateway with the API
enabled; use a paper trading account.

| Directory                        | What it is                                           | Use it to                                        |
| -------------------------------- | ---------------------------------------------------- | ------------------------------------------------ |
| [`programs/`](programs/)         | Complete, typed, async command-line programs         | Build a system: start from one of these          |
| [`notebooks/`](notebooks/)       | [marimo](https://marimo.io) notebooks, one per topic | Explore the API and your data interactively      |
| [`gui/`](gui/)                   | Qt and Tk desktop integrations                       | Embed `ib_async` in a GUI event loop             |
| [`../notebooks/`](../notebooks/) | The legacy Jupyter notebooks                         | Compare with the old style; they will be removed |

Notebooks are for looking around: trying a request, inspecting what comes
back, plotting it. Anything that should keep running, be tested or be
deployed belongs in a program, structured like the ones in `programs/`.

## Running them

From a checkout of this repository:

```
uv sync --group examples

# a program
uv run --group examples examples/programs/download_bars.py --help

# a notebook, in the browser
uv run --group examples marimo edit examples/notebooks/bar_data.py
```

Each program takes `--host`, `--port` and `--client-id`; each notebook sets
`HOST`, `PORT` and `CLIENT_ID` in its setup cell. The defaults connect to
TWS paper trading on `127.0.0.1:7497`; IB Gateway paper trading listens on
`4002`.

## What changed from the legacy notebooks

Each notebook in `notebooks/` has a legacy counterpart with the same name in
[`../notebooks/`](../notebooks/), so the two can be read side by side.

- **Async API.** Every request is `await ib.reqXxxAsync(...)`. marimo runs
  cells inside a running event loop, so the synchronous API (which runs
  its own loop) is not used and `util.startLoop()` (which patches the loop
  to allow that) is gone. Programs use the same async API, so code moves
  from a notebook to a program unchanged.
- **Plain Python files.** A marimo notebook is a `.py` file: it diffs and
  reviews like code, and `make examples-check` lints it, checks its cell
  structure and checks that every cell's inputs are defined, in CI.
- **No stored outputs.** Outputs are produced when the notebook runs, so
  there are no stale results in the repository.
- **No hidden state.** marimo re-runs the cells that depend on a changed
  cell, so the notebook always matches its code, whatever order cells were
  edited in.
- **Bounded streaming.** Live data (ticks, bars, market depth) is consumed
  by iterating the event (`async for ... in ticker.updateEvent`) for a set
  time, with the subscription cancelled in `finally`, instead of
  `clear_output()` loops and handlers left connected.
- **polars.** Tables are polars DataFrames from `util.df()`.

## Conventions

New examples follow these, so the set stays consistent.

### Notebooks (`notebooks/`)

- One topic per notebook, named like its legacy counterpart if it has one.
- `app = marimo.App(width="medium")`.
- A setup cell (`with app.setup:`) holds every import and the connection
  settings `HOST`, `PORT`, `CLIENT_ID` (each notebook its own client id).
  Imports are explicit: no `from ib_async import *`.
- Prose is in `mo.md(...)` cells with `hide_code=True`.
- One cell connects: `ib = IB()` then `await ib.connectAsync(HOST, PORT,
clientId=CLIENT_ID)`. There is no disconnect cell: cells run in
  dependency order, not file order, so a disconnect cell could run before
  the cells that use the connection. Re-running the connection cell or
  stopping the notebook releases the connection.
- Requests use the async API. Calls that only start a subscription
  (`reqMktData`, `reqMktDepth`, `reqRealTimeBars`, `placeOrder`,
  `cancelOrder`) return immediately and are called directly.
- A cell shows its result as its last expression. Cell-local names start
  with `_`; every other name is defined by exactly one cell.
- Streaming cells iterate the event inside
  `contextlib.suppress(TimeoutError)` and `asyncio.timeout(seconds)`,
  replace their output with `mo.output.replace(...)` on each update, and
  cancel the subscription in `finally`.
- Plots are matplotlib figures returned as the cell's last expression;
  `Decimal` columns are cast to `pl.Float64` for plotting.

### Programs (`programs/`)

- One self-contained file per program, runnable as a script, with a module
  docstring that says what it does and how to run it.
- `argparse` for options, including `--host`, `--port` and `--client-id`;
  `--help` never connects.
- `async def main(args) -> int`, run with `asyncio.run(...)`; the exit code
  says whether it worked.
- `with IB() as ib:` so the connection closes however the program ends,
  including Ctrl-C.
- Logging through `logging`, not `print`, for anything but the program's
  output.
- Fully typed: `make examples-check` runs mypy on them.
- The work is in small async functions that take the `IB` instance, so
  they can be tested without a server: a stand-in returns prepared results
  and emits events by hand. `tests/test_examples_programs.py` does this for
  every program.
- Anything that places orders does nothing irreversible without an
  explicit flag.

### Checks

```
make examples-check
```

runs ruff, mypy on the programs, `marimo check`, `scripts/check_marimo.py`
(every cell input is defined by some cell) and each program's `--help`.
Nothing in it connects to TWS or IB Gateway, so it runs in CI.
