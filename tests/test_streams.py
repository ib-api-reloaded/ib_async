"""Every live stream is a public Stream of its own type, and the events
about a stream carry it.

One contract can carry market data, depth and tick-by-tick at once, so a
reqId or a contract alone does not say which stream an error or reroute
concerns. An error that ends a stream closes it before errorEvent fires,
so the event itself names the stream.
"""

from __future__ import annotations

import ib_async as ibi
from ib_async import (
    ContractStream,
    MarketDataStream,
    MarketDepthStream,
    PnLStream,
    RealTimeBarsStream,
    ScannerStream,
    SnapshotStream,
    Stream,
    TickByTickStream,
    TickerStream,
)
from ib_async.util import getLoop
from tests._sim import CONTRACT, SimulatedTws


def started() -> SimulatedTws:
    return SimulatedTws(getLoop())


def reqIdOf(tws: SimulatedTws, kind: str) -> int:
    [ask] = tws.openAsks(kind)
    assert ask.reqId is not None
    return ask.reqId


def kinds(streams: dict[int, Stream]) -> set[type[Stream]]:
    return {type(s) for s in streams.values()}


def test_each_stream_is_its_own_type_with_exactly_its_data() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqTickByTickData(CONTRACT, "AllLast")
    tws.ib.reqMktDepth(CONTRACT)
    bars = tws.ib.reqRealTimeBars(CONTRACT, 5, "TRADES", False)
    pnl = tws.ib.reqPnL("DU1", "MODEL")
    tws.run()

    streams = tws.ib.streams()

    mktData = streams[reqIdOf(tws, "reqMktData")]
    assert isinstance(mktData, MarketDataStream)
    assert (mktData.contract, mktData.ticker) == (CONTRACT, ticker)
    tickByTick = streams[reqIdOf(tws, "reqTickByTickData")]
    assert isinstance(tickByTick, TickByTickStream)
    assert (tickByTick.tickType, tickByTick.ticker) == ("AllLast", ticker)
    depth = streams[reqIdOf(tws, "reqMktDepth")]
    assert isinstance(depth, MarketDepthStream) and depth.ticker is ticker
    realTime = streams[reqIdOf(tws, "reqRealTimeBars")]
    assert isinstance(realTime, RealTimeBarsStream)
    assert (realTime.bars, realTime.reqId) == (bars, bars.reqId)
    account = streams[reqIdOf(tws, "reqPnL")]
    assert isinstance(account, PnLStream)
    assert (account.account, account.modelCode, account.pnl) == ("DU1", "MODEL", pnl)
    assert not isinstance(account, ContractStream)
    assert set(streams) == {s.reqId for s in streams.values()}
    assert len(streams) == 5


def test_the_bases_group_what_kinds_share() -> None:
    tws = started()
    tws.ib.reqMktData(CONTRACT)
    tws.ib.reqTickByTickData(CONTRACT, "BidAsk")
    tws.ib.reqMktDepth(CONTRACT)
    tws.ib.reqRealTimeBars(CONTRACT, 5, "TRADES", False)
    tws.run()
    streams = tws.ib.streams().values()
    assert all(isinstance(s, ContractStream) for s in streams)
    tickers = [s for s in streams if isinstance(s, TickerStream)]
    assert len(tickers) == 3 and len({id(s.ticker) for s in tickers}) == 1


def test_a_stream_matches_by_its_type_and_fields() -> None:
    tws = started()
    tws.ib.reqTickByTickData(CONTRACT, "BidAsk")
    tws.run()
    [stream] = tws.ib.streams().values()
    match stream:
        case TickByTickStream(tickType="BidAsk", ticker=ticker):
            assert ticker.contract == CONTRACT
        case _:
            raise AssertionError(stream)


