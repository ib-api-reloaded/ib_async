"""IBKR's reroute messages, decoded, reach the reroute events with the
stream they reroute (more cases in tests/test_streams.py)."""

from __future__ import annotations

import ib_async as ibi
from ib_async._pb import RerouteMarketDataRequest_pb2, RerouteMarketDepthRequest_pb2
from ib_async._subscriptions import MktDataSub, MktDepthSub

CONTRACT = ibi.Stock("SIM", "SMART", "USD", conId=1)
REROUTE_MKT_DATA, REROUTE_MKT_DEPTH = 91, 92


def test_decoded_reroute_carries_the_market_data_stream() -> None:
    ib = ibi.IB()
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(CONTRACT)
    ib.wrapper.subscriptions.add(MktDataSub(reqId=12, contract=CONTRACT, ticker=ticker))
    seen: list[tuple[ibi.Stream, int, str]] = []
    ib.rerouteMktDataReqEvent += lambda s, conId, exchange: seen.append(
        (s, conId, exchange)
    )

    message = RerouteMarketDataRequest_pb2.RerouteMarketDataRequest(
        reqId=12, conId=345, exchange="SMART"
    )
    ib.client.decoder.processProtoBuf(REROUTE_MKT_DATA, message.SerializeToString())

    assert seen == [(ibi.MarketDataStream(12, CONTRACT, ticker), 345, "SMART")]


def test_decoded_reroute_carries_the_market_depth_stream() -> None:
    ib = ibi.IB()
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(CONTRACT)
    ib.wrapper.subscriptions.add(
        MktDepthSub(reqId=22, contract=CONTRACT, ticker=ticker)
    )
    seen: list[tuple[ibi.Stream, int, str]] = []
    ib.rerouteMktDepthReqEvent += lambda s, conId, exchange: seen.append(
        (s, conId, exchange)
    )

    message = RerouteMarketDepthRequest_pb2.RerouteMarketDepthRequest(
        reqId=22, conId=789, exchange="ISLAND"
    )
    ib.client.decoder.processProtoBuf(REROUTE_MKT_DEPTH, message.SerializeToString())

    assert seen == [(ibi.MarketDepthStream(22, CONTRACT, ticker), 789, "ISLAND")]
