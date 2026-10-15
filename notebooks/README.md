# Legacy Jupyter notebooks

These are the original `ib_insync` notebooks, kept for comparison while
their replacements settle in. Their current versions are the marimo
notebooks in [`examples/notebooks/`](../examples/notebooks/), one per topic
with the same name:

| Legacy notebook          | Current version                          |
| ------------------------ | ---------------------------------------- |
| `basics.ipynb`           | `examples/notebooks/basics.py`           |
| `contract_details.ipynb` | `examples/notebooks/contract_details.py` |
| `option_chain.ipynb`     | `examples/notebooks/option_chain.py`     |
| `bar_data.ipynb`         | `examples/notebooks/bar_data.py`         |
| `tick_data.ipynb`        | `examples/notebooks/tick_data.py`        |
| `market_depth.ipynb`     | `examples/notebooks/market_depth.py`     |
| `ordering.ipynb`         | `examples/notebooks/ordering.py`         |
| `scanners.ipynb`         | `examples/notebooks/scanners.py`         |

What changed between the two, and why, is in
[`examples/README.md`](../examples/README.md). In short: these notebooks
use the synchronous API, which inside Jupyter needs `util.startLoop()` to
patch the running event loop; their saved outputs are from 2019 and are
not regenerated; and as JSON files they are not linted, type-checked or
reviewed like code. They are not maintained and will be removed.
