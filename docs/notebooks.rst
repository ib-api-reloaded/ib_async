.. _notebooks:

Examples and notebooks
======================

The repository's `examples <https://github.com/ib-api-reloaded/ib_async/tree/main/examples>`__
directory holds working examples, from complete programs to interactive
notebooks. Its `README <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/README.md>`__
explains how to run them and the conventions they follow.

Programs
--------

Complete, typed, async command-line programs: the starting point for
building a system. Each runs as a script, closes its connection however it
ends, and has its logic tested without a server.

* `download_bars.py <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/programs/download_bars.py>`_:
  historical bars, requested in chunks with pacing, written to Parquet.
* `stream_quotes.py <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/programs/stream_quotes.py>`_:
  live quotes until stopped, stopping cleanly if the connection drops.
* `order_lifecycle.py <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/programs/order_lifecycle.py>`_:
  a what-if check, and with ``--place`` an order placed and cancelled.

Notebooks
---------

`marimo <https://marimo.io>`_ notebooks for exploring the API and your
data. They are plain Python files using the async API; open one with
``uv run --group examples marimo edit examples/notebooks/<name>.py``.

* `Basics <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/basics.py>`__
* `Contract details <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/contract_details.py>`__
* `Option chain <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/option_chain.py>`__
* `Bar data <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/bar_data.py>`__
* `Tick data <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/tick_data.py>`__
* `Market depth <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/market_depth.py>`__
* `Ordering <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/ordering.py>`__
* `Scanners <https://github.com/ib-api-reloaded/ib_async/blob/main/examples/notebooks/scanners.py>`__

Legacy Jupyter notebooks
------------------------

The original Jupyter notebooks, kept for comparison with their marimo
versions above. They use the synchronous API with ``util.startLoop()``,
their outputs are from 2019, and they will be removed.

* `Basics <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/basics.ipynb>`__
* `Contract details <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/contract_details.ipynb>`__
* `Option chain <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/option_chain.ipynb>`__
* `Bar data <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/bar_data.ipynb>`__
* `Tick data <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/tick_data.ipynb>`__
* `Market depth <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/market_depth.ipynb>`__
* `Ordering <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/ordering.ipynb>`__
* `Scanners <https://nbviewer.jupyter.org/github/ib-api-reloaded/ib_async/tree/main/notebooks/scanners.ipynb>`__
