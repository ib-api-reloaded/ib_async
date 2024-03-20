import ib_async
from ib_async import *

import pandas as pd


def test_contract_format_data_pd():
    """Simple smoketest to verify everything still works minimally."""
    ib = ib_async.IB()
    ib.connect("127.0.0.1", 4001, clientId=90, readonly=True)

    symbols = ["AMZN", "TSLA"]

    # Method to get OHLCV
    def get_OHLCV(
        symbol,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="1 hour",
        whatToShow="TRADES",
        useRTH=False,
        formatDate=1,
    ):
        bars = ib.reqHistoricalData(
            symbol,
            endDateTime,
            durationStr,
            barSizeSetting,
            whatToShow,
            useRTH,
            formatDate,
        )
        df = util.df(bars)
        df["date"] = df["date"].dt.tz_convert("America/New_York")
        df = df.drop(columns=["average", "barCount"])
        # df.set_index("date", inplace=True)

        print("\n", df)

        # df = df.iloc[::-1]
        # df.to_csv("{}.csv".format(symbol.symbol))
        # df = pd.read_csv("{}.csv".format(symbol.symbol))
        df.columns = ["date", "open", "high", "low", "close", "volume"]

        df["date"] = pd.to_datetime(df["date"])
        df.set_index("date", inplace=True)

        print(f"Data for {symbol.symbol} downloaded OK with OLD")
        return df

    for symbol_str in symbols:
        symbol = Stock(symbol_str, "SMART", "USD")
        df = get_OHLCV(symbol)