def test_streams_of_a_contract_match_by_the_instrument_not_the_object() -> None:
    """Another Contract object for the same instrument, made later, finds
    the same streams: matched by conId, not by which object was used."""
    tws = started()
    tws.ib.reqMktData(CONTRACT)
    tws.ib.reqTickByTickData(CONTRACT, "AllLast")
    tws.ib.reqMktDepth(CONTRACT)
    tws.ib.reqRealTimeBars(CONTRACT, 5, "TRADES", False)
    other = ibi.Stock("OTHER", "SMART", "USD", conId=2)
    tws.ib.reqMktData(other)
    tws.ib.reqPnL("DU1")
    tws.run()

    sameInstrument = ibi.Stock("SIM", "SMART", "USD", conId=1)
    assert sameInstrument is not CONTRACT
    found = tws.ib.streams(sameInstrument)

    assert kinds(found) == {
        MarketDataStream,
        TickByTickStream,
        MarketDepthStream,
        RealTimeBarsStream,
    }
    assert set(found) == {s.reqId for s in found.values()}
    assert kinds(tws.ib.streams(other)) == {MarketDataStream}


def test_streams_of_a_bag_match_by_its_legs_whatever_its_conid() -> None:
    """IBKR's copy of a bag carries a combo conId the user's bag lacks;
    the legs say which spread it is."""
    tws = started()
    legs = [ibi.ComboLeg(conId=11, ratio=1, action="BUY", exchange="SMART")]
    mine = ibi.Contract(
        secType="BAG", symbol="SIM", exchange="SMART", currency="USD", comboLegs=legs
    )
    tws.ib.reqMktData(mine)
    tws.run()
    theirs = ibi.Contract(
        secType="BAG",
        symbol="SIM",
        exchange="SMART",
        currency="USD",
        conId=28812380,
        comboLegs=list(legs),
    )
    assert kinds(tws.ib.streams(theirs)) == {MarketDataStream}


def test_streams_of_an_unqualified_contract_match_by_its_fields() -> None:
    """Market data needs a qualified contract; bars do not."""
    tws = started()
    tws.ib.reqRealTimeBars(ibi.Stock("SIM", "SMART", "USD"), 5, "TRADES", False)
    tws.run()
    found = tws.ib.streams(ibi.Stock("SIM", "SMART", "USD"))
    assert kinds(found) == {RealTimeBarsStream}
    assert tws.ib.streams(ibi.Stock("SIM", "SMART", "EUR")) == {}


def test_streams_without_an_instrument_are_never_on_a_contract() -> None:
    tws = started()
    tws.ib.reqPnL("DU1")
    tws.ib.reqScannerSubscription(ibi.ScannerSubscription())
    tws.run()
    assert kinds(tws.ib.streams()) == {PnLStream, ScannerStream}
    assert tws.ib.streams(CONTRACT) == {}


def test_a_snapshot_is_its_own_type_with_its_own_ticker() -> None:
    """A snapshot with no stream live gets a private Ticker; with a stream
    live, reqMktData returns the stream's Ticker and sends nothing."""
    tws = started()
    snapshot = tws.ib.reqMktData(CONTRACT, snapshot=True)
    tws.run()
    [stream] = tws.ib.streams().values()
    assert isinstance(stream, SnapshotStream) and stream.ticker is snapshot
    assert snapshot not in tws.ib.tickers()


def test_stream_finds_a_live_stream_only() -> None:
    tws = started()
    tws.ib.reqMktData(CONTRACT)
    tws.run()
    reqId = reqIdOf(tws, "reqMktData")
    assert isinstance(tws.ib.stream(reqId), MarketDataStream)
    assert tws.ib.stream(reqId + 1000) is None
    tws.ib.cancelMktData(CONTRACT)
    tws.run()
    assert tws.ib.stream(reqId) is None
    assert tws.ib.streams() == {}


def test_a_stream_sent_again_is_found_under_its_new_reqid() -> None:
    tws = started()
    tws.ib.reqRealTimeBars(CONTRACT, 5, "TRADES", False)
    tws.run()
    [ask] = tws.openAsks("reqRealTimeBars")
    old = ask.reqId
    assert old is not None
    tws.bust(ask)
    new = reqIdOf(tws, "reqRealTimeBars")
    assert new != old
    assert tws.ib.stream(old) is None
    found = tws.ib.stream(new)
    assert found is not None and found.reqId == new


