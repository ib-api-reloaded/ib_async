"""Decoder mask-bit decoding for historical bid/ask ticks must match the
live tick-by-tick handler so that user code sees consistent flag values
regardless of whether ticks came from a streaming or historical request.

Per the IB TWS API spec: bit 0 (mask & 1) is bidPastLow, bit 1 (mask & 2)
is askPastHigh. Both decoder paths must follow this.
"""

import ib_async as ibi
from ib_async._requests import ReqIdKey
from ib_async.decoder import Decoder


def _decode_historical_bidask_with_mask(mask: int):
    ib = ibi.IB()
    decoder = Decoder(ib.wrapper, serverVersion=176)

    req_id = 11
    req, _ = ib.wrapper.requests.open(ReqIdKey(req_id))

    # Synthetic wire payload: msgId, reqId, n=1, [time, mask, priceBid,
    # priceAsk, sizeBid, sizeAsk] * n, done.
    fields = [
        "97",
        str(req_id),
        "1",
        "1700000000",
        str(mask),
        "100.0",
        "100.5",
        "10",
        "20",
        "1",
    ]
    decoder.historicalTicksBidAsk(fields)

    result = req.future.result()
    assert len(result) == 1
    return result[0].tickAttribBidAsk


def test_historical_bidask_mask_bit0_is_bidpastlow():
    attrib = _decode_historical_bidask_with_mask(0x01)
    assert attrib.bidPastLow is True
    assert attrib.askPastHigh is False


def test_historical_bidask_mask_bit1_is_askpasthigh():
    attrib = _decode_historical_bidask_with_mask(0x02)
    assert attrib.bidPastLow is False
    assert attrib.askPastHigh is True


def test_historical_bidask_mask_both_bits_set():
    attrib = _decode_historical_bidask_with_mask(0x03)
    assert attrib.bidPastLow is True
    assert attrib.askPastHigh is True


def test_historical_bidask_matches_live_tickbytick_decoding():
    """Both decoders must agree on which bit means what."""
    ib = ibi.IB()
    decoder = Decoder(ib.wrapper, serverVersion=176)

    # Capture the tickByTickBidAsk attrib for mask=1.
    captured = {}

    def fake_tick_by_tick_bid_ask(
        reqId, time, bidPrice, askPrice, bidSize, askSize, attrib
    ):  # noqa: N803
        captured["live"] = attrib

    ib.wrapper.tickByTickBidAsk = fake_tick_by_tick_bid_ask  # type: ignore[method-assign]

    # Live tickByTick payload for tickType=3 (bid/ask):
    #   msgId, reqId, tickType, time, bidPrice, askPrice, bidSize, askSize, mask
    decoder.tickByTick(
        ["99", "1", "3", "1700000000", "100.0", "100.5", "10", "20", "1"]
    )

    historical = _decode_historical_bidask_with_mask(0x01)
    live = captured["live"]
    assert historical.bidPastLow == live.bidPastLow
    assert historical.askPastHigh == live.askPastHigh
