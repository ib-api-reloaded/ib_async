[![Build](https://github.com/ib-api-reloaded/ib_async/actions/workflows/test.yml/badge.svg?branch=next)](https://github.com/ib-api-reloaded/ib_async/actions) [![PyVersion](https://img.shields.io/badge/python-3.10+-blue.svg)](#) <!-- [![Status](https://img.shields.io/badge/status-beta-green.svg)](#) --> [![PyPiVersion](https://img.shields.io/pypi/v/ib_async.svg)](https://pypi.python.org/pypi/ib_async) [![License](https://img.shields.io/badge/license-BSD-blue.svg)](#) <!-- [![Downloads](https://static.pepy.tech/badge/ib-insync)](https://pepy.tech/project/ib-insync) --> [![Docs](https://img.shields.io/badge/Documentation-green.svg)](https://ib-api-reloaded.github.io/ib_async/)

# ib_async

## Update

Under new management. See [original discussions](https://github.com/mattsta/ib_insync/discussions) for recent history. Create new discussions or PRs or issues under [the new primary repo](https://github.com/ib-api-reloaded/ib_async) for ongoing updates.

New contributions welcome. We are open to adding more maintainers with commit access if your updates and understanding of IBKR/TWS and Python are all high quality.

This is a small project with a userbase of widely varying experience and knowledge, so if you open issues which are more about IBKR problems and less about client problems, we may not be able to assist you unless your problem is a direct client issue and not one of many IBKR API edge cases. Feel free to open [Discussion topics](https://github.com/ib-api-reloaded/ib_async/discussions) about anything if you are unsure about a problem being IBKR, our client, or your own code usage.

## Introduction

The goal of the `ib_async` library is to make working with the
[Trader Workstation API](https://ibkrcampus.com/ibkr-api-page/twsapi-doc/)
from Interactive Brokers as easy as possible.

The main features are:

* An easy to use linear style of programming;
* An [IB component](https://ib-api-reloaded.github.io/ib_async/api.html#module-ib_async.ib)
  that automatically keeps in sync with the TWS or IB Gateway application;
* A fully asynchonous framework based on
  [asyncio](https://docs.python.org/3/library/asyncio.html)
  and
  [eventkit](https://github.com/erdewit/eventkit)
  for advanced users;
* Interactive operation with live data in Jupyter notebooks.

Be sure to take a look at the
[notebooks](https://ib-api-reloaded.github.io/ib_async/notebooks.html),
the [recipes](https://ib-api-reloaded.github.io/ib_async/recipes.html)
and the [API docs](https://ib-api-reloaded.github.io/ib_async/api.html).


## Installation

```
pip install ib_async
```

Requirements:

- Python 3.10 or higher
  - We plan to support Python releases [2 years back](https://devguide.python.org/versions/) which allows us to continue adding newer features and performance improvements over time.
- A running IB Gateway application (or TWS with API mode enabled)
    - [stable gateway](https://www.interactivebrokers.com/en/trading/ibgateway-stable.php) — updated every few months
    - [latest gateway](https://www.interactivebrokers.com/en/trading/ibgateway-latest.php) — updated weekly
- Make sure the [API port is enabled](https://ibkrcampus.com/ibkr-api-page/twsapi-doc/#tws-download) and 'Download open orders on connection' is checked.
- You may also want to increase the Java memory usage under `Configure->Settings->Memory Allocation` to 4096 MB minimum to prevent gateway crashes when loading bulk data.

The ibapi package from IB is not needed. `ib_async` implements the full IBKR API protocol internally.

## Build Manually

First, install poetry:

```
pip install poetry -U
```

### Installing Only Library

```
poetry install
```

### Install Everything (enable docs + dev testing)

```
poetry install --with=docs,dev
```

## Generate Docs

```
poetry install --with=docs
poetry run sphinx-build -b html docs html
```

## Check Types

```
poetry run mypy ib_async
```

## Build Package

```
poetry build
```

## Upload Package (if maintaining)

```
poetry install
poetry config pypi-token.pypi your-api-token
poetry publish --build
```

## Example

This is a complete script to download historical data:

```python
from ib_async import *
# util.startLoop()  # uncomment this line when in a notebook

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

ib.reqMarketDataType(4)  # Use free, delayed, frozen data
contract = Forex('EURUSD')
bars = ib.reqHistoricalData(
    contract, endDateTime='', durationStr='30 D',
    barSizeSetting='1 hour', whatToShow='MIDPOINT', useRTH=True)

# convert to pandas dataframe (pandas needs to be installed):
df = util.df(bars)
print(df)
```

Output:

```
                   date      open      high       low     close  volume
0   2019-11-19 23:15:00  1.107875  1.108050  1.107725  1.107825      -1
1   2019-11-20 00:00:00  1.107825  1.107925  1.107675  1.107825      -1
2   2019-11-20 01:00:00  1.107825  1.107975  1.107675  1.107875      -1
3   2019-11-20 02:00:00  1.107875  1.107975  1.107025  1.107225      -1
4   2019-11-20 03:00:00  1.107225  1.107725  1.107025  1.107525      -1
..                  ...       ...       ...       ...       ...     ...
705 2020-01-02 14:00:00  1.119325  1.119675  1.119075  1.119225      -1
```

## Documentation

The complete [API documentation](https://ib-api-reloaded.github.io/ib_async/api.html).

[Changelog](https://ib-api-reloaded.github.io/ib_async/changelog.html).

## Community Resources

If you have other public work related to `ib_async` or `ib_insync` open an issue and we can keep an active list here.

Projects below are not endorsed by any entity and are purely for reference or entertainment purposes.

- Adi's livestream VODs about using IBKR APIs: [Interactive Brokers API in Python](https://www.youtube.com/playlist?list=PLCZZtBmmgxn8CFKysCkcl-B1tqRgCCNIX)
- Matt's IBKR python CLI: [icli](http://github.com/mattsta/icli)
- Corporate data parsing via IBKR API: [ib_fundamental](https://github.com/quantbelt/ib_fundamental)

## Disclaimer

The software is provided on the conditions of the simplified BSD license.

This project is not affiliated with Interactive Brokers Group, Inc.

[Official Interactive Brokers API Docs](https://ibkrcampus.com/ibkr-api-page/twsapi-doc/)

## History

This library was originally created by [Ewald de Wit](https://github.com/erdewit) as [`tws_async` in early-2017](https://github.com/erdewit/tws_async) then became the more prominent [`ib_insync` library in mid-2017](https://github.com/erdewit/ib_insync). He maintained and improved the library for the world to use for free until his unexpected passing in early 2024. Afterward, we decided to rename the project to `ib_async` under a new github organization since we lost access to modify anything in the original repos and packaging and docs infrastructure.

The library is currently maintained by [Matt Stancliff](https://github.com/mattsta) and we are open to adding more committers and org contributors if people show interest in helping out.