def test_an_error_names_its_stream_among_three_on_one_contract() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.ib.reqTickByTickData(CONTRACT, "AllLast")
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()
    seen: list[tuple[Stream, int, bool, bool]] = []

    def onStreamError(
        stream: Stream, errorCode: int, errorString: str, ended: bool
    ) -> None:
        # The stream is already closed when the event fires.
        seen.append((stream, errorCode, ended, tws.ib.stream(stream.reqId) is None))

    tws.ib.streamErrorEvent += onStreamError
    [depthAsk] = tws.openAsks("reqMktDepth")
    tws.refuseStream(depthAsk, 309)

    [(stream, code, ended, gone)] = seen
    assert isinstance(stream, MarketDepthStream) and stream.ticker is ticker
    assert (code, ended, gone) == (309, True, True)
    assert kinds(tws.ib.streams()) == {MarketDataStream, TickByTickStream}


def test_a_warning_for_a_stream_leaves_it_running() -> None:
    tws = started()
    tws.ib.reqMktData(CONTRACT)
    tws.run()
    reqId = reqIdOf(tws, "reqMktData")
    seen: list[tuple[type[Stream], int, bool]] = []
    tws.ib.streamErrorEvent += lambda s, code, text, ended: seen.append(
        (type(s), code, ended)
    )

    tws.wrapper.error(reqId, 10167, "Displaying delayed market data", "")

    assert seen == [(MarketDataStream, 10167, False)]
    assert tws.ib.stream(reqId) is not None


def test_ended_means_the_error_ended_it_not_an_error_event_handler() -> None:
    tws = started()
    ticker = tws.ib.reqMktData(CONTRACT)
    tws.run()
    reqId = reqIdOf(tws, "reqMktData")
    seen: list[bool] = []
    tws.ib.errorEvent += lambda r, code, text, contract: tws.ib.cancelMktData(
        ticker.contract
    )
    tws.ib.streamErrorEvent += lambda s, code, text, ended: seen.append(ended)

    tws.wrapper.error(reqId, 10167, "Displaying delayed market data", "")

    assert seen == [False]
    assert tws.ib.stream(reqId) is None


def test_an_error_without_a_stream_fires_only_error_event() -> None:
    tws = started()
    errors: list[int] = []
    streamErrors: list[int] = []
    tws.ib.errorEvent += lambda reqId, code, text, contract: errors.append(code)
    tws.ib.streamErrorEvent += lambda s, code, text, ended: streamErrors.append(code)

    tws.wrapper.error(4242, 354, "Requested market data is not subscribed", "")

    assert (errors, streamErrors) == ([354], [])


def test_reroute_events_carry_the_stream() -> None:
    tws = started()
    tws.ib.reqMktData(CONTRACT)
    tws.ib.reqMktDepth(CONTRACT)
    tws.run()
    seen: list[tuple[type[Stream], int, str]] = []
    tws.ib.rerouteMktDataReqEvent += lambda s, conId, exchange: seen.append(
        (type(s), conId, exchange)
    )
    tws.ib.rerouteMktDepthReqEvent += lambda s, conId, exchange: seen.append(
        (type(s), conId, exchange)
    )

    tws.wrapper.rerouteMktDataReq(reqIdOf(tws, "reqMktData"), 345, "SMART")
    tws.wrapper.rerouteMktDepthReq(reqIdOf(tws, "reqMktDepth"), 789, "ISLAND")
    tws.wrapper.rerouteMktDataReq(4242, 1, "SMART")  # no such stream

    assert seen == [
        (MarketDataStream, 345, "SMART"),
        (MarketDepthStream, 789, "ISLAND"),
    ]


def test_a_stream_prints_its_reqid_and_not_what_it_fills() -> None:
    tws = started()
    tws.ib.reqMktData(CONTRACT)
    tws.run()
    [stream] = tws.ib.streams().values()
    text = repr(stream)
    assert text.startswith("MarketDataStream(") and f"reqId={stream.reqId}" in text
    assert "Ticker" not in text


def test_streams_are_equal_when_kind_and_reqid_are() -> None:
    tws = started()
    tws.ib.reqMktData(CONTRACT)
    tws.run()
    reqId = reqIdOf(tws, "reqMktData")
    stream = tws.ib.stream(reqId)
    assert stream == tws.ib.stream(reqId)
    assert stream != SnapshotStream(reqId, CONTRACT, ibi.Ticker())
